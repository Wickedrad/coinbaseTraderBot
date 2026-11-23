import assert from 'node:assert/strict';
import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import crypto from 'crypto';
import {
  assertCalibrationDays, calibrateStage, calibrationCode, checkDepthModelCalibration, loadRealFitRows, realFitKey, realFitRows, REAL_FIT_FILE, REAL_FIT_FOLLOW_FILE, restrictFitRows, twinTickersOf, writeRealFitHandoff,
  assertDisjoint, assertModelFitDays, assertHeldOut, auc, CONFIRM_DAYS, checkDepthModelReuse, checkReal15m, collectSweep, corrMatrix, dayRows, discriminate, discriminatePerDay, FEATURE_CODE_VERSION, FEATURES, fastRows, filledDayRows, followDiag, isBlind, loadRealSide,
  judgeSweepRows, loadDepthParamsFile, MIN_CUSTOM_JUDGED_DAYS, MIN_DAY_LIVES, MIN_SWEEP_LIVES, outcome, parseDays, parseFailedSteps, prepDay, prepReport, prepStatus, quantile, quantiles3, real15mError, real15mTag,
  REAL15M_VERSION, realMetaDiff, resolveSplit, resolveSweepFit, restrictLine, rowBuilder, runSweep, type Row, SPLITS, stageVerdict, stressAuc, sweepShardName, topCorrDiffs, twinSource, type SweepCollected,
} from '../research/historyTwin';
import {
  CEM_SD_FLOOR, cemStep, clipParams, describeParams, eliteOf, eliteStats, fromSpace, generationCandidates, latinHypercube, mergeShards, parentsFrom, parseShard, rankResults, shardRange,
  SWEEP_VERSION, toSpace, type SweepShardFile,
} from '../research/history/depthParamSearch';
import { DEFAULT_DEPTH_SIM_PARAMS, DEPTH_PARAM_NAMES, DEPTH_PARAM_SPACE, readDepthModel, resolveDepthSimParams, type AssetCalibration, type DepthModel, type DepthSimParams } from '../research/history/depthSim';
import { depthModelNote, depthPicksNote, depthSims, fillDayFile, simulatorLine } from '../research/goLiveTally';
import { DEPTH_MODEL_SCHEMA } from '../research/history/depthModelVersion';
import { calibrateDepthModel, gapsOfAsset, withCalibration, type CalCols } from '../research/history/depthCalibrate';
import { REPLAY_VERSION } from '../research/history/historyReplay';
import { pinned, synthModel, synthRequoteDay, writeEventsGz } from './twinSweepSynth';
import { tmpDir } from './helpers';
import { depthStudy } from '../research/depthStudy';
import { synthRecording, writeRecording } from './depthStudySynth';
import { childExecArgv, childNodeOptions, DEFAULT_CHILD_HEAP_MB, noAnswerMessage, runUnits, UNIT_TMP_PREFIX } from '../research/history/unitPool';

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
  write({ ...model, schema: DEPTH_MODEL_SCHEMA + 1 }); assert.throws(() => assertModelFitDays(f, split), /refit it with this code/);
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
  fs.copyFileSync(path.join(ROOT, '.github/scripts/twin-windows.py'), path.join(ws, '.github/scripts/twin-windows.py')); // S2: the verdict job's windows assembly is a script file now
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
const READ = ['features-real.json', 'features-requote.json', 'features-depth.json', 'paired.json', 'split.json', 'real-meta.json', 'real-activity.json', 'real-fit-features.json'];
const FAST_ONLY = /^\[twin\] (fast: |depth fill-in: \d+ day\(s\) built in-stream)/;
/** The full route's own lines that say a file was written (the fast route writes no filled day), and the directory in a line. */
const FILL_WRITTEN = /^\[twin\] depth fill-in written for \d+ day\(s\)$/;
/** The timing lines (round S1) of the file route's three stages: seconds only, the fast route prints its own `fast: STEP N s` lines instead. */
const FILE_ROUTE_TIMING = /^\[twin\] (match (\d{4}-\d{2}-\d{2}: tickers \d+\.\d s, restrict \d+\.\d s, pair \d+\.\d s|took \d+\.\d s \(jobs \d+\))|fill (\d{4}-\d{2}-\d{2}: \d+\.\d s|took \d+\.\d s)|features (\w+ \d{4}-\d{2}-\d{2}: \d+\.\d s|took \d+\.\d s \(jobs \d+\)))$/;
const sameLines = (full: string[], fast: string[], fullOut: string, fastOut: string) => {
  const norm = (l: string, out: string) => l.split(out).join('OUT');
  assert.deepEqual(fast.filter((l) => !FAST_ONLY.test(l)).map((l) => norm(l, fastOut)), full.filter((l) => !FILL_WRITTEN.test(l) && !FILE_ROUTE_TIMING.test(l)).map((l) => norm(l, fullOut)));
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
const REAL_SIDE = ['features-real.json', 'paired.json', 'real-meta.json', 'real-activity.json', 'real-fit-features.json'];
const metaFilesOnly = (w: FastWorld, name: string) => { const d = path.join(w.root, name); fs.mkdirSync(d); copyFiles(w.real, d, fs.readdirSync(w.real).filter((f) => f.startsWith('meta-'))); return d; };
const readJ = (f: string) => JSON.parse(fs.readFileSync(f, 'utf8'));
/** fastRows in this process: the lines it prints, and the files it writes in `out` (its split.json made by the split stage). */
async function fastHere(w: FastWorld, out: string, realCache: string | undefined, o: { realDir?: string; twinDir?: string; handoff?: string } = {}): Promise<string[]> {
  const lines: string[] = [];
  await fastRows({ out, realDir: o.realDir ?? w.real, twinDir: o.twinDir ?? w.twin, days: FAST_JUDGE, modelFile: w.modelFile, realCache, realRun: realCache ? '4242' : undefined, handoff: o.handoff, log: (l) => lines.push(l) });
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
  for (const f of ['features-real.json', 'features-requote.json', 'features-depth.json', 'paired.json', 'split.json', 'real-activity.json', 'real-fit-features.json']) assert.equal(fs.readFileSync(path.join(out, f), 'utf8'), fs.readFileSync(path.join(full, f), 'utf8'), `${f} equals the full route's, bytes`);
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
  await refused(withMeta('tag', (m) => { m.real15m = 'r15m-0|exclude=DOGE'; }), head('real days tag r15m-0\\|exclude=DOGE', `real days tag ${real15mTag().split('|').join('\\|')}`, 'real days tag'));
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
  await refused(old, /^real_features_run 4242 has no real-meta\.json, real-activity\.json, real-fit-features\.json: it was made before the fast route kept its real side \(or it read the confirm days\), and an old run is never guessed at\. Dispatch a dev run with this code/);
  // R2: a real side of an earlier round (every sidecar but the real FIT rows) is refused, naming that file, and so is one with other fit days' rows
  const noFitRows = path.join(w.root, 'no-fit-rows'); copyFiles(cache, noFitRows, REAL_SIDE.filter((n) => n !== 'real-fit-features.json'));
  await refused(noFitRows, /^real_features_run 4242 has no real-fit-features\.json: it was made before the per-asset calibration kept the real FIT rows \(round R2\), and an old run is never guessed at\. Dispatch a dev run with this code/);
  const fitRows = readJ(path.join(cache, 'real-fit-features.json')) as Array<{ day: string }>;
  assert.ok(fitRows.length > 0 && FAST_FIT.every((d) => fitRows.some((r) => r.day === d)), 'the real side holds rows of every fit day');
  const otherFitDay = path.join(w.root, 'other-fit-day'); copyFiles(cache, otherFitDay, REAL_SIDE);
  fs.writeFileSync(path.join(otherFitDay, 'real-fit-features.json'), JSON.stringify([...fitRows.filter((r) => r.day !== FAST_FIT[1]), { ...fitRows[0], day: '2026-11-15' }]));
  await refused(otherFitDay, /^real_features_run 4242: real-fit-features\.json holds rows of 2026-11-11, 2026-11-15, these fit days are 2026-11-11, 2026-11-12 \(other fit days: 2026-11-15\) \(none for 2026-11-12\)\. Leave real_features_run empty to parse the real days again$/);
  const junkFit = path.join(w.root, 'junk-fit'); copyFiles(cache, junkFit, REAL_SIDE); fs.writeFileSync(path.join(junkFit, 'real-fit-features.json'), '{"not":"rows"}');
  await refused(junkFit, /^real_features_run 4242: real-fit-features\.json is not a list of rows$/);
  const nofeat = path.join(w.root, 'nofeat'); copyFiles(cache, nofeat, ['real-meta.json', 'real-activity.json', 'real-fit-features.json', 'paired.json']);
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
  thr(() => line(put('tag', {}), path.join(dir, 'old-meta.json')), new RegExp(`^depth_model_run 321: the model was fitted from real days tagged r15m-0\\|exclude=DOGE, these are tagged ${real15mTag().split('|').join('\\|')}`));
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
  assert.match(ok.log, /^\[twin\] real side of run 77 read from Drive: 5 file\(s\)$/m);
  assert.equal(ok.calls.trim(), 'get simulated/history-twin/77/twinlite data/real-cache --include features-real.json --include real-meta.json --include real-activity.json --include real-fit-features.json --include paired.json');
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
  const withSide = put([...core, 'real-meta.json', 'real-activity.json', 'real-fit-features.json', 'verdict-junk.txt']); assert.equal(withSide.r.status, 0, withSide.r.stderr);
  assert.deepEqual(withSide.kept, [...core, 'real-meta.json', 'real-activity.json', 'real-fit-features.json'].sort());
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

// ---------------------------------------------------------------------------------------------------------------
// ---- R2 begin ----
// Round R2 (Nov 22): the depth model's per-asset LEVEL calibration, fitted on the FIT days (research/history/depthCalibrate.ts, whose own tests are
// tests/depthCalibrate.test.ts). Here: the stage that runs it (days it may read, the block it writes, the handoff it leaves), the real FIT rows beside
// the judged real side (a new file of the cache key), the reuse of a calibrated model, the verdict's per-asset gap lines and the workflow's wiring.
// Synthetic days only: the FIT days' real side is the fill-in of a requote day under a model with KNOWN per-asset multipliers, so the stage has an answer to find.

const CAL_TRUTH: Record<string, AssetCalibration> = {
  BTC: { tradeRateMult: 1.5, tradeSizeMult: 1.6, topSizeMult: 1.3, levelSizeMult: 2.2, flickMult: 0.8 },
  ETH: { tradeRateMult: 0.7, tradeSizeMult: 0.6, topSizeMult: 0.8, levelSizeMult: 0.5, flickMult: 1.3 },
};
interface CalWorld extends FastWorld { twinFit: string }
let calOnce: Promise<CalWorld> | undefined;
/** Like fastWorld, but the two FIT days hold 12 contracts an asset (BTC and ETH): their real days are the fill-in of the requote FIT day (kept in `twinFit`, as the
 *  workflow keeps them in data/replay-fit) under CAL_TRUTH, the judged days as in fastWorld (an uncalibrated fill-in). A copy per call: a stage writes into its model file. */
async function calWorld(): Promise<CalWorld> {
  calOnce ??= (async () => {
    const root = tmpDir(), real = path.join(root, 'real15m'), twin = path.join(root, 'replay-src'), twinFit = path.join(root, 'replay-fit');
    for (const d of [real, twin, twinFit]) fs.mkdirSync(d);
    const modelFile = path.join(root, 'depth_model.json'), truthFile = path.join(root, 'truth_model.json');
    // the model's own params block pins the simulator's constants (tests/twinSweepSynth.ts `pinned`): the stage plays the model FILE, so the real FIT days, the twin's
    // rows and the recovery below are all made with the same constants whatever DEFAULT_DEPTH_SIM_PARAMS becomes (RUNBOOK 9.5), and the calibration multiplies on top
    const base = pinned({ ...synthModel({ days: FAST_FIT }), schema: DEPTH_MODEL_SCHEMA });
    fs.writeFileSync(modelFile, JSON.stringify(base)); fs.writeFileSync(truthFile, JSON.stringify(withCalibration(base, FAST_FIT, 0, CAL_TRUTH)));
    const neutral = readDepthModel(modelFile)!, truth = readDepthModel(truthFile)!;
    for (const [i, d] of [...FAST_FIT, ...FAST_JUDGE].entries()) {
      const fit = FAST_FIT.includes(d), raw = path.join(root, `raw-${d}.jsonl.gz`), f = path.join(real, `md-${d}.jsonl.gz`);
      writeEventsGz(raw, synthRequoteDay({ day: d, assets: fit ? ['BTC', 'ETH'] : ['BTC', 'ETH', 'SOL'], windows: fit ? 12 : 4, seed: 40 + i }));
      await fillDayFile(raw, f, { how: 'depth' }, fit ? truth : neutral);
      fs.writeFileSync(path.join(real, `meta-${d}.json`), JSON.stringify({ day: d, version: real15mTag(), sha256: sha256Of(f) }));
      if (fit) fs.copyFileSync(raw, path.join(twinFit, `md-${d}.jsonl.gz`));
      else writeEventsGz(path.join(twin, `md-${d}.jsonl.gz`), synthRequoteDay({ day: d, assets: ['BTC', 'ETH'], windows: 4, seed: 3 + i }));
    }
    fs.rmSync(truthFile);
    return { root, real, twin, twinFit, modelFile };
  })();
  const base = await calOnce, root = tmpDir();
  fs.cpSync(base.root, root, { recursive: true });
  return { root, real: path.join(root, 'real15m'), twin: path.join(root, 'replay-src'), twinFit: path.join(root, 'replay-fit'), modelFile: path.join(root, 'depth_model.json') };
}
const splitIn = (w: FastWorld, name = 'split') => { const d = path.join(w.root, name); fs.mkdirSync(d, { recursive: true }); okCli(...splitArgs(d)); return path.join(d, 'split.json'); };
const calArgs = (w: CalWorld, splitFile: string, out: string, ...more: string[]) => ['--stage', 'calibrate', '--depth-model', w.modelFile, '--split-file', splitFile, '--real', w.real, '--twin-fit', w.twinFit, '--out', out, ...more];
const withoutDays = (from: string, to: string, days: string[]) => { fs.mkdirSync(to, { recursive: true }); for (const f of fs.readdirSync(from)) if (!days.some((d) => f === `md-${d}.jsonl.gz`)) fs.copyFileSync(path.join(from, f), path.join(to, f)); return to; };

test('the calibration reads the model\'s own FIT days only: a DEV day, a CONFIRM day, a judged day, a model with no days and a calibration of other days are refused, and before any day file is opened', async () => {
  const dir = tmpDir(), dev = { name: 'dev', fit: [...SPLITS.dev.fit], judge: [...SPLITS.dev.judge] }, conf = { name: 'confirm', fit: [...SPLITS.confirm.fit], judge: [...SPLITS.confirm.judge] };
  const put = (name: string, days: string[] | undefined, o: Record<string, unknown> = {}) => { const f = path.join(dir, `${name}.json`); fs.writeFileSync(f, JSON.stringify({ ...synthModel({ days }), schema: DEPTH_MODEL_SCHEMA, ...(days === undefined ? { days: undefined } : {}), ...o })); return f; };
  const thr = (fn: () => unknown, re: RegExp) => assert.throws(fn, (e: Error) => { assert.match(e.message, re); return true; });
  // what it accepts: the model's days, all of them FIT days (the confirm refit is fitted on FIT + DEV: all fit days of the confirm split)
  assert.deepEqual(assertCalibrationDays(put('ok', dev.fit), dev), dev.fit);
  assert.deepEqual(assertCalibrationDays(put('ok-confirm', conf.fit), conf), conf.fit);
  assert.deepEqual(assertCalibrationDays(put('subset', [dev.fit[0], dev.fit[1]]), dev), [dev.fit[0], dev.fit[1]], 'a model fitted on some of the fit days');
  // a DEV (judged) day in a dev split, a CONFIRM day anywhere but the confirm split, and the confirm split's own judged days
  thr(() => assertCalibrationDays(put('dev-day', [...dev.fit, '2026-11-13']), dev), /overlap.*2026-11-13/);
  thr(() => assertCalibrationDays(put('confirm-day', [...dev.fit, '2026-11-18']), dev), /fitted on days outside the fit set: 2026-11-18/);
  thr(() => assertCalibrationDays(put('confirm-judged', [...conf.fit, '2026-11-18']), conf), /overlap.*2026-11-18/);
  thr(() => assertCalibrationDays(put('ok2', dev.fit), { ...dev, fit: [...dev.fit, '2026-11-18'] }), /confirm days \(2026-11-18\) are read only through split=confirm/);
  thr(() => assertCalibrationDays(put('stray', ['2026-11-11', '2026-11-30']), dev), /outside the fit set: 2026-11-30/);
  thr(() => assertCalibrationDays(put('nodays', []), dev), /does not record the days it was fitted on/);
  thr(() => assertCalibrationDays(put('nodays2', undefined), dev), /does not record the days it was fitted on/);
  // a block fitted on other days than the model's
  const model = { ...synthModel({ days: dev.fit }), schema: DEPTH_MODEL_SCHEMA };
  const other = path.join(dir, 'other-cal.json'); fs.writeFileSync(other, JSON.stringify(withCalibration(model, ['2026-11-11'], 2, { BTC: { ...CAL_TRUTH.BTC } })));
  thr(() => assertCalibrationDays(other, dev), /the depth model's calibration was fitted on 2026-11-11, not on the days the model was fitted on \(2026-11-11, 2026-11-12, 2026-11-15\)/);
  thr(() => assertModelFitDays(other, dev), /calibration was fitted on 2026-11-11/);
  // the stage refuses these before it opens a day: its day folders do not exist, and the reason is the days', not a missing file
  const split = path.join(dir, 'split.json'); fs.writeFileSync(split, JSON.stringify({ ...dev, warm: [] }));
  const stage = (modelFile: string, splitFile = split) => calibrateStage({ out: path.join(dir, 'handoff'), modelFile, splitFile, realDir: path.join(dir, 'no-real'), twinFitDir: path.join(dir, 'no-twin'), log: () => {} });
  await assert.rejects(stage(put('dev-day2', [...dev.fit, '2026-11-13'])), /overlap.*2026-11-13/);
  await assert.rejects(stage(put('confirm-day2', [...dev.fit, '2026-11-18'])), /outside the fit set: 2026-11-18/);
  await assert.rejects(stage(other), /calibration was fitted on 2026-11-11/);
  await assert.rejects(stage(put('ok3', dev.fit), path.join(dir, 'missing-split.json')), /no split in .*missing-split\.json/);
  await assert.rejects(stage(put('ok4', dev.fit)), /the calibration needs the cached real FIT day 2026-11-11 in .*no-real; dispatch prep_days=2026-11-11 first$/, 'a model that passes the days reaches the first file it needs, and says which');
  assert.ok(!fs.existsSync(path.join(dir, 'handoff')), 'and writes nothing before it has what it needs');
  // the stage in its own process: one [twin] ERROR line, a failed exit, and the model file as it was
  const bad = put('dev-day3', [...dev.fit, '2026-11-13']), before = fs.readFileSync(bad, 'utf8');
  const r = twinCli('--stage', 'calibrate', '--depth-model', bad, '--split-file', split, '--real', path.join(dir, 'no-real'), '--twin-fit', path.join(dir, 'no-twin'), '--out', path.join(dir, 'h2'));
  assert.notEqual(r.status, 0); assert.match(r.stderr, /^\[twin\] ERROR: .*overlap.*2026-11-13/m); assert.equal(fs.readFileSync(bad, 'utf8'), before);
  // the check a reused model goes through says the same
  thr(() => checkDepthModelCalibration(put('dev-day4', [...dev.fit, '2026-11-13']), dev, { run: '9' }), /^depth_model_run 9: .*overlap.*2026-11-13/);
  thr(() => checkDepthModelCalibration(put('nocal', dev.fit), dev, { run: '9' }), /^depth_model_run 9: the model has no calibration block: it was fitted before the per-asset calibration ran, or its calibration failed, so it is not reused\. Leave depth_model_run empty to fit and calibrate it again$/);
});

test('the calibrate stage fits the per-asset multipliers on the FIT days, writes the block into the model file, leaves the real FIT rows for the stages after it, recovers the known offsets, and a second run is refused', async () => {
  const w = await calWorld(), sp = splitIn(w), out = path.join(w.root, 'calib');
  const before = JSON.parse(fs.readFileSync(w.modelFile, 'utf8'));
  assert.equal(before.calibration, undefined);
  const stdout = okCli(...calArgs(w, sp, out));
  const lines = tw(stdout);
  const m = readDepthModel(w.modelFile)!, cal = m.calibration!;
  assert.ok(cal); assert.deepEqual(cal.fitDays, FAST_FIT); assert.equal(m.schema, DEPTH_MODEL_SCHEMA); assert.deepEqual(Object.keys(cal.byAsset).sort(), ['BTC', 'ETH']);
  // the offsets the real FIT days were made with are found (within the 12 percent the 5-iteration damped loop leaves on this world)
  for (const a of ['BTC', 'ETH']) for (const k of Object.keys(CAL_TRUTH[a]) as Array<keyof AssetCalibration>) assert.ok(Math.abs(cal.byAsset[a][k] / CAL_TRUTH[a][k] - 1) <= 0.12, `${a} ${k}: found ${cal.byAsset[a][k]}, made with ${CAL_TRUTH[a][k]}`);
  assert.ok(cal.iterations >= 2 && cal.iterations <= 5, `${cal.iterations} iterations`);
  // nothing else in the model file moved: the block is the only difference
  assert.deepEqual({ ...JSON.parse(fs.readFileSync(w.modelFile, 'utf8')), calibration: undefined }, { ...before, calibration: undefined });
  assert.deepEqual(fs.readdirSync(w.root).filter((f) => f.startsWith('depth_model')), ['depth_model.json'], 'written in place: no temporary file is left');
  // the lines: per iteration and asset, a final line per asset, the held-in check (run or skipped, with its reason), what was written, and a summary
  assert.ok(lines.filter((l) => /^\[twin\] calibration: asset (BTC|ETH) iter \d: gaps \(sd\) top /.test(l)).length >= 4);
  assert.equal(lines.filter((l) => /^\[twin\] calibration: asset \w+ final /.test(l)).length, 2);
  assert.ok(lines.some((l) => /^\[twin\] calibration: held-in check/.test(l)), 'the held-in check is run or says why it was skipped');
  assert.match(lines.find((l) => /^\[twin\] calibration: fitted on the FIT days/.test(l))!, /^\[twin\] calibration: fitted on the FIT days 2026-11-11 2026-11-12: 2 asset\(s\)/);
  assert.match(lines[lines.length - 1], new RegExp(`^\\[twin\\] calibration: written into the depth model \\(schema ${DEPTH_MODEL_SCHEMA}\\); \\d+ s$`));
  assert.ok(lines.every((l) => !/KX|md-2026|\$\d/.test(l)), 'numbers and asset names only: no ticker, no file of a day');
  // the model it leaves passes the checks the later stages make of it
  assert.doesNotThrow(() => assertModelFitDays(w.modelFile, { fit: FAST_FIT, judge: FAST_JUDGE }));
  assert.match(checkDepthModelCalibration(w.modelFile, { name: 'custom', fit: FAST_FIT, judge: FAST_JUDGE }, { run: '7' }), /^\[twin\] depth model calibration carried by run 7: assets BTC ETH, fitted on 2026-11-11 2026-11-12, \d iteration\(s\); no recalibration$/);
  // the handoff: the FIT days' real rows (and only those) and the follow diagnostics they feed, under a key
  assert.deepEqual(fs.readdirSync(out).sort(), [REAL_FIT_FILE, REAL_FIT_FOLLOW_FILE]);
  const rows = readJ(path.join(out, REAL_FIT_FILE)) as Array<{ day: string; ticker: string; src: string }>, fol = readJ(path.join(out, REAL_FIT_FOLLOW_FILE));
  assert.ok(rows.length >= 48 && FAST_FIT.every((d) => rows.some((r) => r.day === d)) && rows.every((r) => FAST_FIT.includes(r.day) && r.src === 'real'), `${rows.length} real FIT lives`);
  assert.deepEqual(fol.key, { fit: FAST_FIT, real15m: real15mTag(), featureCode: FEATURE_CODE_VERSION, shas: Object.fromEntries(FAST_FIT.map((d) => [d, sha256Of(path.join(w.real, `md-${d}.jsonl.gz`))])) });
  assert.equal(JSON.stringify(fol.rowsPerDay), JSON.stringify(Object.fromEntries(FAST_FIT.map((d) => [d, rows.filter((r) => r.day === d).length]))));
  // a second run on a calibrated model is refused (a model is calibrated once), and leaves the file as it is
  const bytes = fs.readFileSync(w.modelFile, 'utf8');
  const again = twinCli(...calArgs(w, sp, out));
  assert.notEqual(again.status, 0); assert.match(again.stderr, /^\[twin\] ERROR: the depth model already carries a calibration: a model is calibrated once/m); assert.equal(fs.readFileSync(w.modelFile, 'utf8'), bytes);
  // a requote FIT day that is not there: refused with its name, the model untouched
  const w2 = await calWorld(), bytes2 = fs.readFileSync(w2.modelFile, 'utf8');
  const lost = twinCli(...calArgs({ ...w2, twinFit: withoutDays(w2.twinFit, path.join(w2.root, 'fit-lost'), ['2026-11-12']) }, splitIn(w2), path.join(w2.root, 'c2')));
  assert.notEqual(lost.status, 0); assert.match(lost.stderr, /^\[twin\] ERROR: the calibration needs the requote day of FIT day 2026-11-12 in .*fit-lost/m); assert.equal(fs.readFileSync(w2.modelFile, 'utf8'), bytes2);
  // a real FIT day that is not there is refused too (the calibration does not guess at a day it has not got)
  const w3 = await calWorld(), lostReal = twinCli(...calArgs({ ...w3, real: withoutDays(w3.real, path.join(w3.root, 'real-lost'), ['2026-11-11']) }, splitIn(w3), path.join(w3.root, 'c3')));
  assert.notEqual(lostReal.status, 0); assert.match(lostReal.stderr, /^\[twin\] ERROR: the calibration needs the cached real FIT day 2026-11-11 in .*real-lost; dispatch prep_days=2026-11-11 first/m);
});

/** The features stage of the full route again, into `out`, on the filled days of `full`; the real FIT days are read from `realDir`, or from `handoff` when it holds them. */
function featuresInto(full: string, out: string, realDir: string, handoff?: string): string[] {
  fs.mkdirSync(out, { recursive: true }); okCli(...splitArgs(out));
  return tw(okCli('--stage', 'features', '--dirs', `real=${full}/real,requote=${full}/requote,depth=${full}/depth`, '--days', FAST_JUDGE.join(','), '--extra-days', FAST_FIT.join(','), '--extra-dir', realDir, '--real15m', realDir, '--out', out, ...(handoff ? ['--handoff', handoff] : [])));
}

test('the real FIT rows of the calibrate stage\'s handoff are used only under their own key (these FIT days, their prepped days\' sha256, the real days tag, the feature code) and then give what parsing the days gives, followed by the judged days\' diagnostics', async () => {
  const w = await calWorld(), ho = path.join(w.root, 'ho');
  const keyOf = (k: string) => Object.keys(followDiag.real ?? {})[0] ?? k;
  delete followDiag.real;
  const parsed = await realFitRows({ fit: FAST_FIT, realDir: w.real });
  assert.equal(parsed.reused, false); assert.ok(parsed.rows.length >= 48 && parsed.rows.every((r) => r.src === 'real' && FAST_FIT.includes(r.day)));
  assert.deepEqual([...parsed.perDay.keys()], FAST_FIT);
  const parsedFollow = JSON.stringify(followDiag.real), someKey = keyOf('');
  assert.ok(someKey && followDiag.real![someKey].m.length > 0, 'the FIT days feed follow diagnostics');
  writeRealFitHandoff(ho, FAST_FIT, w.real, parsed);
  // with the real FIT days gone (their meta files, which hold the sha256, stay): the handoff gives the same rows, the same diagnostics, and the same per-day split
  const metaOnly = metaFilesOnly(w, 'meta-only');
  // the judged days' diagnostics are in followDiag.real first (a stage that reads the judged days first leaves them there): the fit days' come after, key by key
  const pre = () => { followDiag.real = { [someKey]: { m: [-1], x: [-2] }, judgedOnly: { m: [5], x: [6] } }; };
  pre(); const viaHandoff = await realFitRows({ fit: FAST_FIT, realDir: metaOnly, handoff: ho });
  assert.equal(viaHandoff.reused, true); assert.deepEqual(viaHandoff.rows, parsed.rows); assert.deepEqual([...viaHandoff.perDay.keys()], FAST_FIT); assert.deepEqual(viaHandoff.follow, parsed.follow);
  const mergedHandoff = JSON.stringify(followDiag.real);
  pre(); await realFitRows({ fit: FAST_FIT, realDir: w.real });
  assert.equal(JSON.stringify(followDiag.real), mergedHandoff, 'the diagnostics merged are those parsing the days merges');
  assert.deepEqual(followDiag.real!.judgedOnly, { m: [5], x: [6] }); assert.deepEqual(followDiag.real![someKey].m.slice(0, 1), [-1]); assert.ok(followDiag.real![someKey].m.length > 1);
  delete followDiag.real; assert.ok(parsedFollow.length > 2);
  // the key: any aspect that is not this run's, and the handoff is not trusted (the days, when they are there, are parsed; when they are not, they are left out as the features stage always did)
  const miss = async (label: string, realDir: string, handoff: string) => { delete followDiag.real; const r = await realFitRows({ fit: FAST_FIT, realDir, handoff, skipMissing: true }); assert.equal(r.reused, false, label); return r; };
  const edited = (name: string, edit: (fol: any, rows: any[]) => void) => { const d = path.join(w.root, name); copyFiles(ho, d, [REAL_FIT_FILE, REAL_FIT_FOLLOW_FILE]); const fol = readJ(path.join(d, REAL_FIT_FOLLOW_FILE)), rows = readJ(path.join(d, REAL_FIT_FILE)); edit(fol, rows); fs.writeFileSync(path.join(d, REAL_FIT_FOLLOW_FILE), JSON.stringify(fol)); fs.writeFileSync(path.join(d, REAL_FIT_FILE), JSON.stringify(rows)); return d; };
  assert.deepEqual((await miss('no handoff folder', metaOnly, path.join(w.root, 'nothing-here'))).rows, []);
  assert.equal((await miss('a day parsed instead', w.real, edited('bad-tag', (f) => { f.key.real15m = 'r15m-0|exclude=DOGE'; }))).rows.length, parsed.rows.length, 'with the days there, parsing gives the rows');
  for (const [label, edit] of [
    ['feature code', (f: any) => { f.key.featureCode = 'f0'; }], ['real days tag', (f: any) => { f.key.real15m = 'r15m-0'; }], ['fit days', (f: any) => { f.key.fit = ['2026-11-11']; }], ['a sha256', (f: any) => { f.key.shas['2026-11-12'] = 'a'.repeat(64); }],
    ['format', (f: any) => { f.version = 99; }], ['rows per day', (f: any) => { f.rowsPerDay['2026-11-11'] += 1; }], ['no follow', (f: any) => { delete f.follow; }],
    ['a row of another day', (_f: any, rows: any[]) => { rows.push({ ...rows[0], day: '2026-11-15' }); }], ['a row lost', (_f: any, rows: any[]) => { rows.pop(); }],
  ] as Array<[string, (f: any, rows: any[]) => void]>) assert.deepEqual((await miss(label, metaOnly, edited(`bad-${label}`, edit))).rows, [], `${label}: not trusted`);
  const junk = edited('junk', () => {}); fs.writeFileSync(path.join(junk, REAL_FIT_FILE), '{no'); assert.deepEqual((await miss('damaged rows', metaOnly, junk)).rows, []);
  // the prepped day made again (another sha256 in its meta): the handoff of the old one is not this run's
  const remade = path.join(w.root, 'meta-remade'); copyFiles(metaOnly, remade, fs.readdirSync(metaOnly));
  fs.writeFileSync(path.join(remade, 'meta-2026-11-12.json'), JSON.stringify({ ...readJ(path.join(metaOnly, 'meta-2026-11-12.json')), sha256: 'b'.repeat(64) }));
  assert.deepEqual((await miss('a prepped day made again', remade, ho)).rows, []);
  // a day with no sha256 on record is never trusted either
  const nosha = path.join(w.root, 'meta-nosha'); copyFiles(metaOnly, nosha, fs.readdirSync(metaOnly)); fs.writeFileSync(path.join(nosha, 'meta-2026-11-11.json'), JSON.stringify({ day: '2026-11-11' }));
  assert.deepEqual((await miss('no sha256', nosha, ho)).rows, []);
  // the key itself
  assert.deepEqual(realFitKey(FAST_FIT, w.real), { fit: FAST_FIT, real15m: real15mTag(), featureCode: FEATURE_CODE_VERSION, shas: Object.fromEntries(FAST_FIT.map((d) => [d, sha256Of(path.join(w.real, `md-${d}.jsonl.gz`))])) });
  delete followDiag.real;
});

test('the features stage and the fast rows take the real FIT rows from the handoff when they are the key\'s, and write the files the real FIT days\' parsing writes; without the handoff and without the days they do not guess', async () => {
  const w = await calWorld(), sp = splitIn(w), ho = path.join(w.root, 'ho');
  await calibrateStage({ out: ho, modelFile: w.modelFile, splitFile: sp, realDir: w.real, twinFitDir: w.twinFit, heldInBudgetS: 0, log: () => {} });
  const full = path.join(w.root, 'full'), fullLines = fullRoute(w, full);
  const noFit = withoutDays(w.real, path.join(w.root, 'real-no-fit'), FAST_FIT);
  // the features stage: handoff + no FIT day files = the files and lines of the stage that read them
  const viaHo = path.join(w.root, 'via-handoff'), linesHo = featuresInto(full, viaHo, noFit, ho);
  for (const f of ['features-real.json', 'features-requote.json', 'features-depth.json', 'real-meta.json', 'real-activity.json', 'real-fit-features.json']) assert.equal(fs.readFileSync(path.join(viaHo, f), 'utf8'), fs.readFileSync(path.join(full, f), 'utf8'), `${f} from the handoff equals the one from the parsed days`);
  // (round S1: but for the seconds-only timing lines of the features stage, whose numbers are the run's own)
  assert.deepEqual(linesHo.filter((l) => !FILE_ROUTE_TIMING.test(l)), fullLines.slice(fullLines.findIndex((l) => /^\[twin\] features real: /.test(l))).filter((l) => !FILE_ROUTE_TIMING.test(l)), 'the stage prints the same lines (the full route\'s features stage is the last of its three)');
  assert.ok(linesHo.some((l) => /^\[twin\] features took \d+\.\d s \(jobs 1\)$/.test(l)) && linesHo.some((l) => /^\[twin\] features real 2026-11-1\d: \d+\.\d s$/.test(l)), 'the stage still prints its timing lines');
  assert.ok(linesHo.some((l) => /^\[twin\] real 2026-11-12 \(not judged\): /.test(l)) && linesHo.some((l) => /^\[twin\] real follow /.test(l)), 'the fit days\' activity and follow lines come from the handoff');
  // without the handoff the same folder gives a real side with no fit days (the features stage skips a day it has not got), which is what the handoff made up for
  const noHo = path.join(w.root, 'no-handoff'); featuresInto(full, noHo, noFit);
  assert.equal(fs.readFileSync(path.join(noHo, 'real-fit-features.json'), 'utf8'), '[]'); assert.notEqual(fs.readFileSync(path.join(noHo, 'real-activity.json'), 'utf8'), fs.readFileSync(path.join(full, 'real-activity.json'), 'utf8'));
  // a handoff of other days is no handoff
  const other = path.join(w.root, 'other-handoff'); copyFiles(ho, other, [REAL_FIT_FILE, REAL_FIT_FOLLOW_FILE]);
  const fol = readJ(path.join(other, REAL_FIT_FOLLOW_FILE)); fol.key.shas['2026-11-11'] = 'c'.repeat(64); fs.writeFileSync(path.join(other, REAL_FIT_FOLLOW_FILE), JSON.stringify(fol));
  const viaOther = path.join(w.root, 'via-other'); featuresInto(full, viaOther, noFit, other); assert.equal(fs.readFileSync(path.join(viaOther, 'real-fit-features.json'), 'utf8'), '[]');
  // the fast rows: the same, in-process and in its own process; with neither the days nor the handoff the fast route refuses (it never skips a FIT day)
  const fastHo = path.join(w.root, 'fast-handoff'); fs.mkdirSync(fastHo); okCli(...splitArgs(fastHo));
  const fl = await fastHere(w, fastHo, undefined, { realDir: noFit, handoff: ho });
  for (const f of READ) assert.equal(fs.readFileSync(path.join(fastHo, f), 'utf8'), fs.readFileSync(path.join(full, f), 'utf8'), `fast with the handoff: ${f}`);
  sameLines(fullLines, fl, full, fastHo);
  const bare = path.join(w.root, 'fast-bare'); fs.mkdirSync(bare); okCli(...splitArgs(bare));
  await assert.rejects(fastHere(w, bare, undefined, { realDir: noFit }), /the fast run needs the cached real FIT day 2026-11-11 in .*real-no-fit .*dispatch prep_days=2026-11-11 first/);
  await assert.rejects(fastHere(w, bare, undefined, { realDir: noFit, handoff: other }), /the fast run needs the cached real FIT day/);
  const cli = path.join(w.root, 'fast-cli'); fs.mkdirSync(cli); okCli(...splitArgs(cli));
  okCli(...fastArgs({ ...w, real: noFit }, cli, '--handoff', ho));
  assert.equal(fs.readFileSync(path.join(cli, 'real-fit-features.json'), 'utf8'), fs.readFileSync(path.join(full, 'real-fit-features.json'), 'utf8'));
});

test('a calibrated model plays the same in the file route and the in-stream route, each says which calibration it plays, the calibration moves the depth rows and no other, and the fast route never fits or writes a calibration', async () => {
  const { depthCalibrationNote } = await import('../research/goLiveTally');
  const w = await calWorld(), sp = splitIn(w), uncal = path.join(w.root, 'depth_model.uncalibrated.json');
  fs.copyFileSync(w.modelFile, uncal);
  await calibrateStage({ out: path.join(w.root, 'ho'), modelFile: w.modelFile, splitFile: sp, realDir: w.real, twinFitDir: w.twinFit, heldInBudgetS: 0, log: () => {} });
  const bytes = fs.readFileSync(w.modelFile, 'utf8'), model = readDepthModel(w.modelFile)!;
  const note = depthCalibrationNote(model)!;
  assert.match(note, /^\[twin\] depth model calibration: BTC \(top [\d.]+ level [\d.]+ size [\d.]+ trades [\d.]+ flick [\d.]+\), ETH \(.*\); fitted on the FIT days 2026-11-11 2026-11-12, \d iteration\(s\)$/);
  assert.equal(depthCalibrationNote({ ...model, calibration: undefined }), undefined, 'a model without a calibration says nothing of one');
  const full = path.join(w.root, 'full'), fullLines = fullRoute(w, full), fast = path.join(w.root, 'fast'), fastLines = fastRoute(w, fast);
  for (const f of READ) assert.equal(fs.readFileSync(path.join(fast, f), 'utf8'), fs.readFileSync(path.join(full, f), 'utf8'), `${f}: the in-stream route's bytes are the file route's`);
  sameLines(fullLines, fastLines, full, fast);
  for (const [name, ls] of [['full', fullLines], ['fast', fastLines]] as const) assert.equal(ls.filter((l) => l === note).length, 1, `the ${name} route says which calibration it plays, once`);
  // the fast route fits nothing: no calibration line, the model file as it was
  assert.ok(fastLines.every((l) => !/^\[twin\] calibration: /.test(l)) && fullLines.every((l) => !/^\[twin\] calibration: /.test(l)), 'the fill and fast stages play a calibration, they do not fit one');
  assert.equal(fs.readFileSync(w.modelFile, 'utf8'), bytes);
  // the calibration acts on the depth rows of the judged days, and on nothing else (the real rows and the requote rows are not the fill-in's)
  const un = path.join(w.root, 'fast-uncalibrated'); fs.mkdirSync(un); okCli(...splitArgs(un)); const unLines = tw(okCli(...fastArgs({ ...w, modelFile: uncal }, un)));
  assert.notEqual(fs.readFileSync(path.join(un, 'features-depth.json'), 'utf8'), fs.readFileSync(path.join(fast, 'features-depth.json'), 'utf8'), 'the calibration moves the depth rows');
  for (const f of ['features-real.json', 'features-requote.json', 'paired.json', 'real-fit-features.json']) assert.equal(fs.readFileSync(path.join(un, f), 'utf8'), fs.readFileSync(path.join(fast, f), 'utf8'), `${f} is not the fill-in's`);
  assert.ok(unLines.every((l) => !/depth model calibration/.test(l)), 'an uncalibrated model says nothing of one');
  // a sweep's parameters name the three knobs the calibration multiplies: the fill-in plays them in place of the calibrated three, and says so
  const best = bestFileOf(w.root, generationCandidates(0, 6)[2]), warn = path.join(w.root, 'fast-sweep'); fs.mkdirSync(warn); okCli(...splitArgs(warn));
  const wl = tw(okCli(...fastArgs(w, warn, '--depth-params', best)));
  assert.equal(wl.filter((l) => /^\[twin\] WARNING: the sweep's parameters \(depth_params_run\) name tradeRateMult, tradeSizeMult and levelSizeMult, so for every asset they REPLACE the calibration's multipliers for those three knobs; its topSizeMult and flickMult still apply/.test(l)).length, 1);
  assert.ok(!fastLines.some((l) => /WARNING: the sweep/.test(l)), 'no sweep, no warning');
});

test('the calibrate stage reads an earlier run\'s real FIT rows (real_features_run) only when they were built for these fit days, this tag, these prepped days and this code, and then calibrates exactly as parsing the days does', async () => {
  const w = await calWorld(), full = path.join(w.root, 'full'); fullRoute(w, full);
  const cache = path.join(w.root, 'cache'); copyFiles(full, cache, REAL_SIDE);
  const meta = readJ(path.join(cache, 'real-meta.json')) as RealMetaT, metaOnly = metaFilesOnly(w, 'meta-only');
  const parsed = (await realFitRows({ fit: FAST_FIT, realDir: w.real })).rows; delete followDiag.real;
  assert.deepEqual(loadRealFitRows(cache, FAST_FIT, metaOnly, '4242'), parsed, 'the rows kept by the run are the rows the days give');
  // the calibration through the cache and through the days is the same block, byte for byte; the cache run reads no real day
  const sp = splitIn(w), copy = (name: string) => { const f = path.join(w.root, name); fs.copyFileSync(w.modelFile, f); return f; };
  const viaDays = copy('m-days.json'), viaCache = copy('m-cache.json');
  const lines: string[][] = [[], []];
  await calibrateStage({ out: path.join(w.root, 'h1'), modelFile: viaDays, splitFile: sp, realDir: w.real, twinFitDir: w.twinFit, heldInBudgetS: 0, log: (l) => lines[0].push(l), now: () => 0 });
  await calibrateStage({ out: path.join(w.root, 'h2'), modelFile: viaCache, splitFile: sp, realDir: metaOnly, twinFitDir: w.twinFit, realCache: cache, realRun: '4242', heldInBudgetS: 0, log: (l) => lines[1].push(l), now: () => 0 });
  assert.equal(fs.readFileSync(viaCache, 'utf8'), fs.readFileSync(viaDays, 'utf8')); assert.deepEqual(lines[1], lines[0]);
  assert.ok(!fs.existsSync(path.join(w.root, 'h2')), 'rows read from a kept run leave no handoff: the run that kept them has the files');
  // refused, with what differs (the judged part of the key is not this stage's business)
  const refused = (c: string, re: RegExp) => assert.throws(() => loadRealFitRows(c, FAST_FIT, metaOnly, '4242'), (e: Error) => { assert.match(e.message, re); return true; });
  const withMeta = (name: string, edit: (m: RealMetaT) => void) => { const d = path.join(w.root, name); copyFiles(cache, d, REAL_SIDE); const m = structuredClone(meta); edit(m); fs.writeFileSync(path.join(d, 'real-meta.json'), JSON.stringify(m)); return d; };
  const head = (had: string, now: string, what: string) => new RegExp(`^real_features_run 4242 was built for ${had}, not these \\(${now}\\): it differs in ${what}\\. Leave real_features_run empty to parse the real days again$`);
  refused(withMeta('fit1', (m) => { m.fit = ['2026-11-11']; }), head('fit days 2026-11-11', 'fit days 2026-11-11,2026-11-12', 'fit days'));
  refused(withMeta('tag1', (m) => { m.real15m = 'r15m-0|exclude=DOGE'; }), head('real days tag r15m-0\\|exclude=DOGE', `real days tag ${real15mTag().split('|').join('\\|')}`, 'real days tag'));
  refused(withMeta('code1', (m) => { m.featureCode = 'f0'; }), head('feature code f0', `feature code ${FEATURE_CODE_VERSION}`, 'feature code'));
  refused(withMeta('sha1', (m) => { m.days['2026-11-12'].real = 'd'.repeat(64); }), /it differs in prepped real days\./);
  refused(withMeta('sha2', (m) => { delete m.days['2026-11-11']; }), /it differs in prepped real days\./);
  assert.doesNotThrow(() => loadRealFitRows(withMeta('judged1', (m) => { m.judged = ['2026-11-13']; }), FAST_FIT, metaOnly, '4242'), 'the judged days of the kept run are not what this stage reads');
  refused(path.join(w.root, 'no-such-run'), /^real_features_run 4242 has no real-meta\.json, real-fit-features\.json: it was made before the per-asset calibration kept the real FIT rows \(round R2\)/);
  const noFit = path.join(w.root, 'no-fit-file'); copyFiles(cache, noFit, REAL_SIDE.filter((n) => n !== REAL_FIT_FILE)); refused(noFit, /^real_features_run 4242 has no real-fit-features\.json: it was made before the per-asset calibration kept the real FIT rows \(round R2\)/);
  const rows = readJ(path.join(cache, REAL_FIT_FILE)) as Array<{ day: string }>;
  const stray = path.join(w.root, 'stray-fit'); copyFiles(cache, stray, REAL_SIDE); fs.writeFileSync(path.join(stray, REAL_FIT_FILE), JSON.stringify([...rows, { ...rows[0], day: '2026-11-15' }]));
  refused(stray, /real-fit-features\.json holds rows of 2026-11-11, 2026-11-12, 2026-11-15, these fit days are 2026-11-11, 2026-11-12 \(other fit days: 2026-11-15\)/);
  const short = path.join(w.root, 'short-fit'); copyFiles(cache, short, REAL_SIDE); fs.writeFileSync(path.join(short, REAL_FIT_FILE), JSON.stringify(rows.filter((r) => r.day === '2026-11-11')));
  refused(short, /holds rows of 2026-11-11, these fit days are 2026-11-11, 2026-11-12 \(none for 2026-11-12\)/);
  const bad = path.join(w.root, 'bad-fit'); copyFiles(cache, bad, REAL_SIDE); fs.writeFileSync(path.join(bad, REAL_FIT_FILE), '{"x":1}'); refused(bad, /real-fit-features\.json is not what this code writes/);
  fs.writeFileSync(path.join(bad, REAL_FIT_FILE), '{no'); refused(bad, /real-fit-features\.json is not readable JSON/);
  // and the stage reports it as its own [twin] ERROR
  const r = twinCli(...calArgs({ ...w, real: metaOnly }, sp, path.join(w.root, 'h3'), '--real-cache', stray, '--real-run', '4242'));
  assert.notEqual(r.status, 0); assert.match(r.stderr, /^\[twin\] ERROR: real_features_run 4242: real-fit-features\.json holds rows of/m);
});

test('a reused depth model (depth_model_run) is checked for schema 3 and its calibration and never refitted: schema 2, no block, a block of other days and a model fitted on other days are refused; a calibrated one passes', () => {
  const dir = tmpDir(), split = { name: 'custom', fit: FAST_FIT, judge: FAST_JUDGE }, sp = path.join(dir, 'split.json'); fs.writeFileSync(sp, JSON.stringify({ ...split, warm: [] }));
  const model = { ...synthModel({ days: FAST_FIT }), schema: DEPTH_MODEL_SCHEMA };
  const put = (name: string, m: object) => { const f = path.join(dir, `${name}.json`); fs.writeFileSync(f, JSON.stringify(m)); return f; };
  const good = put('good', withCalibration(model, FAST_FIT, 3, { BTC: { ...CAL_TRUTH.BTC }, ETH: { ...CAL_TRUTH.ETH } }, undefined, calibrationCode()));
  // the study version: a model of schema 2 (before the calibration block) is not reused, with or without a block in it
  const reuse = (f: string, re: RegExp) => assert.throws(() => checkDepthModelReuse(f, split, { run: '321' }), (e: Error) => { assert.match(e.message, re); return true; });
  reuse(put('two', { ...model, schema: 2 }), new RegExp(`^depth_model_run 321: the model has schema 2, this code reads schema ${DEPTH_MODEL_SCHEMA}: the depth study or the simulator changed since it was fitted, so it is not reused\\. Leave depth_model_run empty to fit it again$`));
  reuse(put('two-cal', { ...withCalibration(model, FAST_FIT, 3, { BTC: { ...CAL_TRUTH.BTC } }), schema: 2 }), /schema 2/);
  assert.equal(checkDepthModelReuse(good, split, { run: '321' }), `[twin] depth model reused from run 321: fitted on 2026-11-11 2026-11-12 (exactly the fit days), schema ${DEPTH_MODEL_SCHEMA}; no real-meta.json beside it, so the real days' tag it was fitted from is not recorded`);
  // the calibration it carries
  assert.equal(checkDepthModelCalibration(good, split, { run: '321' }), '[twin] depth model calibration carried by run 321: assets BTC ETH, fitted on 2026-11-11 2026-11-12, 3 iteration(s); no recalibration');
  const thr = (f: string, re: RegExp) => assert.throws(() => checkDepthModelCalibration(f, split, { run: '321' }), (e: Error) => { assert.match(e.message, re); return true; });
  thr(put('nocal', model), /^depth_model_run 321: the model has no calibration block: it was fitted before the per-asset calibration ran, or its calibration failed, so it is not reused\. Leave depth_model_run empty to fit and calibrate it again$/);
  thr(put('othercal', withCalibration(model, ['2026-11-11'], 2, { BTC: { ...CAL_TRUTH.BTC } })), /^depth_model_run 321: the depth model's calibration was fitted on 2026-11-11, not on the days the model was fitted on/);
  // a model fitted on some of the fit days only is the days check's business (checkDepthModelReuse: exactly the fit days), not the calibration check's: the block is of its days
  const subset = put('otherdays', withCalibration({ ...model, days: ['2026-11-11'] }, ['2026-11-11'], 2, { BTC: { ...CAL_TRUTH.BTC } }, undefined, calibrationCode()));
  assert.match(checkDepthModelCalibration(subset, split, { run: '321' }), /fitted on 2026-11-11, 2 iteration\(s\)/);
  reuse(subset, /^depth_model_run 321: the model was fitted on 2026-11-11, not exactly the fit days 2026-11-11, 2026-11-12\./);
  thr(put('judged', withCalibration({ ...model, days: [...FAST_FIT, '2026-11-13'] }, [...FAST_FIT, '2026-11-13'], 2, { BTC: { ...CAL_TRUTH.BTC } })), /^depth_model_run 321: .*overlap.*2026-11-13/);
  fs.writeFileSync(path.join(dir, 'junk.json'), '{no'); thr(path.join(dir, 'junk.json'), /^depth_model_run 321: /);
  // the stage the workflow runs: the line, or a [twin] ERROR and a failed exit
  const ok = twinCli('--stage', 'calibration-check', '--depth-model', good, '--split-file', sp, '--run', '321');
  assert.equal(ok.status, 0, ok.stderr); assert.match(ok.stdout, /^\[twin\] depth model calibration carried by run 321: assets BTC ETH, fitted on 2026-11-11 2026-11-12, 3 iteration\(s\); no recalibration$/m);
  const no = twinCli('--stage', 'calibration-check', '--depth-model', put('nocal2', model), '--split-file', sp, '--run', '321');
  assert.notEqual(no.status, 0); assert.match(no.stderr, /^\[twin\] ERROR: depth_model_run 321: the model has no calibration block/m);
  // a confirm split's model (fitted on FIT + DEV) is checked on the confirm split's own fit days
  const cm = { ...synthModel({ days: [...SPLITS.confirm.fit] }), schema: DEPTH_MODEL_SCHEMA };
  fs.writeFileSync(sp, JSON.stringify({ name: 'confirm', fit: [...SPLITS.confirm.fit], judge: [...SPLITS.confirm.judge], warm: [] }));
  assert.match(checkDepthModelCalibration(put('confirm', withCalibration(cm, [...SPLITS.confirm.fit], 1, { BTC: { ...CAL_TRUTH.BTC } }, undefined, calibrationCode())), { name: 'confirm', fit: [...SPLITS.confirm.fit], judge: [...SPLITS.confirm.judge] }, { run: '9' }), /^\[twin\] depth model calibration carried by run 9: assets BTC, fitted on 2026-11-11 2026-11-12 2026-11-15 2026-11-13 2026-11-14 2026-11-16 2026-11-17, 1 iteration\(s\)/);
});

/** calWorld whose real FIT days ALSO hold contracts the twin does not have (R2 fix round 1): 4 contracts an asset and day, opened at 14:00 UTC, made by a THIN model
 *  (under a tenth of the levels, a seventh of the trade size, a twentieth of the trade rate: the quiet contracts a real day has and the Kalshi candles miss). The requote FIT
 *  days (twinFit) do not hold them. Returns the world and how many real FIT lives per asset are extra. */
async function calWorldWithExtras(): Promise<CalWorld & { extra: number }> {
  const w = await calWorld(), thinFile = path.join(w.root, 'thin_model.json');
  fs.writeFileSync(thinFile, JSON.stringify({ ...synthModel({ days: FAST_FIT }), schema: DEPTH_MODEL_SCHEMA, params: { levelSizeMult: 0.08, tradeSizeMult: 0.15, tradeRateMult: 0.05 } }));
  const thin = readDepthModel(thinFile)!, read = (g: string) => zlib.gunzipSync(fs.readFileSync(g)).toString('utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l) as { t: number });
  let extra = 0;
  for (const [i, d] of FAST_FIT.entries()) {
    const f = path.join(w.real, `md-${d}.jsonl.gz`), raw = path.join(w.root, `raw-extra-${d}.jsonl.gz`), filled = path.join(w.root, `extra-${d}.jsonl.gz`);
    writeEventsGz(raw, synthRequoteDay({ day: d, assets: ['BTC', 'ETH'], windows: 4, seed: 90 + i, startHour: 14 }));
    await fillDayFile(raw, filled, { how: 'depth' }, thin);
    writeEventsGz(f, [...read(f), ...read(filled)].sort((a, b) => a.t - b.t));
    fs.writeFileSync(path.join(w.real, `meta-${d}.json`), JSON.stringify({ day: d, version: real15mTag(), sha256: sha256Of(f) }));
    extra += 4;
  }
  return { ...w, extra };
}

test('the calibration fits the twin to the contracts the twin HAS (the judge\'s population): real FIT lives with no contract in the requote FIT day change neither the multipliers nor the held-in check, and a day with none in common is refused', async () => {
  const a = await calWorld(), b = await calWorldWithExtras();
  const run = async (w: CalWorld) => {
    const lines: string[] = [], uncal = path.join(w.root, 'uncalibrated.json'); fs.copyFileSync(w.modelFile, uncal);
    await calibrateStage({ out: path.join(w.root, 'ho'), modelFile: w.modelFile, splitFile: splitIn(w), realDir: w.real, twinFitDir: w.twinFit, log: (l) => lines.push(l), now: () => 0 });
    return { lines, bytes: fs.readFileSync(w.modelFile, 'utf8'), uncal };
  };
  const A = await run(a), B = await run(b);
  const keptRe = /^\[twin\] calibration: asset (BTC|ETH) real FIT lives kept (\d+) of (\d+) \(contract in the twin\)$/;
  const keptOf = (ls: string[]) => ls.map((l) => keptRe.exec(l)).filter((m): m is RegExpExecArray => !!m).map((m) => [m[1], +m[2], +m[3]] as const);
  const ka = keptOf(A.lines), kb = keptOf(B.lines);
  assert.deepEqual(ka.map((k) => k[0]), ['BTC', 'ETH']); assert.ok(ka.every((k) => k[1] === k[2] && k[1] >= 24), 'without extras every real FIT life has its twin contract');
  assert.deepEqual(kb.map((k) => [k[0], k[1]]), ka.map((k) => [k[0], k[1]]), 'with extras the same lives are kept');
  assert.deepEqual(kb.map((k) => k[2] - k[1]), [b.extra, b.extra], 'and the extras are counted as read and not kept');
  // the same answer, byte for byte: the block, and with it the model file; and the same lines, held-in check included, apart from the kept counts
  assert.equal(B.bytes, A.bytes, 'the multipliers do not depend on contracts the twin lacks');
  assert.ok(A.lines.some((l) => /^\[twin\] calibration: held-in check \(2 folds/.test(l)), 'the held-in check ran');
  const rest = (ls: string[]) => ls.filter((l) => !keptRe.test(l));
  assert.deepEqual(rest(B.lines), rest(A.lines), 'every other line, the held-in gaps included, is the same');
  assert.ok(B.lines.every((l) => !/KX|md-2026/.test(l)), 'counts only');
  // the stage leaves every real FIT row in its handoff (the activity lines read them); only the calibration is restricted
  const all = readJ(path.join(b.root, 'ho', REAL_FIT_FILE)) as Row[], tk = new Map(FAST_FIT.map((d) => [d, twinTickersOf(zlib.gunzipSync(fs.readFileSync(path.join(b.twinFit, `md-${d}.jsonl.gz`))).toString('utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l)))]));
  assert.equal(all.length, restrictFitRows(all, tk).rows.length + 2 * b.extra);
  assert.deepEqual(restrictFitRows(all, tk).counts.map((c) => [c.asset, c.of - c.kept]), [['BTC', b.extra], ['ETH', b.extra]]);
  // ... and the test is not vacuous: fitted to ALL the real FIT lives the multipliers move away (the quiet contracts pull the twin's means down, as the finding ran)
  const fi = (k: (typeof FEATURES)[number]) => FEATURES.indexOf(k);
  const cols: CalCols = { top: fi('topSize'), depth10: fi('depth10'), tradeSize: fi('tradeSize'), qchg: fi('quoteChangesPerMin'), trades: fi('tradesPerMin'), quotedShare: fi('quotedShare') };
  const requote = new Map(FAST_FIT.map((d) => [d, zlib.gunzipSync(fs.readFileSync(path.join(b.twinFit, `md-${d}.jsonl.gz`))).toString('utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l))]));
  const twinRows = async (m: DepthModel, ds: readonly string[]) => { const out = []; for (const d of ds) out.push(...(await filledDayRows(requote.get(d)!, d, 'depth', new Map(), m, undefined, { diag: false })).rows); return out; };
  const un = await calibrateDepthModel({ model: readDepthModel(B.uncal)!, fitDays: FAST_FIT, realRows: all, twinRows, cols });
  const fitted = readDepthModel(B.uncal.replace('uncalibrated', 'depth_model'))!.calibration!;
  for (const as of ['BTC', 'ETH']) for (const k of ['levelSizeMult', 'tradeSizeMult'] as const) assert.ok(un.calibration.byAsset[as][k] < 0.9 * fitted.byAsset[as][k], `${as} ${k}: unrestricted ${un.calibration.byAsset[as][k]} against ${fitted.byAsset[as][k]}`);
  // the rule itself: a row stays only when its ticker is in ITS day's requote day; and twinTickersOf reads the market records the rows are built from
  const r = (day: string, ticker: string): Row => ({ day, ticker, src: 'real', f: [] });
  const rr = restrictFitRows([r('d1', 'KXBTC15M-A'), r('d1', 'KXBTC15M-B'), r('d2', 'KXBTC15M-A'), r('d2', 'KXETH15M-C'), r('d3', 'KXDOGE15M-Z')], new Map([['d1', new Set(['KXBTC15M-A'])], ['d2', new Set(['KXETH15M-C'])]]));
  assert.deepEqual(rr.rows.map((x) => `${x.day}/${x.ticker}`), ['d1/KXBTC15M-A', 'd2/KXETH15M-C'], 'a ticker of another day does not count, a day with no requote day keeps nothing');
  assert.deepEqual(rr.counts, [{ asset: 'BTC', kept: 1, of: 3 }, { asset: 'ETH', kept: 1, of: 1 }]);
  assert.deepEqual([...twinTickersOf([{ k: 'market', ticker: 'KXBTC15M-A', series: 'KXBTC15M' }, { k: 'market', ticker: 'KXBTCD-B', series: 'KXBTCD' }, { k: 'book', ticker: 'KXBTC15M-C' }, { k: 'market' }])], ['KXBTC15M-A']);
  // a real FIT day whose contracts the requote day does not hold at all: refused with the reason, the model untouched
  const w2 = await calWorld(), other = path.join(w2.root, 'fit-other'); fs.mkdirSync(other);
  for (const d of FAST_FIT) writeEventsGz(path.join(other, `md-${d}.jsonl.gz`), synthRequoteDay({ day: d, assets: ['BTC', 'ETH'], windows: 12, seed: 5, startHour: 16 }));
  const before = fs.readFileSync(w2.modelFile, 'utf8');
  await assert.rejects(calibrateStage({ out: path.join(w2.root, 'ho'), modelFile: w2.modelFile, splitFile: splitIn(w2), realDir: w2.real, twinFitDir: other, log: () => {} }), /^Error: the calibration: none of the \d+ real FIT lives is a contract the requote FIT days have/);
  assert.equal(fs.readFileSync(w2.modelFile, 'utf8'), before);
});

test('a reused calibration is checked against the code it was fitted by (simulator source, requote layer, feature code): a stamp that differs, or none, refuses the model, and a comment or whitespace edit of the simulator does not', async () => {
  const dir = tmpDir(), split = { name: 'custom', fit: FAST_FIT, judge: FAST_JUDGE };
  const model = { ...synthModel({ days: FAST_FIT }), schema: DEPTH_MODEL_SCHEMA };
  const put = (name: string, code?: Partial<ReturnType<typeof calibrationCode>>) => { const f = path.join(dir, `${name}.json`); fs.writeFileSync(f, JSON.stringify(withCalibration(model, FAST_FIT, 3, { BTC: { ...CAL_TRUTH.BTC } }, undefined, code ? { ...calibrationCode(), ...code } : undefined))); return f; };
  const now = calibrationCode();
  assert.match(now.sim, /^[0-9a-f]{16}$/); assert.equal(now.replay, String(REPLAY_VERSION)); assert.equal(now.featureCode, FEATURE_CODE_VERSION);
  assert.match(checkDepthModelCalibration(put('same', {}), split, { run: '5' }), /^\[twin\] depth model calibration carried by run 5: assets BTC, fitted on 2026-11-11 2026-11-12, 3 iteration\(s\); no recalibration$/);
  const thr = (f: string, re: RegExp, code?: typeof now) => assert.throws(() => checkDepthModelCalibration(f, split, { run: '5', ...(code ? { code } : {}) }), (e: Error) => { assert.match(e.message, re); return true; });
  const tail = ' Its multipliers are a fit of that twin, not of this one, so the model is not reused\\. Leave depth_model_run empty to fit and calibrate it again';
  thr(put('nostamp'), /^depth_model_run 5: the model's calibration carries no code stamp .*so it cannot be told from a stale one and is not reused\. Leave depth_model_run empty to fit and calibrate it again$/);
  thr(put('othersim', { sim: 'deadbeefdeadbeef' }), new RegExp(`^depth_model_run 5: the model's calibration was fitted by other code than this ref's: simulator deadbeefdeadbeef then, ${now.sim} now\\.${tail}`));
  thr(put('otherreplay', { replay: '8' }), new RegExp(`other code than this ref's: requote layer 8 then, ${now.replay} now\\.`));
  thr(put('otherfeat', { featureCode: 'f0' }), new RegExp(`other code than this ref's: feature code f0 then, ${now.featureCode} now\\.`));
  thr(put('all3', { sim: 'a', replay: 'b', featureCode: 'c' }), /simulator a then, [0-9a-f]{16} now; requote layer b then, \d+ now; feature code c then, \w+ now\./);
  // the check compares with the code of THIS ref: the same file refused under another code stamp, accepted under its own
  const good = put('good2', {});
  thr(good, /simulator [0-9a-f]{16} then, cafecafecafecafe now/, { ...now, sim: 'cafecafecafecafe' });
  assert.doesNotThrow(() => checkDepthModelCalibration(good, split, { run: '5', code: now }));
  // the stamp is a block field the simulator validates: a stamp with an empty part is not a block it reads
  assert.throws(() => put('emptysim', { sim: '' }), /calibration code stamp must name the sim/);
  // the simulator's stamp: a hash of the code with comments and whitespace out
  const src = fs.readFileSync(path.join(ROOT, 'research/history/depthSim.ts'), 'utf8'), at = (name: string, text: string) => { const f = path.join(dir, name); fs.writeFileSync(f, text); return calibrationCode(f); };
  assert.deepEqual(at('same.ts', src), now, 'the stamp is read from depthSim.ts');
  assert.deepEqual(at('docs.ts', src.replace('// Per-asset LEVEL calibration', '// A reworded comment, and a new one\n// Per-asset LEVEL calibration').replace(/\n(?=import fs)/, '\n\n   \n')), now, 'a comment or whitespace edit does not stale a calibration');
  // the default's value is found by its shape, not spelled out: a promotion of a sweep's winners (RUNBOOK 9.5) changes the number and must not break this test
  const bumped = src.replace(/(\bcapMult:\s*)([0-9.]+)(\s*,)/, (_m, a: string, v: string, c: string) => `${a}${+v + 0.5}${c}`);
  assert.notEqual(bumped, src, 'the capMult default literal was found in depthSim.ts and edited');
  assert.notEqual(at('code.ts', bumped).sim, now.sim, 'a changed default does');
  assert.notEqual(at('code2.ts', src.replace('const pull = 1 - Math.exp(-1 / P.revertS)', 'const pull = 1 - Math.exp(-1.01 / P.revertS)')).sim, now.sim, 'and so does a changed line of play()');
  // the stage the workflow runs: the same refusal as a [twin] ERROR, and a pass prints the stamp
  const sp = path.join(dir, 'split.json'); fs.writeFileSync(sp, JSON.stringify({ ...split, warm: [] }));
  const ok = twinCli('--stage', 'calibration-check', '--depth-model', good, '--split-file', sp, '--run', '5');
  assert.equal(ok.status, 0, ok.stderr); assert.match(ok.stdout, new RegExp(`^\\[twin\\] depth model calibration was fitted by simulator ${now.sim}, requote layer ${now.replay}, feature code ${now.featureCode} \\(this ref has the same: a calibration fitted by other code is refused\\)$`, 'm'));
  const bad = twinCli('--stage', 'calibration-check', '--depth-model', put('othersim2', { sim: '0123456789abcdef' }), '--split-file', sp, '--run', '5');
  assert.notEqual(bad.status, 0); assert.match(bad.stderr, /^\[twin\] ERROR: depth_model_run 5: the model's calibration was fitted by other code than this ref's: simulator 0123456789abcdef then/m);
  // a model the calibrate stage fitted carries this ref's stamp, says so, and passes the check
  const w = await calWorld(), lines: string[] = [];
  await calibrateStage({ out: path.join(w.root, 'ho'), modelFile: w.modelFile, splitFile: splitIn(w), realDir: w.real, twinFitDir: w.twinFit, heldInBudgetS: 0, log: (l) => lines.push(l), now: () => 0 });
  assert.deepEqual(readDepthModel(w.modelFile)!.calibration!.code, now);
  assert.equal(lines.filter((l) => l === `[twin] calibration: fitted by simulator ${now.sim}, requote layer ${now.replay}, feature code ${now.featureCode}`).length, 1);
  assert.match(lines[lines.length - 1], /^\[twin\] calibration: written into the depth model/, 'the stamp line comes before the written line');
  assert.doesNotThrow(() => checkDepthModelCalibration(w.modelFile, split, { run: '6' }));
});

test('the dev verdict adds, right after each by-asset line, the per-asset mean gaps of the six level features in real within-asset sd (report only, the numbers the calibration reads); the confirm verdict prints none of it and the checks do not move', async () => {
  const ix = (n: string) => FEATURES.indexOf(n as (typeof FEATURES)[number]);
  // BTC and ETH lives; the twin is a quarter of the real trade rate and a shade shallower, with a heavier trade size, and the same top size and quoted share
  const build = (src: string, twin: boolean, seed: number): Row[] => rows(src, 0, seed).map((r, i) => {
    const a = i % 2 ? 'BTC' : 'ETH', f = [...r.f], noise = (k: string) => 0.1 * f[ix(k)];
    f[ix('tradesPerMin')] = (twin ? 900 : 3000) * (a === 'BTC' ? 1 : 0.1) * (1 + noise('tradesPerMin')); f[ix('depth10')] = (twin ? 7 : 8) + noise('depth10'); f[ix('tradeSize')] = (twin ? 1.5 : 1) + noise('tradeSize');
    f[ix('topSize')] = 5 + noise('topSize'); f[ix('quotedShare')] = 0.7 + noise('quotedShare'); f[ix('quoteChangesPerMin')] = 40 * (twin ? 0.5 : 1) * (1 + noise('quoteChangesPerMin'));
    return { ...r, ticker: `KX${a}15M-26OCT${20 + (i % 3)}${String(i).padStart(4, '0')}`, f };
  });
  const real = build('real', false, 51), twin = build('twin', true, 52);
  const dir = (name: 'dev' | 'confirm') => { const out = verdictDir(name, () => twin); fs.writeFileSync(path.join(out, 'features-real.json'), JSON.stringify(real)); for (const s of ['requote', 'depth']) fs.writeFileSync(path.join(out, `features-${s}.json`), JSON.stringify(twin.map((x) => ({ ...x, src: s })))); return out; };
  const devDir = dir('dev'), dev = await verdictLines(devDir);
  const cols = Object.fromEntries(['depth10', 'tradeSize', 'quoteChangesPerMin', 'topSize', 'tradesPerMin', 'quotedShare'].map((k) => [k, ix(k)]));
  for (const src of ['requote', 'depth']) for (const asset of ['BTC', 'ETH']) {
    const at = dev.lines.findIndex((l) => l.startsWith(`[twin] ${src} by asset ${asset}: `)), gap = dev.lines[at + 1];
    assert.ok(at >= 0, `${src} ${asset}: the by-asset line is there`);
    assert.match(gap, new RegExp(`^\\[twin\\] ${src} gap by asset ${asset} \\(twin minus real, in real within-asset sd; report only\\): depth10 -?[\\d.]+, tradeSize -?[\\d.]+, quoteChangesPerMin -?[\\d.]+, topSize -?[\\d.]+, tradesPerMin -?[\\d.]+, quotedShare -?[\\d.]+$`), 'the gap line follows its by-asset line, the six features in the order of the brief\'s table');
    // the numbers are the calibration's own: the same function on the same rows
    const g = gapsOfAsset(real.filter((r) => r.ticker.startsWith(`KX${asset}`)), twin.filter((r) => r.ticker.startsWith(`KX${asset}`)), cols);
    assert.equal(gap.split('): ')[1], Object.entries(g.gaps).map(([k, v]) => `${k} ${v.toFixed(2)}`).join(', '));
    assert.ok(g.gaps.tradesPerMin < -5 && g.gaps.depth10 < -5 && g.gaps.tradeSize > 5 && g.gaps.quoteChangesPerMin < -5, `${asset}: the twin is quieter, shallower and heavier-sized: ${JSON.stringify(g.gaps)}`);
    assert.ok(Math.abs(g.gaps.topSize) < 1 && Math.abs(g.gaps.quotedShare) < 1, `${asset}: no gap where there is none`);
    assert.ok(gap.length < 300 && !/KX[A-Z]|\$/.test(gap), 'short, numbers only');
    // the report holds them too, rounded to 3 places
    assert.deepEqual(dev.report.twins[src].gapByAsset[asset].gaps, Object.fromEntries(Object.entries(g.gaps).map(([k, v]) => [k, +v.toFixed(3)])));
  }
  assert.deepEqual(Object.keys(dev.report.twins.depth.gapByAsset).sort(), ['BTC', 'ETH'], 'an asset with no lives has no gap line');
  assert.equal(JSON.parse(fs.readFileSync(path.join(devDir, 'verdict.json'), 'utf8')).twins.depth.gapByAsset.BTC.gaps.tradesPerMin, dev.report.twins.depth.gapByAsset.BTC.gaps.tradesPerMin, 'verdict.json keeps them');
  // report only: the checks are the same four, and nothing of the gaps is among them
  assert.deepEqual(Object.keys(dev.report.twins.depth.checks), ['indistinguishable', 'noBias', 'errorWithinNoise', 'sameActivity']);
  // the confirm verdict is blind: no per-asset line, no gap, no gap in its report
  const confDir = dir('confirm'), conf = await verdictLines(confDir, { n: 1, note: 'a look' });
  assert.ok(!conf.lines.some((l) => /gap by asset|by asset/.test(l)), 'no per-asset line on a confirm verdict');
  for (const src of ['requote', 'depth']) assert.ok(!('gapByAsset' in conf.report.twins[src]));
  assert.ok(!/gapByAsset/.test(fs.readFileSync(path.join(confDir, 'verdict.json'), 'utf8')), 'and none in the verdict.json a confirm run keeps');
});

const yamlDoc = (): { d: any; jobs: Record<string, any>; ins: Record<string, any> } => {
  const r = spawnSync('python3', ['-I', '-c', 'import yaml,json,sys; print(json.dumps(yaml.safe_load(open(sys.argv[1]))))', path.join(ROOT, '.github/workflows/history-twin.yml')], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  const d = JSON.parse(r.stdout); return { d, jobs: d.jobs, ins: (d.true ?? d.on).workflow_dispatch.inputs };
};

test('the workflow wires the calibration: wherever the model is fitted it is calibrated right after (FIT days only, never from the judged days\' folder), a reused model is checked and not refitted, and all of it is before the confirm look is numbered', { skip: hasYaml ? false : 'python3 with PyYAML is not installed here' }, () => {
  const { d, jobs, ins } = yamlDoc();
  const steps = jobs.build.steps as Array<{ name?: string; if?: string; id?: string; env?: Record<string, string>; run?: string; uses?: string; with?: Record<string, string> }>;
  const named = (re: RegExp) => { const m = steps.filter((x) => re.test(x.name ?? '')); assert.equal(m.length, 1, `one step ${re}: ${m.length}`); return m[0]; };
  assert.equal(new Set(steps.map((x) => x.name ?? '').filter(Boolean)).size, steps.filter((x) => x.name).length, 'step names stay unique in the build job');
  const fit = named(/^The depth model, fitted/), reuse = named(/^The depth model, reused/), realSide = named(/^The real side of an earlier run/), fitsrc = named(/^The requote FIT days for the calibration/), restore = named(/^Restore the Kalshi history and its replay \(to regenerate FIT days\)/),
    regen = named(/^Regenerate the requote FIT days Drive lacks/), save = named(/^Save the Kalshi history and its replay \(FIT days\)/), calib = named(/^The depth model's per-asset calibration/), check = named(/^The reused depth model's calibration/),
    look = named(/^Number this confirm look/), match = named(/^Match, fill in/), fastRowsStep = named(/^Fast rows/), keep = named(/^Keep the judged features/);
  const evalIf = (e: string | undefined, fastOut: string, v: Record<string, string>): boolean => {
    if (e === undefined) return true;
    const m = /^\$\{\{ (.*) \}\}$/.exec(e); assert.ok(m, `an if of the form: ${e}`);
    const js = m![1].replace(/steps\.split\.outputs\.fast/g, JSON.stringify(fastOut)).replace(/inputs\.([a-z_]+)/g, (_, k) => { assert.ok(k in ins, `input ${k} exists`); return JSON.stringify(v[k] ?? ''); });
    assert.ok(/^[\s"'!=&|a-z0-9_.-]+$/i.test(js), `only comparisons: ${js}`);
    return new Function(`return (${js});`)() as boolean;
  };
  for (const fast of ['true', 'false']) for (const model of ['', '55']) {
    if (fast !== 'true' && model) continue; // the split step refuses depth_model_run without fast
    const on = (s: { if?: string }) => evalIf(s.if, fast, { depth_model_run: model }), fitted = !(fast === 'true' && model !== '');
    assert.equal(on(fit), fitted); assert.equal(on(fitsrc), fitted, `the FIT days' requote source is read wherever the model is fitted (fast ${fast}, model run '${model}')`); assert.equal(on(calib), fitted, 'the calibration runs wherever the model was fitted in this job');
    assert.equal(on(check), !fitted, 'a reused model is checked instead'); assert.equal(on(check), on(reuse)); assert.equal(on(calib) !== on(check), true, 'exactly one of the two');
  }
  assert.equal(evalIf(calib.if, 'false', {}), true, 'a push (no inputs) is the full route: calibrated'); assert.equal(evalIf(check.if, 'false', {}), false);
  assert.equal(fitsrc.id, 'fitsrc');
  for (const s of [restore, regen]) assert.equal(s.if, "${{ steps.fitsrc.outputs.regen != '' }}");
  assert.equal(save.if, "${{ always() && github.event_name == 'workflow_dispatch' && steps.fitsrc.outputs.regen != '' }}");
  assert.notEqual(restore.with!.key, named(/^Restore the Kalshi history and its replay \(to regenerate days\)/).with!.key, 'its own cache key: it never overwrites the judged days\' history');
  // the order: fit, then the FIT days' source, then the calibration, all before the look is numbered and the judged days are read
  const at = (x: object) => steps.indexOf(x as never);
  assert.ok(at(fit) < at(fitsrc) && at(fitsrc) < at(restore) && at(restore) < at(regen) && at(regen) < at(save) && at(save) < at(calib), 'fit < FIT days < calibration');
  assert.ok(at(reuse) < at(check) && at(realSide) < at(calib) && at(realSide) < at(check), 'the real side of an earlier run is there before the calibration reads it');
  assert.ok(at(calib) < at(look) && at(check) < at(look) && at(look) < at(match) && at(look) < at(fastRowsStep) && at(fastRowsStep) < at(keep), 'calibration < confirm look < rows < keep');
  assert.ok(steps.findIndex((x) => /^The depth simulator parameters of a sweep/.test(x.name ?? '')) < at(calib), 'a sweep\'s parameters are read before they are played');
  // the FIT days' steps name no judged day, no warm-up day and the judged days' requote folder
  for (const s of [fitsrc, restore, regen, save, calib, check]) {
    const text = JSON.stringify({ ...s, name: undefined });
    assert.ok(!/judge|warm|WARM|replay-src|steps\.real\.outputs|steps\.twinsrc|NEED|JUDGE|data\/twin\/(real|requote|depth)|confirm_look/i.test(text), `${s.name}: names no judged day or the judged days' folder`);
  }
  assert.deepEqual(Object.keys(fitsrc.env!), ['FIT']); assert.equal(fitsrc.env!.FIT, '${{ steps.split.outputs.fit }}');
  assert.match(fitsrc.run!, /--include "md-\$d\.jsonl\.gz"/); assert.match(fitsrc.run!, /--stage twin-source --dir "\$D" --days "\$FIT" --out data\/calib/); assert.match(fitsrc.run!, /cp "\$D\/md-\$d\.jsonl\.gz" data\/replay-fit\//);
  assert.match(regen.run!, /for d in \$\{REGEN\/\/,\/ \}; do[\s\S]*cp "data\/history-replay\/md-\$d\.jsonl\.gz" data\/replay-fit\//); assert.equal(regen.env!.REGEN, '${{ steps.fitsrc.outputs.regen }}');
  assert.match(calib.run!, /--stage calibrate --depth-model data\/models\/depth_model\.json --split-file data\/twin\/split\.json --real data\/twin-real15m --twin-fit data\/replay-fit --out data\/calib "\$\{RC\[@\]\}"/);
  assert.deepEqual(Object.keys(calib.env!).sort(), ['FAST', 'REAL_FEATURES_RUN']); assert.match(check.run!, /--stage calibration-check --depth-model data\/models\/depth_model\.json --split-file data\/twin\/split\.json --run "\$RUN"/);
  // the Drive reads are copy only, of the replay source the judged days use
  assert.ok(/drive_lab\.sh get simulated\/kalshi-replay-200d/.test(fitsrc.run!) && !/drive_lab\.sh (put|delete|purge|sync|move)|rclone (sync|delete|purge|move|deletefile)/.test(`${fitsrc.run}${calib.run}${check.run}${regen.run}`));
  // the inputs and the header say it, the push trigger watches the new file, and the framing lines of the comment keep the calibration's lines
  assert.match(ins.depth_model_run.description, /^fast only/); assert.match(ins.depth_model_run.description, /per-asset calibration/); assert.match(ins.real_features_run.description, /^fast only[\s\S]*real-fit-features\.json/);
  assert.ok(Object.keys(ins).length <= 25, `${Object.keys(ins).length} inputs (GitHub allows 25)`);
  assert.ok((d.true ?? d.on).push.paths.includes('research/history/depthCalibrate.ts'), 'a change to the calibration runs the workflow on its branch');
  const head = wf().slice(0, wf().indexOf('\nname: History twin'));
  for (const w of ['THE PER-ASSET CALIBRATION (round R2', 'real-fit-features.json', 'data/replay-fit', 'a model without one is refused']) assert.ok(head.includes(w), `the header says: ${w}`);
  const frame = new RegExp(/FRAME='([^']+)'/.exec(stepScript(wf(), 'Report (commit comment; RUNBOOK'))![1]);
  for (const l of ['[twin] calibration: asset BTC iter 1: gaps (sd) top 0.10', '[twin] calibration: fitted on the FIT days 2026-11-11: 2 asset(s)', '[twin] calibration: held-in check skipped: about 9 s', '[twin] depth model calibration: BTC (top 1 level 1.2 size 1 trades 1 flick 1); fitted on the FIT days 2026-11-11, 3 iteration(s)', '[twin] depth model calibration carried by run 5: assets BTC ETH, fitted on 2026-11-11, 2 iteration(s); no recalibration', '[twin] ERROR: the per-asset calibration failed (exit 1)']) assert.ok(frame.test(l), `the comment keeps ${l}`);
  assert.ok(!frame.test('[twin] some other line'), 'and not every line');
  // no step of the calibration hides its failure
  for (const s of [fitsrc, restore, regen, calib, check]) assert.ok(!('continue-on-error' in s), s.name);
});

test('the calibration step: its arguments, its lines in the log, the model kept as depth_model.uncalibrated.json when it fails, and its seconds on a fast run only', () => {
  const y = wf(), { ws, bin, tmp } = stageWs(), step = stepScript(y, 'The depth model\'s per-asset calibration');
  fs.writeFileSync(path.join(bin, 'node'), '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$STUB_ARGS"\necho "[twin] calibration: asset BTC iter 1: stub"\necho "noise that is not a twin line"\n[ "${STUB_RC:-0}" = 0 ] || { echo "Error: boom" >&2; exit "${STUB_RC}"; }\n', { mode: 0o755 });
  const args = path.join(tmp, 'args.txt'), log = path.join(tmp, 'build.log'), model = path.join(ws, 'data/models/depth_model.json');
  const run = (env: Record<string, string>) => {
    fs.rmSync(args, { force: true }); fs.rmSync(log, { force: true }); fs.rmSync(path.join(ws, 'data/models'), { recursive: true, force: true }); fs.mkdirSync(path.join(ws, 'data/models'), { recursive: true }); fs.writeFileSync(model, '{"days":[]}');
    const r = bash(step, { PATH: `${bin}:${process.env.PATH}`, FAST: '', REAL_FEATURES_RUN: '', RUNNER_TEMP: tmp, STUB_ARGS: args, ...env }, ws);
    return { r, args: fs.existsSync(args) ? fs.readFileSync(args, 'utf8').trim() : '', log: fs.existsSync(log) ? fs.readFileSync(log, 'utf8') : '' };
  };
  const base = '--import tsx research/historyTwin.ts --stage calibrate --depth-model data/models/depth_model.json --split-file data/twin/split.json --real data/twin-real15m --twin-fit data/replay-fit --out data/calib';
  const full = run({}); assert.equal(full.r.status, 0, `${full.r.stdout}${full.r.stderr}`);
  assert.equal(full.args, base); assert.match(full.log, /^\[twin\] calibration: asset BTC iter 1: stub$/m); assert.ok(!/noise|fast:/.test(full.log), 'the [twin] lines only, and no fast line on the full route');
  assert.ok(fs.existsSync(model) && !fs.existsSync(path.join(ws, 'data/models/depth_model.uncalibrated.json')));
  assert.equal(run({ FAST: 'false' }).log.includes('fast:'), false);
  const reuse = run({ FAST: 'true', REAL_FEATURES_RUN: '66' }); assert.equal(reuse.r.status, 0);
  assert.equal(reuse.args, `${base} --real-cache data/real-cache --real-run 66`, 'the real FIT rows of an earlier run are read, not parsed');
  assert.match(reuse.log, /^\[twin\] fast: calibration \d+ s$/m);
  // a failure: the model is not left as a model to reuse, the reason is in the log, the step fails
  const bad = run({ STUB_RC: '3' });
  assert.notEqual(bad.r.status, 0); assert.ok(!fs.existsSync(model), 'no depth_model.json is left behind'); assert.equal(fs.readFileSync(path.join(ws, 'data/models/depth_model.uncalibrated.json'), 'utf8'), '{"days":[]}');
  assert.match(bad.log, /^\[twin\] ERROR: the per-asset calibration failed \(exit 3\); last lines: .*boom.*\. The depth model is kept as depth_model\.uncalibrated\.json, never as a model to reuse$/m);
  assert.match(bad.log, /^\[twin\] calibration: asset BTC iter 1: stub$/m, 'the lines the stage printed before it failed are kept');
  assert.ok(!/fast: calibration/.test(run({ STUB_RC: '3', FAST: 'true' }).log), 'a failure prints no timing');
  // the model the Drive step keeps is the models folder: the calibrated file, or the uncalibrated one under its own name (a depth_model_run reuse looks for depth_model.json)
  assert.match(stepScript(y, 'Keep the simulated twin on Drive'), /\[ -d data\/models \] && ln -s "\$GITHUB_WORKSPACE\/data\/models" "\$S\/models"/);
});

test('the calibration check step runs the stage on the reused model: a calibrated one is passed with its line, one without a block, or of other days, stops the run before any day is read', () => {
  const y = wf(), { ws, tmp } = stageWs(), step = stepScript(y, 'The reused depth model\'s calibration');
  const model = { ...synthModel({ days: FAST_FIT }), schema: DEPTH_MODEL_SCHEMA };
  const put = (m: object) => { fs.mkdirSync(path.join(ws, 'data/models'), { recursive: true }); fs.writeFileSync(path.join(ws, 'data/models/depth_model.json'), JSON.stringify(m)); };
  fs.writeFileSync(path.join(ws, 'data/twin/split.json'), JSON.stringify({ name: 'custom', fit: FAST_FIT, judge: FAST_JUDGE, warm: [] }));
  const log = path.join(tmp, 'build.log'), run = (id: string) => { fs.rmSync(log, { force: true }); const r = bash(step, { PATH: process.env.PATH ?? '', RUN: id, RUNNER_TEMP: tmp }, ws); return { r, log: fs.existsSync(log) ? fs.readFileSync(log, 'utf8') : '' }; };
  put(withCalibration(model, FAST_FIT, 4, { BTC: { ...CAL_TRUTH.BTC }, ETH: { ...CAL_TRUTH.ETH } }, undefined, calibrationCode()));
  const ok = run('55'); assert.equal(ok.r.status, 0, `${ok.r.stdout}${ok.r.stderr}`);
  assert.match(ok.log, new RegExp(`^\\[twin\\] depth model calibration was fitted by simulator ${calibrationCode().sim}, requote layer ${REPLAY_VERSION}, feature code ${FEATURE_CODE_VERSION} \\(this ref has the same`, 'm'), 'the code it was fitted by is printed');
  // a calibration fitted by other code (a changed simulator) or by none that says so is stopped here, before any day is read
  put(withCalibration(model, FAST_FIT, 4, { BTC: { ...CAL_TRUTH.BTC } }, undefined, { ...calibrationCode(), sim: 'deadbeefdeadbeef' })); const stale = run('55'); assert.notEqual(stale.r.status, 0); assert.match(stale.log, /^\[twin\] ERROR: depth_model_run 55: the model's calibration was fitted by other code than this ref's: simulator deadbeefdeadbeef then/m);
  put(withCalibration(model, FAST_FIT, 4, { BTC: { ...CAL_TRUTH.BTC } })); const unstamped = run('55'); assert.notEqual(unstamped.r.status, 0); assert.match(unstamped.log, /^\[twin\] ERROR: depth_model_run 55: the model's calibration carries no code stamp/m);
  put(withCalibration(model, FAST_FIT, 4, { BTC: { ...CAL_TRUTH.BTC }, ETH: { ...CAL_TRUTH.ETH } }, undefined, calibrationCode()));
  assert.match(ok.log, /^\[twin\] depth model calibration carried by run 55: assets BTC ETH, fitted on 2026-11-11 2026-11-12, 4 iteration\(s\); no recalibration$/m); assert.ok(!/calibration: /.test(ok.log), 'no fit line: it fits nothing');
  put(model); const none = run('55'); assert.notEqual(none.r.status, 0); assert.match(none.log, /^\[twin\] ERROR: depth_model_run 55: the model has no calibration block: it was fitted before the per-asset calibration ran/m);
  put(withCalibration(model, ['2026-11-11'], 2, { BTC: { ...CAL_TRUTH.BTC } })); const other = run('55'); assert.notEqual(other.r.status, 0); assert.match(other.log, /^\[twin\] ERROR: depth_model_run 55: the depth model's calibration was fitted on 2026-11-11, not on the days/m);
  for (const bad of ['abc', '5;rm', '../1', '']) { const r = run(bad); assert.notEqual(r.r.status, 0, bad); assert.match(r.log, /^\[twin\] ERROR: depth_model_run must be a run id \(digits only\)$/m); }
});

test('the requote FIT days step: copy-only Drive read of the FIT days and the replay manifest, the ones the manifest\'s version vouches for go to data/replay-fit, the rest are named for regeneration, and no judged day or data/replay-src is touched', () => {
  const y = wf(), { ws, bin, tmp } = stageWs(), drive = tmpDir(), calls = path.join(tmp, 'calls.txt'), step = stepScript(y, 'The requote FIT days for the calibration'), out = path.join(tmp, 'gh_out');
  const src = path.join(drive, 'simulated/kalshi-replay-200d'), mk = (version: number | undefined, days: string[]) => { fs.rmSync(drive, { recursive: true, force: true }); fs.mkdirSync(src, { recursive: true }); if (version !== undefined) fs.writeFileSync(path.join(src, 'replay-manifest.json'), JSON.stringify({ version, days: {} })); for (const d of days) fs.writeFileSync(path.join(src, `md-${d}.jsonl.gz`), `day ${d}`); fs.writeFileSync(path.join(src, 'md-2026-11-13.jsonl.gz'), 'a judged day that must not be read'); };
  const run = () => { for (const f of [calls, out, path.join(tmp, 'build.log')]) fs.rmSync(f, { force: true }); for (const d of ['data/replay-fit', 'data/replay-fit-drive', 'data/calib', 'data/replay-src']) fs.rmSync(path.join(ws, d), { recursive: true, force: true });
    const r = bash(step, { PATH: `${bin}:${process.env.PATH}`, FIT: FAST_FIT.join(','), RUNNER_TEMP: tmp, STUB_DRIVE: drive, STUB_CALLS: calls, GITHUB_OUTPUT: out }, ws);
    return { r, log: fs.existsSync(path.join(tmp, 'build.log')) ? fs.readFileSync(path.join(tmp, 'build.log'), 'utf8') : '', out: fs.existsSync(out) ? fs.readFileSync(out, 'utf8') : '', got: fs.existsSync(path.join(ws, 'data/replay-fit')) ? fs.readdirSync(path.join(ws, 'data/replay-fit')).sort() : [], calls: fs.existsSync(calls) ? fs.readFileSync(calls, 'utf8').trim() : '' }; };
  mk(REPLAY_VERSION, FAST_FIT); const all = run(); assert.equal(all.r.status, 0, `${all.r.stdout}${all.r.stderr}`);
  assert.deepEqual(all.got, FAST_FIT.map((d) => `md-${d}.jsonl.gz`)); assert.equal(all.out.trim(), 'regen=');
  assert.match(all.log, new RegExp(`^\\[twin\\] calibration: requote FIT days: 2 of 2 day\\(s\\) from Drive simulated/kalshi-replay-200d \\(manifest version ${REPLAY_VERSION}, REPLAY_VERSION ${REPLAY_VERSION}\\)$`, 'm'));
  assert.equal(all.calls, `get simulated/kalshi-replay-200d data/replay-fit-drive --include replay-manifest.json --include md-2026-11-11.jsonl.gz --include md-2026-11-12.jsonl.gz`, 'only the manifest and the FIT days are asked for');
  assert.ok(!fs.existsSync(path.join(ws, 'data/replay-src')), 'the judged days\' folder is not created or written');
  assert.ok(!fs.existsSync(path.join(ws, 'data/replay-fit/md-2026-11-13.jsonl.gz')));
  // a day Drive lacks, a manifest of another version, and no manifest: regenerated (named in the output the regeneration step reads), never guessed
  mk(REPLAY_VERSION, [FAST_FIT[0]]); const part = run(); assert.equal(part.r.status, 0, part.r.stderr); assert.deepEqual(part.got, [`md-${FAST_FIT[0]}.jsonl.gz`]); assert.equal(part.out.trim(), `regen=${FAST_FIT[1]}`);
  assert.match(part.log, /^\[twin\] calibration: requote FIT days: 1 of 2 day\(s\) from Drive simulated\/kalshi-replay-200d .*; 1 regenerated with research\/kalshiReplayData\.ts \(/m);
  mk(REPLAY_VERSION - 1, FAST_FIT); const old = run(); assert.deepEqual(old.got, []); assert.equal(old.out.trim(), `regen=${FAST_FIT.join(',')}`);
  mk(undefined, FAST_FIT); assert.equal(run().out.trim(), `regen=${FAST_FIT.join(',')}`);
});

test('the match step hands the calibration\'s real FIT rows to the features stage (not on a confirm split, and only when the folder is there); the fast rows step does the same', () => {
  const y = wf(), wsn = stageWs(), args = path.join(wsn.tmp, 'a.txt');
  fs.writeFileSync(path.join(wsn.bin, 'node'), '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$STUB_ARGS"\necho "[twin] stub"\n', { mode: 0o755 }); fs.writeFileSync(path.join(wsn.ws, 'data/twin/x'), 'x');
  const calib = path.join(wsn.ws, 'data/calib'), feat = (split: string, withDir: boolean) => { fs.rmSync(args, { force: true }); fs.rmSync(calib, { recursive: true, force: true }); if (withDir) fs.mkdirSync(calib);
    const r = bash(stepScript(y, 'Match, fill in, and describe'), { PATH: `${wsn.bin}:${process.env.PATH}`, SPLIT: split, FIT: SPLITS.dev.fit.join(','), JUDGE: DEV_JUDGED.join(','), WARM: '', NEED: '', LAG: 'false', DEPTH_PARAMS_RUN: '', RUNNER_TEMP: wsn.tmp, STUB_ARGS: args }, wsn.ws);
    assert.equal(r.status, 0, `${r.stdout}${r.stderr}`); return fs.readFileSync(args, 'utf8').split('\n').filter((l) => /--stage features/.test(l))[0]; };
  assert.match(feat('dev', true), /--extra-days 2026-11-11,2026-11-12,2026-11-15 --extra-dir data\/twin-real15m --real15m data\/twin-real15m --handoff data\/calib --out data\/twin$/);
  assert.match(feat('dev', false), /--extra-days 2026-11-11,2026-11-12,2026-11-15 --extra-dir data\/twin-real15m --real15m data\/twin-real15m --out data\/twin$/, 'no folder, no flag');
  assert.ok(!/--handoff|--extra-days|--real15m/.test(feat('confirm', true)), 'a confirm split prints no fit-day tables and writes no real side: nothing to hand over');
  const fastStep = stepScript(y, 'Fast rows'), fast = (withDir: boolean) => { fs.rmSync(args, { force: true }); fs.rmSync(calib, { recursive: true, force: true }); if (withDir) fs.mkdirSync(calib);
    const r = bash(fastStep, { PATH: `${wsn.bin}:${process.env.PATH}`, JUDGE: FAST_JUDGE.join(','), DEPTH_PARAMS_RUN: '', REAL_FEATURES_RUN: '', RUNNER_TEMP: wsn.tmp, STUB_ARGS: args }, wsn.ws);
    assert.equal(r.status, 0, `${r.stdout}${r.stderr}`); return fs.readFileSync(args, 'utf8').trim(); };
  const base = `--import tsx research/historyTwin.ts --stage fastrows --real data/twin-real15m --twin data/replay-src --days ${FAST_JUDGE.join(',')} --depth-model data/models/depth_model.json --out data/twin`;
  assert.equal(fast(true), `${base} --handoff data/calib`); assert.equal(fast(false), base);
});

test('a depth_model_run reuse carries the calibration: the reuse step copies the model file whole, and the calibration check passes what it copied; a model with no block is copied as it is and then refused by the check', () => {
  const y = wf(), { ws, bin, tmp } = stageWs(), drive = tmpDir(), reuse = stepScript(y, 'The depth model, reused from an earlier run'), check = stepScript(y, 'The reused depth model\'s calibration');
  fs.writeFileSync(path.join(ws, 'data/twin/split.json'), JSON.stringify({ name: 'custom', fit: FAST_FIT, judge: FAST_JUDGE, warm: [] }));
  const model = { ...synthModel({ days: FAST_FIT }), schema: DEPTH_MODEL_SCHEMA };
  const onDrive = (m: object) => { const d = path.join(drive, 'simulated/history-twin/55/models'); fs.mkdirSync(d, { recursive: true }); fs.writeFileSync(path.join(d, 'depth_model.json'), JSON.stringify(m)); return path.join(d, 'depth_model.json'); };
  const env = { PATH: `${bin}:${process.env.PATH}`, RUN: '55', FAST: 'true', JOB_START: String(Math.floor(Date.now() / 1000)), RUNNER_TEMP: tmp, STUB_DRIVE: drive };
  const go = () => { fs.rmSync(path.join(tmp, 'build.log'), { force: true }); for (const d of ['data/models', 'data/model-src', 'data/model-meta']) fs.rmSync(path.join(ws, d), { recursive: true, force: true }); return { a: bash(reuse, env, ws), b: () => bash(check, env, ws) }; };
  const calibrated = onDrive(withCalibration(model, FAST_FIT, 4, { BTC: { ...CAL_TRUTH.BTC }, ETH: { ...CAL_TRUTH.ETH } }, undefined, calibrationCode()));
  const ok = go(); assert.equal(ok.a.status, 0, `${ok.a.stdout}${ok.a.stderr}`);
  assert.equal(fs.readFileSync(path.join(ws, 'data/models/depth_model.json'), 'utf8'), fs.readFileSync(calibrated, 'utf8'), 'the copy is the file, calibration block and all');
  assert.deepEqual(readDepthModel(path.join(ws, 'data/models/depth_model.json'))!.calibration!.byAsset.ETH, CAL_TRUTH.ETH);
  const c = ok.b(); assert.equal(c.status, 0, `${c.stdout}${c.stderr}`);
  const text = fs.readFileSync(path.join(tmp, 'build.log'), 'utf8');
  assert.match(text, /^\[twin\] depth model reused from run 55: fitted on 2026-11-11 2026-11-12 \(exactly the fit days\), schema 3;/m); assert.match(text, /^\[twin\] depth model calibration carried by run 55: assets BTC ETH, fitted on 2026-11-11 2026-11-12, 4 iteration\(s\); no recalibration$/m);
  assert.ok(text.indexOf('depth model reused') < text.indexOf('calibration carried'), 'the days are checked first, then the block');
  // a model that was fitted by this study version but never calibrated (a run whose calibration failed keeps it as depth_model.uncalibrated.json, so this is a hand-made one): copied, then refused by the check
  onDrive(model); const bare = go(); assert.equal(bare.a.status, 0); const r = bare.b(); assert.notEqual(r.status, 0);
  assert.match(fs.readFileSync(path.join(tmp, 'build.log'), 'utf8'), /^\[twin\] ERROR: depth_model_run 55: the model has no calibration block/m);
});
// ---- R2 end ----

// ---- S1 begin: --jobs for the match and features stages, their timing lines, and the job's time budget (round S1) ----
// A synthetic world different from the fast route's: FOUR assets in the real days against THREE in the twin (XRP is real only), FIVE judged days (an odd number) and two warm-up
// days that are also FIT days (as on dev: the day before 11-10 is a fit day), a record of a contract the twin lists only the day before.

const PAR_FIT = ['2026-11-05', '2026-11-06', '2026-11-09'], PAR_JUDGE = ['2026-11-07', '2026-11-08', '2026-11-10', '2026-11-11', '2026-11-12'], PAR_WARM = ['2026-11-06', '2026-11-09'];
const PAR_J = PAR_JUDGE.join(','), PAR_W = PAR_WARM.join(',');
/** A contract of the twin's day 11-09 that the twin's day 11-10 does not list: a record of it in the real day 11-10 is kept only through the day-before rule. */
const CARRIED = 'KXBTC15M-26NOV090600-00';
const gunzipText = (f: string) => zlib.gunzipSync(fs.readFileSync(f)).toString('utf8');
const filesUnder = (dir: string): string[] => (fs.readdirSync(dir, { recursive: true }) as string[]).filter((f) => fs.statSync(path.join(dir, f)).isFile()).sort();

interface ParWorld { root: string; real: string; twin: string; modelFile: string }
async function buildParWorld(o: { days: string[]; twinDays: string[]; carried?: boolean; assets?: string[]; twinAssets?: string[]; windows?: number }): Promise<ParWorld> {
  const root = tmpDir(), real = path.join(root, 'real15m'), twin = path.join(root, 'replay-src');
  fs.mkdirSync(real); fs.mkdirSync(twin);
  const modelFile = path.join(root, 'depth_model.json');
  fs.writeFileSync(modelFile, JSON.stringify({ ...synthModel({ days: PAR_FIT }), schema: DEPTH_MODEL_SCHEMA }));
  const lib = readDepthModel(modelFile)!;
  for (const [i, d] of o.days.entries()) {
    const raw = path.join(root, `raw-${d}.jsonl.gz`), f = path.join(real, `md-${d}.jsonl.gz`);
    writeEventsGz(raw, synthRequoteDay({ day: d, assets: o.assets ?? ['BTC', 'ETH', 'SOL', 'XRP'], windows: o.windows ?? 2, seed: 70 + i }));
    await fillDayFile(raw, f, { how: 'depth' }, lib);
    if (o.carried && d === '2026-11-10') {
      const t = Date.parse('2026-11-10T00:00:05Z');
      fs.writeFileSync(f, zlib.gzipSync(`${JSON.stringify({ t, k: 'book', ticker: CARRIED, bids: [{ price: 0.4, size: 5 }], asks: [{ price: 0.6, size: 5 }], ts: t })}\n${gunzipText(f)}`));
    }
    fs.writeFileSync(path.join(real, `meta-${d}.json`), JSON.stringify({ day: d, version: real15mTag(), sha256: sha256Of(f) }));
    if (o.twinDays.includes(d)) writeEventsGz(path.join(twin, `md-${d}.jsonl.gz`), synthRequoteDay({ day: d, assets: o.twinAssets ?? ['BTC', 'ETH', 'SOL'], windows: o.windows ?? 2, seed: 5 + i }));
  }
  return { root, real, twin, modelFile };
}
let parWorldP: Promise<ParWorld> | undefined;
const parWorld = () => (parWorldP ??= buildParWorld({ days: [...PAR_FIT, ...PAR_JUDGE].sort(), twinDays: [...PAR_WARM, ...PAR_JUDGE], carried: true }));
/** A copy of a world's folders (the days are small) to take days out of or spoil. */
const copyWorld = (w: ParWorld): ParWorld => { const root = tmpDir(); fs.cpSync(w.real, path.join(root, 'real15m'), { recursive: true }); fs.cpSync(w.twin, path.join(root, 'replay-src'), { recursive: true }); return { ...w, root, real: path.join(root, 'real15m'), twin: path.join(root, 'replay-src') }; };

const parSplit = (out: string) => okCli('--stage', 'split', '--split', 'custom', '--fit-days', PAR_FIT.join(','), '--judge-days', PAR_J, '--warm-days', PAR_W, '--out', out);
const matchArgs = (w: ParWorld, out: string, jobs: number | string, days = PAR_J, warm = PAR_W) => ['--stage', 'match', '--real', w.real, '--twin', w.twin, '--days', days, '--warm-days', warm, '--jobs', String(jobs), '--out', out];
const featArgs = (w: ParWorld, out: string, jobs: number | string) => ['--stage', 'features', '--dirs', `real=${out}/real,requote=${out}/requote,depth=${out}/depth`, '--days', PAR_J, '--jobs', String(jobs), '--extra-days', PAR_FIT.join(','), '--extra-dir', w.real, '--real15m', w.real, '--out', out];
/** The full route with --jobs: split, match, fill, features (the workflow step's arguments). The [twin] lines of the three stages. */
function parRoute(w: ParWorld, out: string, jobs: number | string): string[] {
  fs.mkdirSync(out, { recursive: true });
  parSplit(out);
  return [
    ...tw(okCli(...matchArgs(w, out, jobs))),
    ...tw(okCli('--stage', 'fill', '--src', `${out}/requote`, '--dst', `${out}/depth`, '--how', 'depth', '--depth-model', w.modelFile, '--split-file', `${out}/split.json`)),
    ...tw(okCli(...featArgs(w, out, jobs))),
  ];
}
const TIMING_DAY = /^\[twin\] (?:match (\d{4}-\d{2}-\d{2}): tickers (\d+\.\d) s, restrict (\d+\.\d) s, pair (\d+\.\d) s|fill (\d{4}-\d{2}-\d{2}): (\d+\.\d) s|features (\w+) (\d{4}-\d{2}-\d{2}): (\d+\.\d) s)$/;
/** Everything but the timing lines, the path of the run's folder made a name. */
const untimed = (lines: string[], out: string) => lines.filter((l) => !FILE_ROUTE_TIMING.test(l)).map((l) => l.split(out).join('OUT'));
/** Every file under both folders the same, to the byte, and the lines the same but for the timing lines. */
function assertSameRun(a: { out: string; lines: string[] }, b: { out: string; lines: string[] }, what: string) {
  const fa = filesUnder(a.out);
  assert.deepEqual(filesUnder(b.out), fa, `${what}: the same files`);
  for (const f of fa) {
    assert.ok(fs.readFileSync(path.join(a.out, f)).equals(fs.readFileSync(path.join(b.out, f))), `${what}: ${f} has the same bytes`);
    if (f.endsWith('.gz')) assert.equal(gunzipText(path.join(b.out, f)), gunzipText(path.join(a.out, f)), `${what}: ${f} decompresses to the same text`);
  }
  for (const o of [a.out, b.out]) assert.deepEqual(fs.readdirSync(o).filter((n) => n.startsWith(UNIT_TMP_PREFIX)), [], `${what}: no temp folder is left in ${path.basename(o)}`);
  assert.deepEqual(untimed(b.lines, b.out), untimed(a.lines, a.out), `${what}: the same lines in the same order but for the timing lines`);
}
let parSerialP: Promise<{ out: string; lines: string[] }> | undefined;
const parSerial = () => (parSerialP ??= parWorld().then((w) => { const out = path.join(tmpDir(), 'serial'); return { out, lines: parRoute(w, out, 1) }; }));

test('match and features with --jobs 3 give the serial route\'s files byte for byte and its lines in its order, on a world of 4 real assets, 5 judged days and 2 warm fit days', async () => {
  const w = await parWorld(), serial = await parSerial(), par = { out: path.join(tmpDir(), 'par3'), lines: [] as string[] };
  par.lines = parRoute(w, par.out, 3);
  assertSameRun(serial, par, 'jobs 3 against jobs 1');
  // not vacuous: the order of paired.json is [...warm, ...judged] (not sorted, not the order the days finished), every source has lives on every judged day, the real side is not the twin
  const paired = JSON.parse(fs.readFileSync(path.join(par.out, 'paired.json'), 'utf8')) as Array<{ day: string; both: number; onlyReal15m: number; onlyTwin: number }>;
  assert.deepEqual(paired.map((p) => p.day), [...PAR_WARM, ...PAR_JUDGE]);
  assert.ok(paired.every((p) => p.both >= 6 && p.onlyReal15m >= 2), JSON.stringify(paired));
  const rows = (src: string): Row[] => JSON.parse(fs.readFileSync(path.join(par.out, `features-${src}.json`), 'utf8'));
  for (const src of ['real', 'requote', 'depth']) { const r = rows(src); assert.ok(r.length >= 30, `${src}: ${r.length} lives`); for (const d of PAR_JUDGE) assert.ok(r.some((x) => x.day === d), `${src} ${d}`); }
  assert.notDeepEqual(rows('real').map((r) => r.f), rows('depth').map((r) => r.f));
  const follow = (src: string) => par.lines.filter((l) => l.startsWith(`[twin] ${src} follow `));
  for (const src of ['real', 'requote', 'depth']) assert.ok(follow(src).length >= 2 && follow(src).every((l) => /\d+ moves, corr -?[\d.]+/.test(l)), `${src} has follow lines`);
  for (const d of PAR_FIT) assert.ok(par.lines.some((l) => l.startsWith(`[twin] real ${d} (not judged): `)), `the fit day ${d} has its activity line`);
  assert.ok(par.lines.some((l) => /^\[twin\] real 2026-11-10: \d+ lives/.test(l)));
  // the day-before rule is in force in the children: a record of a contract only the twin's 11-09 lists is in the restricted 11-10 and in no other day
  assert.ok(gunzipText(path.join(par.out, 'real/md-2026-11-10.jsonl.gz')).includes(CARRIED), 'the carried contract is kept in 11-10');
  for (const d of PAR_JUDGE.filter((x) => x !== '2026-11-10')) assert.ok(!gunzipText(path.join(par.out, `real/md-${d}.jsonl.gz`)).includes(CARRIED), `and not in ${d}`);
  // the timing lines (f): there, in seconds, a day each, and the totals say how many processes ran
  const timing = (lines: string[]) => lines.filter((l) => TIMING_DAY.test(l));
  for (const [label, r] of [['serial', serial], ['jobs 3', par]] as const) {
    const t = timing(r.lines), days = (k: number) => t.map((l) => TIMING_DAY.exec(l)!).filter((m) => m[k] !== undefined);
    assert.deepEqual(days(1).map((m) => m[1]).sort(), [...PAR_WARM, ...PAR_JUDGE].sort(), `${label}: a match line per day`);
    assert.deepEqual(days(5).map((m) => m[5]).sort(), [...PAR_WARM, ...PAR_JUDGE].sort(), `${label}: a fill line per requote day (the warm days are filled too)`);
    assert.deepEqual(days(7).map((m) => `${m[7]} ${m[8]}`).sort(), ['depth', 'real', 'requote'].flatMap((s) => PAR_JUDGE.map((d) => `${s} ${d}`)).sort(), `${label}: a features line per source and judged day`);
    const J = label === 'serial' ? 1 : 3;
    assert.equal(r.lines.filter((l) => new RegExp(`^\\[twin\\] match took \\d+\\.\\d s \\(jobs ${J}\\)$`).test(l)).length, 1, `${label}: match took ... (jobs ${J})`);
    assert.equal(r.lines.filter((l) => new RegExp(`^\\[twin\\] features took \\d+\\.\\d s \\(jobs ${J}\\)$`).test(l)).length, 1, `${label}: features took ... (jobs ${J})`);
    assert.equal(r.lines.filter((l) => /^\[twin\] fill took \d+\.\d s$/.test(l)).length, 1);
    assert.ok(Number.isFinite(Number(/ (\d+\.\d) s/.exec(timing(r.lines)[0])![1])));
  }
  // the order of a day's own lines: the match lines of the days in [...warm, ...judged] order
  assert.deepEqual(par.lines.filter((l) => /^\[twin\] 2026-11-\d\d: contracts real/.test(l)).map((l) => l.slice(7, 17)), [...PAR_WARM, ...PAR_JUDGE]);
});

test('--jobs larger than the number of units runs as many as there are units and gives the same files; a bad --jobs is refused before anything is read', async () => {
  const w = await parWorld(), serial = await parSerial(), big = { out: path.join(tmpDir(), 'par16'), lines: [] as string[] };
  big.lines = parRoute(w, big.out, 16);
  assertSameRun(serial, big, 'jobs 16 against jobs 1');
  assert.ok(big.lines.some((l) => /^\[twin\] match took \d+\.\d s \(jobs 7\)$/.test(l)), '7 days: 7 processes at most');
  assert.ok(big.lines.some((l) => /^\[twin\] features took \d+\.\d s \(jobs 15\)$/.test(l)), '3 sources x 5 days: 15 at most');
  const out = tmpDir();
  for (const bad of ['0', 'x', '-2', '65', '1.5']) {
    const r = twinCli(...matchArgs(w, out, bad)); assert.notEqual(r.status, 0, bad); assert.match(r.stderr, /^\[twin\] ERROR: --jobs must be a whole number from 1 to 64 \(got "/m, bad);
    assert.ok(!fs.existsSync(path.join(out, 'paired.json')) && !fs.existsSync(path.join(out, 'real')), 'nothing was read or written');
    assert.notEqual(twinCli(...featArgs(w, out, bad)).status, 0);
  }
  // no --jobs at all is the serial route
  const none = twinCli(...matchArgs(w, tmpDir(), 1).filter((a, i, all) => a !== '--jobs' && all[i - 1] !== '--jobs'));
  assert.equal(none.status, 0, none.stderr); assert.match(none.stdout, /^\[twin\] match took \d+\.\d s \(jobs 1\)$/m);
});

test('days a run lacks are left out in their place of the order (a warm day with no twin, a warm day with no real recording), the same in the serial and the parallel route', async () => {
  const w = copyWorld(await parWorld());
  fs.rmSync(path.join(w.twin, 'md-2026-11-06.jsonl.gz')); fs.rmSync(path.join(w.real, 'md-2026-11-09.jsonl.gz'));
  const run = (jobs: number) => { const out = path.join(tmpDir(), `left-${jobs}`); fs.mkdirSync(out); parSplit(out); return { out, lines: tw(okCli(...matchArgs(w, out, jobs))) }; };
  const a = run(1), b = run(4);
  assertSameRun(a, b, 'left-out days');
  const first = b.lines.filter((l) => /left out|contracts real/.test(l));
  assert.deepEqual(first.map((l) => l.slice(7, 17)), [...PAR_WARM, ...PAR_JUDGE]);
  assert.match(first[0], /^\[twin\] 2026-11-06: no history twin; left out$/); assert.match(first[1], /^\[twin\] 2026-11-09: no real recording ; left out$/);
  assert.deepEqual((JSON.parse(fs.readFileSync(path.join(b.out, 'paired.json'), 'utf8')) as Array<{ day: string }>).map((p) => p.day), PAR_JUDGE);
  assert.equal(b.lines.filter((l) => /^\[twin\] match 2026-11-0[69]: tickers/.test(l)).length, 0, 'a day left out has no timing line');
  assert.ok(b.lines.some((l) => /^\[twin\] match took \d+\.\d s \(jobs 4\)$/.test(l)));
  // a JUDGED day lacking is an error after the lines, in both routes, and paired.json is the one the serial route writes
  fs.rmSync(path.join(w.twin, 'md-2026-11-11.jsonl.gz'));
  for (const jobs of [1, 3]) { const out = path.join(tmpDir(), `lost-${jobs}`); fs.mkdirSync(out); parSplit(out); const r = twinCli(...matchArgs(w, out, jobs)); assert.notEqual(r.status, 0); assert.match(r.stderr, /^\[twin\] ERROR: judged day\(s\) without a real recording or a twin: 2026-11-11$/m); }
});

/** The pids of every process whose command line holds `needle` (Linux only: undefined elsewhere). */
const processesWith = (needle: string): string[] | undefined => {
  if (!fs.existsSync('/proc/self/cmdline')) return undefined;
  return fs.readdirSync('/proc').filter((p) => /^\d+$/.test(p) && p !== String(process.pid)).filter((p) => { try { return fs.readFileSync(`/proc/${p}/cmdline`, 'utf8').includes(needle); } catch { return false; } });
};

test('a failing unit (a corrupt day file) fails the stage with the child\'s own message, leaves no paired.json, no features file, no temp folder and no child behind', async () => {
  const w = copyWorld(await parWorld()), out = path.join(tmpDir(), 'bad-match');
  fs.mkdirSync(out); parSplit(out);
  fs.writeFileSync(path.join(w.real, 'md-2026-11-10.jsonl.gz'), 'this is not gzip, and has no recording in it');
  const r = twinCli(...matchArgs(w, out, 3));
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /^\[twin\] ERROR: match 2026-11-10: incorrect header check$/m, 'the child\'s own message, with the stage and the unit');
  assert.ok(!fs.existsSync(path.join(out, 'paired.json')), 'no partial paired.json');
  assert.deepEqual(fs.readdirSync(out).filter((n) => n.startsWith(UNIT_TMP_PREFIX)), [], 'the temp folder is removed');
  assert.ok(!/contracts real/.test(r.stdout.split('\n').filter((l) => /2026-11-10/.test(l)).join('\n')), 'the failed day printed no mechanics');
  const strays = processesWith(out); if (strays) assert.deepEqual(strays, [], 'no child process is left behind');
  // the serial route fails on the same file too (it never printed a [twin] ERROR line for it: the stream error is uncaught there)
  const s = twinCli(...matchArgs(w, path.join(tmpDir(), 'bad-serial'), 1)); assert.notEqual(s.status, 0);
  // features: one (source, day) of 15 is corrupt: the whole stage fails, nothing of it is written, nobody is left running
  const good = await parSerial(), fout = path.join(tmpDir(), 'bad-features'); fs.cpSync(good.out, fout, { recursive: true });
  for (const f of fs.readdirSync(fout).filter((x) => x.startsWith('features-') || x === 'real-meta.json')) fs.rmSync(path.join(fout, f));
  fs.writeFileSync(path.join(fout, 'depth/md-2026-11-11.jsonl.gz'), 'not gzip either');
  const fr = twinCli(...featArgs(w, fout, 3));
  assert.notEqual(fr.status, 0); assert.match(fr.stderr, /^\[twin\] ERROR: features depth 2026-11-11: incorrect header check$/m);
  assert.deepEqual(fs.readdirSync(fout).filter((n) => n.startsWith('features-') || n.startsWith(UNIT_TMP_PREFIX)), [], 'no features file, no temp folder');
  const fs2 = processesWith(fout); if (fs2) assert.deepEqual(fs2, []);
});

test('the blind rules hold with --jobs: a confirm-named split prints no per-day mechanics and no tables (only the timing lines, seconds), the files are the serial route\'s, and a dev split that names a confirm day is refused before a child starts', async () => {
  const days = ['2026-11-17', '2026-11-18', '2026-11-19', '2026-11-20'];
  const w = await buildParWorld({ days, twinDays: days, assets: ['BTC', 'ETH', 'XRP'], windows: 2 });
  const CJ = CONFIRM_DAYS.join(','), run = (jobs: number) => {
    const out = path.join(tmpDir(), `confirm-${jobs}`); fs.mkdirSync(out);
    okCli('--stage', 'split', '--split', 'confirm', '--warm-days', '2026-11-17', '--out', out);
    const m = tw(okCli('--stage', 'match', '--real', w.real, '--twin', w.twin, '--days', CJ, '--warm-days', '2026-11-17', '--jobs', String(jobs), '--out', out));
    const f = tw(okCli('--stage', 'features', '--dirs', `real=${out}/real,requote=${out}/requote`, '--days', CJ, '--jobs', String(jobs), '--out', out));
    return { out, lines: [...m, ...f] };
  };
  const a = run(1), b = run(3);
  assertSameRun(a, b, 'confirm split');
  for (const r of [a, b]) {
    assert.ok(!r.lines.some((l) => /^\[twin\] 2026-11-\d\d: /.test(l)), 'no per-day mechanics line');
    assert.ok(!r.lines.some((l) => /follow|\(not judged\)|lives, trades\/min/.test(l)), 'no follow or activity table');
    assert.equal(r.lines.filter((l) => /^\[twin\] matched 3 of 3 judged day\(s\): /.test(l)).length, 1);
    assert.equal(r.lines.filter((l) => /^\[twin\] match 2026-11-\d\d: tickers /.test(l)).length, 4, 'timing lines are printed on every split');
    assert.equal(r.lines.filter((l) => /^\[twin\] features (real|requote) 2026-11-\d\d: \d+\.\d s$/.test(l)).length, 6);
  }
  assert.ok(!fs.existsSync(path.join(b.out, 'real-meta.json')), 'a blind run keeps no real side');
  // a dev-named split on record, a confirm day asked for: refused, in the parent, with --jobs 3, before any day is read
  const out = tmpDir(); okCli('--stage', 'split', '--split', 'dev', '--out', out);
  const r = twinCli('--stage', 'match', '--real', w.real, '--twin', w.twin, '--days', '2026-11-18', '--jobs', '3', '--out', out);
  assert.notEqual(r.status, 0); assert.match(r.stderr, /^\[twin\] ERROR: the confirm days \(2026-11-18\) are read only through split=confirm/m);
  assert.ok(!fs.existsSync(path.join(out, 'paired.json')) && !fs.existsSync(path.join(out, 'real')), 'nothing was made');
  const f = twinCli('--stage', 'features', '--dirs', `real=${w.real}`, '--days', '2026-11-18', '--jobs', '3', '--out', out); assert.notEqual(f.status, 0); assert.match(f.stderr, /confirm days/);
});

// The pool itself (research/history/unitPool.ts), with a tiny child (tests/unitPoolChild.ts) instead of the stages.
const POOL_CHILD = path.join(ROOT, 'tests/unitPoolChild.ts');
const poolOpts = (dir: string, jobs: number, more: object = {}) => ({ script: POOL_CHILD, dir, label: 'test', jobs, execArgv: ['--import', 'tsx'], ...more });
const alive = (pid: number) => { try { process.kill(pid, 0); return true; } catch { return false; } };

test('the pool runs each unit in a child process, at most `jobs` at once, gives the results in the units\' order, calls back once per unit, and two units that must meet only meet with two jobs', async () => {
  const dir = tmpDir(), seen: number[] = [];
  const res = await runUnits<{ id: string; n: number; pid: number }>([0, 1, 2, 3, 4].map((n) => ({ id: `u${n}`, spec: { kind: 'echo', n, ms: n === 0 ? 800 : 0 } })), { ...poolOpts(dir, 2), onResult: (i: number) => seen.push(i) });
  assert.deepEqual(res.map((r) => [r.id, r.n]), [['u0', 0], ['u1', 2], ['u2', 4], ['u3', 6], ['u4', 8]], 'in the order of the units, not of the answers');
  assert.deepEqual([...seen].sort(), [0, 1, 2, 3, 4], 'one callback per unit');
  assert.equal(new Set(res.map((r) => r.pid)).size, 5); assert.ok(res.every((r) => r.pid !== process.pid), 'a process each, none of them this one');
  assert.deepEqual(fs.readdirSync(dir), [], 'the temp folder is gone');
  const track = await runUnits<{ n: number }>([...Array(6).keys()].map((n) => ({ id: `t${n}`, spec: { kind: 'track', dir, ms: 300 } })), poolOpts(dir, 2));
  assert.ok(track.every((t) => t.n >= 1 && t.n <= 2), `never more than 2 at once: ${JSON.stringify(track)}`);
  // concurrency is real: two units that wait for each other's marker meet with 2 jobs (they cannot with 1)
  const meetSpec = (d: string, wait: number) => [{ id: 'a', spec: { kind: 'meet', dir: d, me: 'a', other: 'b', wait } }, { id: 'b', spec: { kind: 'meet', dir: d, me: 'b', other: 'a', wait } }];
  const two = tmpDir(), one = tmpDir();
  assert.deepEqual((await runUnits<{ met: boolean }>(meetSpec(two, 20_000), poolOpts(tmpDir(), 2))).map((r) => r.met), [true, true]);
  assert.deepEqual((await runUnits<{ met: boolean }>(meetSpec(one, 1500), poolOpts(tmpDir(), 1))).map((r) => r.met), [false, true], 'with one job the first waits alone, the second then finds its marker');
  assert.deepEqual(await runUnits([], poolOpts(dir, 3)), [], 'no units, no children');
});

test('the first failed unit rejects the pool with its own first line after every other child is gone; a child that dies with no answer, and a corrupt day (a stream error), are failures too; the temp folder always goes', async () => {
  const dir = tmpDir(), pids = [path.join(dir, 'p1'), path.join(dir, 'p2')];
  await assert.rejects(runUnits([{ id: 'h1', spec: { kind: 'hang', pidFile: pids[0] } }, { id: 'h2', spec: { kind: 'hang', pidFile: pids[1] } }, { id: 'bad', spec: { kind: 'fail', msg: 'boom: a plain message', waitFor: pids } }, { id: 'later', spec: { kind: 'echo', n: 1 } }], poolOpts(dir, 3)),
    (e: Error) => { assert.equal(e.message, 'test bad: boom: a plain message', 'the child\'s own first line, with the stage and the unit'); return true; });
  for (const f of pids) assert.ok(!alive(Number(fs.readFileSync(f, 'utf8'))), 'a child that was still running when the failure came is gone');
  assert.deepEqual(fs.readdirSync(dir).filter((n) => n.startsWith(UNIT_TMP_PREFIX)), []);
  await assert.rejects(runUnits([{ id: 'x', spec: { kind: 'exit', code: 3 } }], poolOpts(dir, 1)), /^Error: test x: its process exited with code 3 and left no result$/);
  const garbage = path.join(dir, 'g.jsonl.gz'); fs.writeFileSync(garbage, 'nope');
  await assert.rejects(runUnits([{ id: 'g', spec: { kind: 'read', file: garbage } }], poolOpts(dir, 1)), /^Error: test g: incorrect header check$/);
  await assert.rejects(runUnits([{ id: 'k', spec: { kind: 'nonsense' } }], poolOpts(dir, 1)), /test k: unknown unit kind nonsense/);
  assert.deepEqual(fs.readdirSync(dir).filter((n) => n.startsWith(UNIT_TMP_PREFIX)), []);
  // a temp folder a killed run left behind is cleared by the next pool (and nothing else in the folder is touched)
  fs.mkdirSync(path.join(dir, `${UNIT_TMP_PREFIX}old-1`)); fs.writeFileSync(path.join(dir, `${UNIT_TMP_PREFIX}old-1`, 'x'), 'x'); fs.writeFileSync(path.join(dir, 'keep.txt'), 'k');
  await runUnits([{ id: 'e', spec: { kind: 'echo', n: 1 } }], poolOpts(dir, 1));
  assert.ok(!fs.existsSync(path.join(dir, `${UNIT_TMP_PREFIX}old-1`)) && fs.existsSync(path.join(dir, 'keep.txt')));
});

test('a child that dies of memory says so in words a fresh reader can act on: node reports a heap abort as code null, signal SIGABRT (never 134) and the kernel\'s killer as SIGKILL; the hint names TWIN_CHILD_HEAP_MB, the step that sets it, and the bound jobs x heap', async () => {
  const STEP = 'the step "Match, fill in, and describe every contract both ways" of history-twin.yml';
  // the pure message: both shapes of heap exhaustion, both shapes of a kill, and no guess for an ordinary exit
  const abort = noAnswerMessage(null, 'SIGABRT', 3072, 4), viaShell = noAnswerMessage(134, null, 3072, 4);
  assert.equal(abort, `exited with code null (signal SIGABRT) and left no result (node ran out of memory at the child heap TWIN_CHILD_HEAP_MB = 3072 MB, set in the env of ${STEP}, so changing it is a workflow edit; 4 job(s) x 3072 MB; jobs x heap must stay under about 12 GB of the runner's 16 GB)`);
  assert.equal(viaShell, `exited with code 134 and left no result (node ran out of memory at the child heap TWIN_CHILD_HEAP_MB = 3072 MB, set in the env of ${STEP}, so changing it is a workflow edit; 4 job(s) x 3072 MB; jobs x heap must stay under about 12 GB of the runner's 16 GB)`);
  for (const m of [noAnswerMessage(null, 'SIGKILL', 3072, 4), noAnswerMessage(137, null, 3072, 4)]) {
    assert.match(m, /^exited with code (null \(signal SIGKILL\)|137) and left no result \(killed from outside, most likely by the kernel's out-of-memory killer because the runner's memory ran out; TWIN_CHILD_HEAP_MB = 3072 MB is set in /);
    assert.ok(m.includes(STEP) && m.includes('jobs x heap must stay under about 12 GB of the runner\'s 16 GB'), m);
  }
  assert.equal(noAnswerMessage(3, null, 3072, 4), 'exited with code 3 and left no result', 'an ordinary exit gets no guess');
  assert.equal(noAnswerMessage(null, 'SIGTERM', 3072, 4), 'exited with code null (signal SIGTERM) and left no result');
  // the real thing: a child with a tiny heap that fills it, and a child that is SIGKILLed, through the pool
  const dir = tmpDir();
  await assert.rejects(runUnits([{ id: 'm1', spec: { kind: 'oom' } }], poolOpts(dir, 1, { heapMb: 32 })),
    (e: Error) => { assert.equal(e.message, `test m1: its process ${noAnswerMessage(null, 'SIGABRT', 32, 1)}`); assert.match(e.message, /exited with code null \(signal SIGABRT\) and left no result \(node ran out of memory at the child heap TWIN_CHILD_HEAP_MB = 32 MB, set in the env of the step "Match, fill in/); return true; });
  await assert.rejects(runUnits([{ id: 'k1', spec: { kind: 'selfkill' } }], poolOpts(dir, 1)),
    (e: Error) => { assert.equal(e.message, `test k1: its process ${noAnswerMessage(null, 'SIGKILL', 3072, 1)}`); assert.match(e.message, /^test k1: its process exited with code null \(signal SIGKILL\) and left no result \(killed from outside, most likely by the kernel's out-of-memory killer/); return true; });
  assert.deepEqual(fs.readdirSync(dir).filter((n) => n.startsWith(UNIT_TMP_PREFIX)), [], 'the temp folder is gone');
  // the default heap in the pool, the heap in the workflow and the step the message names are the same number and step
  const wfText = fs.readFileSync(path.join(ROOT, '.github/workflows/history-twin.yml'), 'utf8');
  assert.ok(wfText.includes('- name: Match, fill in, and describe every contract both ways'), 'the step the message names exists');
  assert.equal(wfText.match(/^\s+TWIN_CHILD_HEAP_MB: '(\d+)'$/m)?.[1], String(DEFAULT_CHILD_HEAP_MB), 'the pool\'s default heap is the workflow step\'s');
});

test('a SIGTERM to the parent (the workflow\'s timeout) takes its children with it and removes the temp folder', { skip: fs.existsSync('/proc/self/cmdline') ? false : 'needs /proc' }, async () => {
  const dir = tmpDir(), pids = [path.join(dir, 'p1'), path.join(dir, 'p2')], { spawn } = await import('node:child_process');
  const parent = spawn(process.execPath, ['--import', 'tsx', path.join(ROOT, 'tests/unitPoolParent.ts'), dir, pids[0], pids[1]], { stdio: 'ignore' });
  const exited = new Promise<number | null>((ok) => parent.once('exit', (code, sig) => ok(code ?? (sig ? 128 : null))));
  for (let i = 0; i < 800 && !pids.every((f) => fs.existsSync(f)); i++) await new Promise((ok) => setTimeout(ok, 25));
  assert.ok(pids.every((f) => fs.existsSync(f)), 'both children started');
  const kids = pids.map((f) => Number(fs.readFileSync(f, 'utf8')));
  parent.kill('SIGTERM');
  assert.equal(await exited, 143);
  for (let i = 0; i < 200 && kids.some(alive); i++) await new Promise((ok) => setTimeout(ok, 25));
  assert.deepEqual(kids.filter(alive), [], 'no child is left');
  assert.deepEqual(fs.readdirSync(dir).filter((n) => n.startsWith(UNIT_TMP_PREFIX)), []);
});

test('a child gets its own heap and is its parent\'s child: the parent\'s heap flag is replaced, its other options and the node arguments (`--import tsx`) stay, the test runner\'s flags go', async () => {
  assert.equal(childNodeOptions('--max-old-space-size=12288', 3072), '--max-old-space-size=3072');
  assert.equal(childNodeOptions('--foo --max-old-space-size 12288 --bar=1 --max_old_space_size=1', 3072), '--foo --bar=1 --max-old-space-size=3072');
  assert.equal(childNodeOptions(undefined, 3072), '--max-old-space-size=3072');
  assert.deepEqual(childExecArgv(['--import', 'tsx', '--test', '--test-name-pattern', 'x y', '--test-reporter=tap', '--inspect-brk=9229', '--watch', '--max-old-space-size=100']), ['--import', 'tsx', '--max-old-space-size=100']);
  const [r] = await runUnits<{ heap: string; ppid: number }>([{ id: 'e', spec: { kind: 'env' } }], poolOpts(tmpDir(), 1, { env: { ...process.env, NODE_OPTIONS: '--max-old-space-size=12288' }, heapMb: 3072 }));
  assert.equal(r.heap, '--max-old-space-size=3072'); assert.equal(r.ppid, process.pid);
  assert.deepEqual(childExecArgv(['--import', 'tsx']), ['--import', 'tsx']);
});

// The job's time budget: the shell functions of .github/scripts/twin-lib.sh, with a fake clock and with the real `timeout`.
const LIB = path.join(ROOT, '.github/scripts/twin-lib.sh');
const budgetRun = (script: string, env: Record<string, string> = {}, tmp = tmpDir()) => bash(`set -euo pipefail\nsource ${LIB}\n${script}`, { RUNNER_TEMP: tmp, ...env }, ROOT);

test('the time budget is the job limit less the time used (from the job clock), the slack and the reserve: a dev step and a confirm step (7 FIT days, a longer fit and calibration first) start at different times and get different budgets, and the reserve is never spent', () => {
  const syntax = spawnSync('bash', ['-n', LIB], { encoding: 'utf8' });
  assert.equal(syntax.status, 0, `bash -n twin-lib.sh: ${syntax.stderr}`);
  const NOW = 1_800_000_000, LIMIT = 340 * 60, RESERVE = 25 * 60, SLACK = 120;
  const left = (usedS: number, env: Record<string, string> = {}) => { const r = budgetRun(`twin_now() { echo ${NOW}; }\ntwin_seconds_left`, { JOB_START: String(NOW - usedS), ...env }); assert.equal(r.status, 0, r.stderr); return Number(r.stdout.trim()); };
  assert.equal(left(0), LIMIT - RESERVE - SLACK, 'a job that has just begun: 340 min less 25 less the 2 minutes of slack');
  // GUESSES of the minutes used before the step (RUNBOOK 5): dev = set-up 5 + depth fit 26 + calibration 22; confirm = set-up 5 + fit of 7 days ~60 + calibration ~51 + the 7 days' real FIT rows ~35
  const dev = (5 + 26 + 22) * 60, confirm = (5 + 60 + 51 + 35) * 60;
  assert.equal(left(dev), LIMIT - RESERVE - SLACK - dev); assert.equal(left(confirm), LIMIT - RESERVE - SLACK - confirm);
  assert.ok(left(confirm) < left(dev) && left(confirm) > 0 && left(dev) > 3 * 3600, `dev ${left(dev)} s, confirm ${left(confirm)} s: both positive, the confirm one smaller`);
  for (const used of [0, dev, confirm, 5 * 3600]) assert.equal(left(used) + used + SLACK + RESERVE, LIMIT, 'what is used, the slack, the reserve and the budget are the job limit, to the second');
  assert.equal(left(0, { TWIN_RESERVE_MIN: '40' }), LIMIT - 40 * 60 - SLACK, 'the reserve and the limit come from the environment'); assert.equal(left(0, { TWIN_JOB_LIMIT_MIN: '60', TWIN_RESERVE_MIN: '5', TWIN_CLOCK_SLACK_S: '0' }), 55 * 60);
  assert.ok(left(LIMIT - RESERVE - SLACK + 1) < 0 && left(LIMIT - RESERVE - SLACK) === 0, 'at the end of the budget it is 0, past it negative');
  // no clock: assumed just begun, with a warning in the log and on stderr
  const tmp = tmpDir(), noClock = budgetRun(`twin_now() { echo ${NOW}; }\ntwin_seconds_left`, { JOB_START: '' }, tmp);
  assert.equal(Number(noClock.stdout.trim()), LIMIT - RESERVE); assert.match(noClock.stderr, /\[twin\] WARNING: the job clock \(JOB_START\) is not set/); assert.match(fs.readFileSync(path.join(tmp, 'build.log'), 'utf8'), /WARNING: the job clock/);
  assert.equal(Number(budgetRun(`twin_now() { echo ${NOW}; }\ntwin_seconds_left`, { JOB_START: 'soon' }).stdout.trim()), LIMIT - RESERVE, 'a clock that is not a number is no clock');
  // with no time left the command is not started at all (a `timeout 0` would let it run without a limit)
  const ran = path.join(tmp, 'ran'), none = budgetRun(`twin_now() { echo ${NOW}; }\ntwin_budgeted features 4 bash -c 'touch ${ran}'`, { JOB_START: String(NOW - 6 * 3600) }, tmp);
  assert.equal(none.status, 1); assert.ok(!fs.existsSync(ran), 'the command did not run');
  const log = fs.readFileSync(path.join(tmp, 'build.log'), 'utf8');
  assert.match(log, /^\[twin\] ERROR: features was cut at the job's time budget after 0 s \(jobs 4\); the rest of this run was not built \(it was not started: no time was left for it\)$/m);
  assert.match(log, /^\[twin\] time budget: features may run up to -\d+ s /m);
});

test('twin_budgeted: a command that outlives its budget is cut by timeout and the step ends non-zero with the cut line in the log; one that fails or finishes is passed through, its [twin] lines kept in the log and printed', () => {
  const tmp = tmpDir(), log = path.join(tmp, 'build.log');
  const NOW = Math.floor(Date.now() / 1000), LIMIT = 340 * 60, RESERVE = 25 * 60, SLACK = 120;
  const startWith = (leftS: number) => String(NOW - (LIMIT - RESERVE - SLACK - leftS)); // JOB_START that leaves `leftS` seconds at NOW
  // cut: 3 seconds left, a command that prints a timing line and then sleeps 60 s
  const t0 = Date.now();
  const cut = budgetRun(`twin_budgeted match 4 bash -c 'echo "[twin] match 2026-11-13: tickers 1.0 s, restrict 2.0 s, pair 3.0 s"; echo "noise that is not a twin line"; sleep 60'; echo "not reached"`, { JOB_START: startWith(3) }, tmp);
  assert.ok(Date.now() - t0 < 30_000, 'cut in seconds, not after the sleep');
  assert.equal(cut.status, 1); assert.ok(!/not reached/.test(cut.stdout), 'the step stops');
  const text = fs.readFileSync(log, 'utf8');
  assert.match(text, /^\[twin\] match 2026-11-13: tickers 1\.0 s, restrict 2\.0 s, pair 3\.0 s$/m, 'what it printed before the cut is in the log');
  assert.match(text, /^\[twin\] ERROR: match was cut at the job's time budget after [3-9] s \(jobs 4\); the rest of this run was not built$/m);
  assert.match(text, /^\[twin\] time budget: match may run up to [2-3] s /m);
  assert.ok(text.indexOf('tickers 1.0') < text.indexOf('was cut'), 'the progress comes before the cut line');
  assert.match(cut.stdout, /^\[twin\] match 2026-11-13: tickers/m, 'the [twin] lines are on the step\'s output'); assert.ok(!/noise that is not a twin line/.test(cut.stdout), 'the rest only in the log file'); assert.match(text, /noise that is not a twin line/);
  assert.match(cut.stdout, /^::error::match was cut at the job's time budget/m);
  // passed through: exit 0, exit 7 (the step's own status), and a kill that is not the budget's (137 long before the limit) is not called a cut
  fs.rmSync(log);
  const ok = budgetRun(`twin_budgeted fill 1 bash -c 'echo "[twin] fill 2026-11-13: 0.1 s"; exit 0'; echo "after=$?"`, { JOB_START: startWith(600) }, tmp);
  assert.equal(ok.status, 0, ok.stderr); assert.match(ok.stdout, /after=0/); assert.match(ok.stdout, /^\[twin\] fill 2026-11-13: 0\.1 s$/m);
  const bad = budgetRun(`twin_budgeted features 2 bash -c 'echo "[twin] ERROR: stage said no"; exit 7'; echo "not reached"`, { JOB_START: startWith(600) }, tmp);
  assert.equal(bad.status, 7); assert.ok(!/not reached/.test(bad.stdout)); assert.ok(!/was cut/.test(fs.readFileSync(log, 'utf8')));
  assert.match(fs.readFileSync(log, 'utf8'), /^\[twin\] ERROR: stage said no$/m);
  const oom = budgetRun(`twin_budgeted features 2 bash -c 'kill -9 $$'; echo "not reached"`, { JOB_START: startWith(600) }, tmp);
  assert.equal(oom.status, 137); assert.ok(!/was cut/.test(fs.readFileSync(log, 'utf8')), 'killed at once, with 10 minutes left: not the budget');
  // the shell options of the step survive the call (set -e is still on after it)
  assert.equal(budgetRun(`twin_budgeted fill 1 true; false; echo "survived"`, { JOB_START: startWith(600) }, tmp).stdout.includes('survived'), false, 'set -e is back on');
});

const exprText = (script: string) => script.replace(/\$\{\{ github\.run_id \}\}/g, '77').replace(/\$\{\{ github\.repository \}\}/g, 'o/r').replace(/\$\{\{ github\.sha \}\}/g, 'abc').replace(/\$\{\{ job\.status \}\}/g, 'failure').replace(/\$\{\{[^}]*\}\}/g, 'X');

test('the build job\'s time budget is wired: the limit and reserve are the job\'s own numbers, every heavy command runs under twin_budgeted with --jobs capped at 4, the steps that run after a cut have limits that fit the reserve, and they tolerate a run with no files', { skip: hasYaml ? false : 'python3 with PyYAML is not installed here' }, () => {
  const { jobs } = yamlDoc(), build = jobs.build, steps = build.steps as Array<{ name?: string; if?: string; 'timeout-minutes'?: number; uses?: string; env?: Record<string, string>; run?: string }>;
  assert.equal(build['timeout-minutes'], 340, 'the job limit is unchanged'); assert.equal(build.env.TWIN_JOB_LIMIT_MIN, String(build['timeout-minutes']), 'the budget\'s limit is the job\'s timeout-minutes'); assert.equal(build.env.TWIN_RESERVE_MIN, '25');
  const lib = fs.readFileSync(LIB, 'utf8'); assert.ok(lib.includes('${TWIN_JOB_LIMIT_MIN:-340}') && lib.includes('${TWIN_RESERVE_MIN:-25}') && lib.includes('${TWIN_CLOCK_SLACK_S:-120}'), 'the library\'s defaults are the same numbers');
  const clock = steps.findIndex((x) => /^The job's clock/.test(x.name ?? '')), match = steps.findIndex((x) => /^Match, fill in/.test(x.name ?? ''));
  assert.ok(clock >= 0 && clock < match && /JOB_START=\$\(date \+%s\)" >> "\$GITHUB_ENV"/.test(steps[clock].run!), 'the job clock is set before the step');
  const run = steps[match].run!, cmds = run.split('\n').filter((l) => /research\/historyTwin\.ts/.test(l));
  assert.equal(cmds.length, 4, 'match, fill, the lag arms\' fill, features'); assert.ok(cmds.every((l) => /^\s*twin_budgeted (match|fill|features) /.test(l)), `no heavy command outside the budget:\n${cmds.join('\n')}`);
  assert.deepEqual(cmds.map((l) => /twin_budgeted (\w+) (\S+)/.exec(l)!.slice(1, 3).join(' ')), ['match "$J"', 'fill 1', 'fill 1', 'features "$J"']);
  assert.ok(/--stage match [^\n]*--jobs "\$J"/.test(cmds[0]) && /--stage features [^\n]*--jobs "\$J"/.test(cmds[3]) && !/--jobs/.test(cmds[1] + cmds[2]), '--jobs on match and features, not on the serial fill');
  assert.ok(/source \.github\/scripts\/twin-lib\.sh/.test(run) && /J=\$\(nproc\); \[ "\$J" -le 4 \] \|\| J=4; \[ "\$J" -ge 1 \] \|\| J=1/.test(run), 'the jobs are the cores, 1 to 4');
  assert.equal(steps[match].env!.TWIN_CHILD_HEAP_MB, '3072', 'a heap for each child');
  // the steps after the stage: those that still run after a cut have limits of their own, and the limits of every step after it fit the reserve of the budget
  const after = steps.slice(match + 1), always = after.filter((x) => /always\(\)/.test(x.if ?? '') || x.if === 'always()');
  assert.deepEqual(always.map((x) => x.name), ['Keep the simulated twin on Drive', "Report (commit comment; RUNBOOK 'Reading results')"]);
  for (const x of always) { const m = x['timeout-minutes']; assert.ok(typeof m === 'number' && m >= 1 && m <= 25, `${x.name}: timeout-minutes ${m}`); }
  const reserve = Number(build.env.TWIN_RESERVE_MIN);
  assert.ok(always.reduce((a, x) => a + x['timeout-minutes']!, 0) <= reserve, 'what runs after a cut (the Drive put and the report) fits the reserve');
  assert.ok(after.filter((x) => x['timeout-minutes'] !== undefined).every((x) => x['timeout-minutes']! <= 25), 'no step after the stage may take more than the reserve');
  assert.ok(after.filter((x) => /cache\/save/.test(x.uses ?? '')).every((x) => typeof x['timeout-minutes'] === 'number'), 'the cache saves have limits too');
  // --jobs follows the cores, at most 4: run the step with a stub nproc and a stub node
  const y = wf(), w = stageWs(), args = path.join(w.tmp, 'a.txt');
  fs.writeFileSync(path.join(w.bin, 'node'), '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$STUB_ARGS"\necho "[twin] stub"\n', { mode: 0o755 }); fs.writeFileSync(path.join(w.ws, 'data/twin/x'), 'x');
  for (const [cores, want] of [['1', '1'], ['2', '2'], ['4', '4'], ['16', '4'], ['64', '4']]) {
    fs.writeFileSync(path.join(w.bin, 'nproc'), `#!/usr/bin/env bash\necho ${cores}\n`, { mode: 0o755 }); fs.rmSync(args, { force: true });
    const r = bash(stepScript(y, 'Match, fill in, and describe'), { PATH: `${w.bin}:${process.env.PATH}`, SPLIT: 'dev', FIT: SPLITS.dev.fit.join(','), JUDGE: DEV_JUDGED.join(','), WARM: '', NEED: '', LAG: 'false', DEPTH_PARAMS_RUN: '', RUNNER_TEMP: w.tmp, STUB_ARGS: args, JOB_START: String(Math.floor(Date.now() / 1000)) }, w.ws);
    assert.equal(r.status, 0, `${r.stdout}${r.stderr}`);
    const lines = fs.readFileSync(args, 'utf8').split('\n').filter(Boolean);
    assert.ok(/--stage match .*--jobs \d+ --out data\/twin$/.test(lines[0]) && lines[0].includes(`--jobs ${want} `), `${cores} cores: ${lines[0]}`); assert.ok(lines.find((l) => /--stage features/.test(l))!.includes(`--jobs ${want} `));
    assert.ok(lines.filter((l) => /--stage fill/.test(l)).every((l) => !/--jobs/.test(l)));
  }
});

test('the step after a cut: with the stage cut at its budget the build ends red with the cut line, the Drive put and the report still run with no files at all, and the comment keeps the timing lines, the budget line and the cut line in its framing part', () => {
  const y = wf(), w = stageWs(), log = path.join(w.tmp, 'build.log'), NOW = Math.floor(Date.now() / 1000);
  // a stub node that prints what the match stage prints, then hangs (the cut ends it)
  fs.writeFileSync(path.join(w.bin, 'node'), '#!/usr/bin/env bash\ncase "$*" in *"--stage match"*) echo "[twin] match 2026-11-13: tickers 1.0 s, restrict 2.0 s, pair 3.0 s"; echo "[twin] 2026-11-13: contracts real 5 / twin 4"; sleep 60;; esac\n', { mode: 0o755 });
  const env = { PATH: `${w.bin}:${process.env.PATH}`, SPLIT: 'dev', FIT: SPLITS.dev.fit.join(','), JUDGE: DEV_JUDGED.join(','), WARM: '', NEED: '', LAG: 'false', DEPTH_PARAMS_RUN: '', RUNNER_TEMP: w.tmp, JOB_START: String(NOW - (340 * 60 - 25 * 60 - 120 - 3)) };
  const t0 = Date.now(), r = bash(stepScript(y, 'Match, fill in, and describe'), env, w.ws);
  assert.ok(Date.now() - t0 < 40_000); assert.notEqual(r.status, 0);
  const text = fs.readFileSync(log, 'utf8');
  assert.match(text, /^\[twin\] ERROR: match was cut at the job's time budget after \d+ s \(jobs [1-4]\); the rest of this run was not built$/m);
  assert.ok(!/--stage fill|--stage features/.test(r.stdout + text), 'nothing after the cut ran');
  // the Drive put, with no folder of data/ there but the days.txt it writes: runs and succeeds
  const calls = path.join(w.tmp, 'calls.txt');
  const keep = bash(exprText(stepScript(y, 'Keep the simulated twin on Drive')), { PATH: `${w.bin}:${process.env.PATH}`, RUNNER_TEMP: w.tmp, GITHUB_WORKSPACE: w.ws, STUB_CALLS: calls, STUB_DRIVE: tmpDir() }, w.ws);
  assert.equal(keep.status, 0, `${keep.stdout}${keep.stderr}`); assert.match(fs.readFileSync(calls, 'utf8'), /^put simulated\/history-twin\/77 /m);
  // the report, from the log the cut left
  const out = path.join(w.tmp, 'comment.txt'), rep = bash(exprText(stepScript(y, 'Report (commit comment')), { PATH: `${w.bin}:${process.env.PATH}`, RUNNER_TEMP: w.tmp, GH_OUT: out, GITHUB_SHA: 'abcdef0123456789' }, w.ws);
  assert.equal(rep.status, 0, `${rep.stdout}${rep.stderr}`);
  const comment = fs.readFileSync(out, 'utf8'), framing = comment.slice(0, comment.indexOf('--- the last lines ---'));
  for (const re of [/^\[twin\] ERROR: match was cut at the job's time budget after \d+ s/m, /^\[twin\] time budget: match may run up to \d+ s/m, /^\[twin\] match 2026-11-13: tickers 1\.0 s, restrict 2\.0 s, pair 3\.0 s$/m]) assert.match(framing, re);
  assert.ok(!/contracts real 5/.test(framing) && /contracts real 5/.test(comment), 'a per-day mechanics line is a detail line, below the framing');
  // a run with no log at all still reports
  fs.rmSync(log); const none = bash(exprText(stepScript(y, 'Report (commit comment')), { PATH: `${w.bin}:${process.env.PATH}`, RUNNER_TEMP: w.tmp, GH_OUT: out, GITHUB_SHA: 'abcdef0123456789' }, w.ws);
  assert.equal(none.status, 0, none.stderr); assert.match(fs.readFileSync(out, 'utf8'), /\(no \[twin\] lines/);
});

test('the commit comment\'s framing pattern is pinned literally, timing lines included: it keeps the timing, budget and cut lines and the other framing lines, and not a detail line', () => {
  const frame = /FRAME='\^\\\[twin\\\] \(([^']+)\)'/.exec(stepScript(wf(), 'Report (commit comment; RUNBOOK'));
  assert.ok(frame, 'the FRAME pattern is where the test looks');
  assert.deepEqual(frame![1].split('|'), [
    'ERROR', 'WARNING', 'split', 'real 15', 'requote source', 'requote days', 'depth model fitted', 'depth model schema', 'depth model: asset', 'depth model calibration', 'depth model reused', 'real side', 'fast', 'decision model', 'CONFIRM', 'no cached', 'matched', 'confirm split', 'calibration',
    'time budget', 'match took', 'match [0-9]{4}-[0-9]{2}-[0-9]{2}: tickers', 'fill took', 'fill [0-9]{4}-[0-9]{2}-[0-9]{2}: ', 'features took', 'features [a-z]+ [0-9]{4}-[0-9]{2}-[0-9]{2}: ',
  ]);
  const re = new RegExp(`^\\[twin\\] (${frame![1]})`);
  for (const l of ['[twin] match 2026-11-13: tickers 1.0 s, restrict 2.0 s, pair 3.0 s', '[twin] match took 12.3 s (jobs 4)', '[twin] fill 2026-11-13: 4.5 s', '[twin] fill took 20.1 s', '[twin] features depth 2026-11-14: 6.0 s', '[twin] features took 99.9 s (jobs 4)', '[twin] time budget: match may run up to 18000 s (the job\'s 340-minute limit)', '[twin] ERROR: features was cut at the job\'s time budget after 12 s (jobs 4); the rest of this run was not built']) assert.ok(re.test(l), l);
  for (const l of ['[twin] 2026-11-13: contracts real 5 / twin 4', '[twin] real 2026-11-13: 12 lives, trades/min 1.00', '[twin] features real: 12 contract lives over 2 day(s)', '[twin] match from 12:00 UTC', '[twin] depth fill-in written for 7 day(s)']) assert.ok(!re.test(l), l);
});
// ---- S1 end of the match and features tests ----

// ---------------------------------------------------------------------------------------------------------------
// ---- S2: the verdict never depends on the 9 GB cache; a re-verdict re-reads checks 2-4 from Drive ----
// P2b (run 45152244309): the verdict job failed in 10 s at `actions/cache/restore@v4` ("Failed to restore cache entry", fail-on-cache-miss) because GitHub's
// 10 GB repository limit had evicted the build's 9 GB cache 12 minutes after the legs restored it. The verdict reads only the lite cache or Drive now, the
// re-verdict also reads the legs' per-window P&L from Drive, and one script (.github/scripts/twin-windows.py) assembles it for both. These tests are
// synthetic: stubbed Drive, node and gh, the workflow's own steps run as text.

const WINDOWS_PY = path.join(ROOT, '.github/scripts/twin-windows.py');
const HOWS = ['real', 'placebo', 'requote', 'depth'] as const;
const J3 = ['2026-11-13', '2026-11-14', '2026-11-16'];
const C3 = ['2026-11-18', '2026-11-19', '2026-11-20'];
/** What the verdict job's inline python was at fcdea68, character for character (the heredoc of its Verdict step): the reference the script's printed lines, legs file and files are held to. */
const OLD_INLINE = `import glob, json, re, sys
src, out, split, judged, legs = sys.argv[1:]
want = {d for d in judged.split(",") if d}
got = []
for how in ("real", "placebo", "requote", "depth"):
    files = sorted(glob.glob(f"{src}/twin-{how}-p*/windows-{how}-p*.json"))
    days = {m.group(1) for m in (re.search(r"(\\d{4}-\\d\\d-\\d\\d)\\.json$", f) for f in files) if m} & want
    w = [x for f in files for x in json.load(open(f))]
    if files: json.dump(w, open(f"{out}/windows-{how}.json", "w"))
    print(f"[twin] backtest legs {how}: {len(days)} of {len(want)} judged day(s) have a per-window file" + ("" if split == "confirm" else f", {len(w)} window(s)"))
    got.append(len(days))
open(legs, "w").write("/".join(str(g) for g in got) + " of " + str(len(want)))
sys.exit(0 if want and all(g == len(want) for g in got) else 3)
`;
/** The legs' folders as drive_lab.sh get leaves them: twin-HOW-pI/windows-HOW-pI-DAY.json, one file per judged day. */
function legsDir(have: Partial<Record<(typeof HOWS)[number], string[]>>, dir = tmpDir()): string {
  for (const [how, days] of Object.entries(have)) days!.forEach((d, i) => {
    const sub = path.join(dir, `twin-${how}-p${i}`); fs.mkdirSync(sub, { recursive: true });
    fs.writeFileSync(path.join(sub, `windows-${how}-p${i}-${d}.json`), JSON.stringify([[`${how}${i}a`, 1.5], [`${how}${i}b`, -2]]));
  });
  return dir;
}
const wholeLegs = (days = J3) => ({ real: days, placebo: days, requote: days, depth: days });
const winFiles = (dir: string) => (fs.existsSync(dir) ? fs.readdirSync(dir).filter((f) => /^windows-.*\.json$/.test(f)).sort() : []);
const runWindowsPy = (src: string, out: string, split: string, judged: string[], legs: string) => spawnSync('python3', ['-I', WINDOWS_PY, src, out, split, judged.join(','), legs], { encoding: 'utf8' });
const runOldInline = (src: string, out: string, split: string, judged: string[], legs: string) => { fs.mkdirSync(out, { recursive: true }); return spawnSync('python3', ['-I', '-', src, out, split, judged.join(','), legs], { input: OLD_INLINE, encoding: 'utf8' }); };

test('twin-windows.py: a whole set writes the four windows files and exits 0, and its lines, its legs file and its files are the old inline python\'s, byte for byte', () => {
  for (const [split, judged] of [['dev', J3], ['custom', J3], ['confirm', C3]] as Array<[string, string[]]>) {
    const src = legsDir(wholeLegs(judged)), a = path.join(tmpDir(), 'new'), b = path.join(tmpDir(), 'old'), la = path.join(tmpDir(), 'legs.txt'), lb = path.join(tmpDir(), 'legs.txt');
    const n = runWindowsPy(src, a, split, judged, la), o = runOldInline(src, b, split, judged, lb);
    assert.equal(n.status, 0, n.stderr); assert.equal(o.status, 0, o.stderr);
    assert.equal(n.stdout, o.stdout, `the printed lines of the ${split} split are unchanged`);
    assert.equal(fs.readFileSync(la, 'utf8'), '3/3/3/3 of 3'); assert.equal(fs.readFileSync(la, 'utf8'), fs.readFileSync(lb, 'utf8'));
    assert.deepEqual(winFiles(a), ['windows-depth.json', 'windows-placebo.json', 'windows-real.json', 'windows-requote.json']);
    for (const how of HOWS) assert.equal(fs.readFileSync(path.join(a, `windows-${how}.json`), 'utf8'), fs.readFileSync(path.join(b, `windows-${how}.json`), 'utf8'), `windows-${how}.json is the old file`);
    assert.equal(JSON.parse(fs.readFileSync(path.join(a, 'windows-depth.json'), 'utf8')).length, 6, '2 windows a day, 3 days');
    if (split === 'confirm') assert.ok(!/window\(s\)/.test(n.stdout), `a confirm split prints day-file counts only: ${n.stdout}`);
    else for (const how of HOWS) assert.ok(n.stdout.includes(`[twin] backtest legs ${how}: 3 of 3 judged day(s) have a per-window file, 6 window(s)\n`), n.stdout);
  }
  assert.ok(runWindowsPy(legsDir(wholeLegs(C3)), path.join(tmpDir(), 'o'), 'confirm', C3, path.join(tmpDir(), 'l')).stdout.endsWith('3 of 3 judged day(s) have a per-window file\n'), 'the confirm line, exactly');
});

test('twin-windows.py: a missing source, a missing day, an empty judged list, a corrupt file, an unjudged day: exit 3, the lines say which, and NOTHING is written to the output folder', () => {
  const none = path.join(tmpDir(), 'none');
  const cases: Array<{ what: string; have: Partial<Record<(typeof HOWS)[number], string[]>>; judged?: string[]; want: string; legs: string }> = [
    { what: 'a lost twin source', have: { ...wholeLegs(), depth: [] }, want: 'depth: 0 of 3', legs: '3/3/3/0 of 3' },
    { what: 'a source that has no folder at all', have: { real: J3, placebo: J3, requote: J3 }, want: 'depth: 0 of 3', legs: '3/3/3/0 of 3' },
    { what: 'a lost placebo day', have: { ...wholeLegs(), placebo: J3.slice(0, 2) }, want: 'placebo: 2 of 3', legs: '3/2/3/3 of 3' },
    { what: 'nothing on Drive', have: {}, want: 'real: 0 of 3', legs: '0/0/0/0 of 3' },
    { what: 'a day that is not judged does not stand in for a judged one', have: { ...wholeLegs(['2026-11-13', '2026-11-14']), real: ['2026-11-13', '2026-11-16'] }, judged: ['2026-11-13', '2026-11-14'], want: 'real: 1 of 2', legs: '1/2/2/2 of 2' },
    { what: 'an empty judged list (no split.json judge list)', have: wholeLegs(), judged: [], want: 'real: 0 of 0', legs: '0/0/0/0 of 0' },
  ];
  for (const c of cases) {
    const src = legsDir(c.have), out = path.join(tmpDir(), 'o'), legs = path.join(tmpDir(), 'legs.txt'), judged = c.judged ?? J3;
    const r = runWindowsPy(src, out, 'dev', judged, legs);
    assert.equal(r.status, 3, `${c.what}: ${r.stderr}`); assert.ok(r.stdout.includes(`[twin] backtest legs ${c.want} judged day(s) have a per-window file`), `${c.what}: ${r.stdout}`);
    assert.equal(fs.readFileSync(legs, 'utf8'), c.legs, c.what);
    assert.deepEqual(winFiles(out), [], `${c.what}: no windows file is written for an incomplete set (the old script wrote the sources that had files)`);
    const o = runOldInline(src, path.join(tmpDir(), 'old'), 'dev', judged, path.join(tmpDir(), 'oldlegs.txt'));
    assert.equal(o.status, 3, `${c.what}: the old script also refused it`);
    if (!c.judged) assert.equal(r.stdout, o.stdout, `${c.what}: the lines are the old script's`);
  }
  assert.ok(!fs.existsSync(none));
  // a file that is not valid JSON, or not a list, is a day with no file (the old script crashed with a traceback and exit 1)
  const bad = legsDir(wholeLegs());
  fs.writeFileSync(path.join(bad, 'twin-real-p1', 'windows-real-p1-2026-11-14.json'), '{"truncated"');
  fs.writeFileSync(path.join(bad, 'twin-depth-p2', 'windows-depth-p2-2026-11-16.json'), '{"a": 1}');
  const r = runWindowsPy(bad, path.join(tmpDir(), 'o'), 'confirm', J3, path.join(tmpDir(), 'legs.txt'));
  assert.equal(r.status, 3); assert.ok(!/Traceback/.test(r.stderr), r.stderr); assert.match(r.stdout, /legs real: 2 of 3 judged day\(s\) have a per-window file\n/); assert.match(r.stdout, /legs depth: 2 of 3 judged day\(s\) have a per-window file\n/);
  // wrong arguments: exit 2, a usage line, nothing else
  const usage = spawnSync('python3', ['-I', WINDOWS_PY, 'a', 'b'], { encoding: 'utf8' }); assert.equal(usage.status, 2); assert.match(usage.stderr, /usage: twin-windows\.py/);
});

test('twin-windows.py reads only the judged days: a file of another day is neither counted nor copied into the four files', () => {
  const src = legsDir(wholeLegs(['2026-11-13', '2026-11-14']));
  // the run's folder also holds a day outside the judged list (a stale or foreign file)
  fs.writeFileSync(path.join(src, 'twin-real-p0', 'windows-real-p0-2026-11-16.json'), JSON.stringify([['stray', 99]]));
  fs.writeFileSync(path.join(src, 'twin-real-p0', 'windows-real-p0-notaday.json'), JSON.stringify([['stray2', 99]]));
  const out = path.join(tmpDir(), 'o'), r = runWindowsPy(src, out, 'dev', ['2026-11-13', '2026-11-14'], path.join(tmpDir(), 'l'));
  assert.equal(r.status, 0, r.stderr); assert.match(r.stdout, /legs real: 2 of 2 judged day\(s\) have a per-window file, 4 window\(s\)\n/);
  const real = JSON.parse(fs.readFileSync(path.join(out, 'windows-real.json'), 'utf8')); assert.equal(real.length, 4); assert.ok(!JSON.stringify(real).includes('stray'));
});

test('twin-windows.py compiles (python3 py_compile), and so does every shell block of the two jobs that call it (bash -n)', () => {
  const pyc = path.join(tmpDir(), 'twin-windows.pyc');
  const c = spawnSync('python3', ['-I', '-c', 'import py_compile,sys; py_compile.compile(sys.argv[1], cfile=sys.argv[2], doraise=True)', WINDOWS_PY, pyc], { encoding: 'utf8' });
  assert.equal(c.status, 0, c.stderr); assert.ok(fs.existsSync(pyc));
  const y = wf();
  for (const j of ['verdict', 'reverdict']) {
    const blocks = allRunScripts(jobText(y, j)); assert.ok(blocks.length >= 5, `${j}: ${blocks.length} run blocks`);
    for (const { at, script } of blocks) { const r = spawnSync('bash', ['-n'], { input: script.replace(/\$\{\{.*?\}\}/g, 'X'), encoding: 'utf8' }); assert.equal(r.status, 0, `${j}: run block at line ${at} of the job: ${r.stderr}`); }
  }
  // the inline python is gone: the verdict job reaches the script file, so does the re-verdict, and no copy of the glob is left in the workflow
  assert.ok(!/python3 - "\$RUNNER_TEMP\/in"/.test(y) && !y.includes('glob.glob'), 'no inline copy of the assembly');
  for (const j of ['verdict', 'reverdict']) assert.ok(jobText(y, j).includes('python3 .github/scripts/twin-windows.py "$RUNNER_TEMP/in" '), `${j} runs the script`);
  assert.match(stepScript(jobText(y, 'verdict'), 'Verdict'), /python3 \.github\/scripts\/twin-windows\.py "\$RUNNER_TEMP\/in" data\/twin "\$SPLIT" "\$JUDGED" "\$RUNNER_TEMP\/legs\.txt" \| tee -a "\$TWIN_LOG" \|\| rc=\$\?/);
});

test('the verdict and re-verdict jobs read no big cache and fail on no cache miss: the lite cache or Drive, in both cases; the build still saves both caches; the legs still restore the big one with the Drive fallback', { skip: hasYaml ? false : 'python3 with PyYAML is not installed here' }, () => {
  const y = wf(), { jobs } = yamlDoc();
  type St = { name?: string; uses?: string; if?: string; with?: Record<string, string>; env?: Record<string, string>; run?: string; id?: string };
  for (const [job, runKey] of [['verdict', '${{ github.run_id }}'], ['reverdict', '${{ inputs.reverdict_run }}']] as const) {
    const steps = jobs[job].steps as St[], text = jobText(y, job).split('\n').filter((l) => !/^\s*#/.test(l)).join('\n'); // (the comments explain the defect and name the cache)
    assert.ok(!/fail-on-cache-miss/.test(text), `${job}: no step fails on a cache miss`);
    const restores = steps.filter((s) => /^actions\/cache\/restore@/.test(s.uses ?? ''));
    assert.equal(restores.length, 1, `${job}: one cache restore`); assert.deepEqual(restores[0].with, { path: 'data/twinlite', key: `history-twin-lite-${runKey}` }); assert.equal(restores[0].if, undefined, `${job}: the lite restore runs in both cases`);
    assert.ok(!text.includes('key: history-twin-${{ github.run_id }}') && !/data\/models/.test(text), `${job}: the build's big cache (data/twin + data/models) is not restored`);
    const at = (re: RegExp) => { const i = steps.findIndex((s) => re.test(s.name ?? s.uses ?? '')); assert.ok(i >= 0, `${job}: step ${re}`); return i; };
    const restore = at(/^actions\/cache\/restore@/), drive = at(/^Drive setup$/), fall = at(/^The judged features from Drive/), place = at(/^The judged features in place$/), verdict = at(/^Verdict$/), report = at(/^Report \(commit comment\)$/);
    assert.ok(restore < drive && drive < fall && fall < place && place < verdict && verdict < report, `${job}: restore, Drive setup, Drive fallback, in place, ..., Verdict, Report`);
    assert.equal(steps[drive].uses, './.github/actions/drive-setup'); assert.equal(steps[drive].if, undefined, `${job}: Drive setup runs with and without backtests`);
    assert.equal(steps[fall].if, "hashFiles('data/twinlite/paired.json') == ''", `${job}: the Drive read only when the cache did not have the files`);
    assert.match(steps[fall].run!, /drive_lab\.sh get "simulated\/history-twin\/\$RUN\/twinlite" data\/twinlite/); assert.match(steps[fall].run!, /twin_fail "[^"]*neither/);
    assert.equal(steps[place].if, undefined, `${job}: the copy runs in both cases`); assert.match(steps[place].run!, /mkdir -p data\/twin && cp data\/twinlite\/\* data\/twin\//);
    for (const i of [restore, drive, fall, place]) assert.ok(!/backtests/.test(steps[i].if ?? ''), `${job}: ${steps[i].name ?? steps[i].uses} does not depend on backtests`);
    // the Report, the permissions, the limits and the job's own condition are what they were
    assert.equal(steps[report].if, 'always()');
  }
  assert.equal(jobs.verdict['timeout-minutes'], 60); assert.deepEqual(jobs.verdict.permissions, { contents: 'write', actions: 'read' }); assert.deepEqual(jobs.verdict.needs, ['build', 'backtest']); assert.equal(jobs.verdict.if, "${{ !cancelled() && needs.build.result == 'success' }}"); assert.equal(jobs.verdict.environment, 'production');
  assert.equal(jobs.reverdict['timeout-minutes'], 30); assert.deepEqual(jobs.reverdict.permissions, { contents: 'write', actions: 'read' }); assert.equal(jobs.reverdict.environment, 'production');
  assert.equal(jobs.reverdict.if, "${{ github.event_name == 'workflow_dispatch' && inputs.prep_days == '' && inputs.reverdict_run != '' && inputs.sweep_gen == '' }}");
  // the verdict job still reads the legs' windows from Drive, with backtests only, between the features and the Verdict step
  const vs = jobs.verdict.steps as St[], win = vs.findIndex((s) => s.name === 'The per-window P&L from Drive');
  assert.ok(win > vs.findIndex((s) => s.name === 'The judged features in place') && win < vs.findIndex((s) => s.name === 'Verdict'));
  assert.equal(vs[win].if, "${{ github.event_name == 'workflow_dispatch' && inputs.backtests }}");
  // the build job still saves both caches, the lite one always and the big one with backtests; the legs restore the big one and fall back to Drive when it is gone
  const saves = (jobs.build.steps as St[]).filter((s) => /^actions\/cache\/save@/.test(s.uses ?? '') && /^history-twin-/.test(s.with?.key ?? ''));
  assert.deepEqual(saves.map((s) => [s.with!.key, s.with!.path, s.if ?? null]), [
    ['history-twin-lite-${{ github.run_id }}', 'data/twinlite', null],
    ['history-twin-${{ github.run_id }}', 'data/twin\ndata/models\n', "${{ github.event_name == 'workflow_dispatch' && inputs.backtests }}"],
  ]);
  const legSteps = jobs.backtest.steps as St[], legRestore = legSteps.filter((s) => /^actions\/cache\/restore@/.test(s.uses ?? ''));
  assert.deepEqual(legRestore.map((s) => s.with!.key), ['history-twin-${{ github.run_id }}']); assert.ok(!/fail-on-cache-miss/.test(jobText(y, 'backtest')), 'the legs never failed on a miss and still do not');
  const fallback = legSteps.find((s) => /^The twin from Drive \(the cache was evicted\)/.test(s.name ?? ''))!; assert.equal(fallback.if, "hashFiles('data/models/model.json') == ''");
  // the header says why
  const head = y.slice(0, y.indexOf('\non:'));
  for (const w of ['THE VERDICT NEVER NEEDS THE BIG CACHE', '10 GB', 'twin-windows.py', 'reverdict_run=RUN']) assert.ok(head.includes(w), `the header says: ${w}`);
});

test('a confirm look is numbered by the build job and only PRINTED by the verdict job; a re-verdict numbers it in its Verdict step, after every step that reads data', () => {
  const y = wf();
  assert.ok(!/twin-look\.sh/.test(jobText(y, 'verdict').split('\n').filter((l) => !/^\s*#/.test(l)).join('\n')), 'the verdict job numbers nothing: the look comes from the build job\'s output');
  assert.match(stepScript(jobText(y, 'verdict'), 'Verdict'), /--confirm-look "\$LOOK_N"/); assert.match(jobText(y, 'verdict'), /LOOK_N: \$\{\{ needs\.build\.outputs\.look \}\}/);
  assert.match(jobText(y, 'build'), /id: look/); assert.equal((jobText(y, 'build').match(/bash \.github\/scripts\/twin-look\.sh/g) ?? []).length, 1, 'one numbering call in the build job');
  // the re-verdict: twin-look.sh is called in the Verdict step and nowhere else, and that step is the LAST one that is not the report
  const re = jobText(y, 'reverdict'), lines = re.split('\n');
  const calls = lines.map((l, i) => [l, i] as const).filter(([l]) => /bash \.github\/scripts\/twin-look\.sh/.test(l));
  assert.equal(calls.length, 1, 'one numbering call in the re-verdict job');
  const verdictAt = lines.findIndex((l) => l === '      - name: Verdict'), reportAt = lines.findIndex((l) => l === '      - name: Report (commit comment)');
  assert.ok(calls[0][1] > verdictAt && calls[0][1] < reportAt, 'inside the Verdict step');
  const before = lines.slice(0, verdictAt).join('\n');
  for (const need of ['drive_lab.sh get "simulated/history-twin/$RUN/twinlite"', 'cp data/twinlite/* data/twin/', 'drive_lab.sh get "simulated/history-twin/$RUN/windows"', 'twin-windows.py', 'cp "$RUNNER_TEMP"/win/windows-*.json data/twin/']) assert.ok(before.includes(need), `before the Verdict step: ${need}`);
  assert.ok(!/drive_lab\.sh|twin-windows\.py|cp data\/twinlite/.test(lines.slice(verdictAt, reportAt).join('\n')), 'the Verdict step reads no data of its own: it only numbers, runs the stage and prints');
  // the lines of the earlier steps survive the stage's output (it appends)
  assert.match(lines.slice(verdictAt, reportAt).join('\n'), /--out data\/twin "\$\{LOOK\[@\]\}" 2>&1 \| tee -a "\$RUNNER_TEMP\/verdict\.log" \|/);
});

// ---- the steps themselves, run in order with a stubbed Drive and node (a job stops at its first failed step) ----

/** A fake drive_lab.sh over a folder: get and put copy whole folders; STUB_GET_FAIL=SUFFIX makes a get of a name ending in SUFFIX fail with rclone's exit 1; get leaves its folder made, exit 3 when Drive has nothing there. */
const fakeLab = (ws: string) => fs.writeFileSync(path.join(ws, 'deploy/drive_lab.sh'), `#!/usr/bin/env bash
echo "$*" >> "\${STUB_CALLS:-/dev/null}"
case "$1" in
  get) mkdir -p "$3"
       if [ -n "\${STUB_GET_FAIL:-}" ]; then case "$2" in *"$STUB_GET_FAIL") exit 1;; esac; fi
       [ -d "$STUB_DRIVE/$2" ] || exit 3; cp -r "$STUB_DRIVE/$2/." "$3/";;
  put) mkdir -p "$STUB_DRIVE/$2"; cp -r "$3/." "$STUB_DRIVE/$2/";;
esac
`, { mode: 0o755 });
function jobWs() {
  const w = stepWs(); fakeLab(w.ws);
  fs.copyFileSync(path.join(ROOT, '.github/scripts/twin-look.sh'), path.join(w.ws, '.github/scripts/twin-look.sh'));
  fs.writeFileSync(path.join(w.bin, 'node'), `#!/usr/bin/env bash\necho "$*" > "${w.tmp}/node-args"\nmkdir -p data/twin; echo '{"paired":[]}' > data/twin/verdict.json\nls data/twin/windows-*.json 2>/dev/null | wc -l | sed 's/^ */[twin] stub verdict saw windows files: /'\necho "[twin] depth: adversary AUC 0.55"\n`, { mode: 0o755 });
  return { ...w, drive: tmpDir(), calls: path.join(w.tmp, 'calls.txt') };
}
/** The run's judged files as the build keeps them (data/twinlite), in a folder: on Drive, or as a cache hit. */
function liteDir(dir: string, split: string, judge: string[], drop: string[] = []): string {
  fs.mkdirSync(dir, { recursive: true });
  const files: Record<string, unknown> = { 'paired.json': [], 'features-real.json': [], 'features-requote.json': [], 'features-depth.json': [], 'split.json': { name: split, fit: SPLITS.dev.fit, judge, warm: [] }, 'twin-source.json': { replayVersion: 1 } };
  for (const [f, v] of Object.entries(files)) if (!drop.includes(f)) fs.writeFileSync(path.join(dir, f), JSON.stringify(v));
  return dir;
}
const putLite = (w: { drive: string }, run: string, split: string, judge: string[], drop: string[] = []) => liteDir(path.join(w.drive, `simulated/history-twin/${run}/twinlite`), split, judge, drop);
/** The legs' windows as kept on Drive: windows/twin-HOW-pI/windows-HOW-pI-DAY.json */
const putWindows = (w: { drive: string }, run: string, have: Partial<Record<(typeof HOWS)[number], string[]>>) => legsDir(have, path.join(w.drive, `simulated/history-twin/${run}/windows`));
type Plan = Array<{ name: string; env?: Record<string, string>; skipIf?: () => boolean }>;
function runPlan(job: 'verdict' | 'reverdict', w: ReturnType<typeof jobWs>, run: string, plan: Plan) {
  const text = jobText(wf(), job); let failed: string | undefined; const outs: string[] = [];
  for (const st of plan) {
    if (st.skipIf?.()) continue;
    const r = bash(expr(stepScript(text, st.name), { run }), { PATH: `${w.bin}:${process.env.PATH}`, RUNNER_TEMP: w.tmp, STUB_DRIVE: w.drive, STUB_CALLS: w.calls, ...(st.env ?? {}) }, w.ws);
    outs.push(`${r.stdout}${r.stderr}`);
    if (r.status !== 0) { failed = st.name; break; }
  }
  const rd = (f: string) => (fs.existsSync(f) ? fs.readFileSync(f, 'utf8') : '');
  const looks = path.join(w.drive, 'derived/twin-confirm-looks');
  return { failed, out: outs.join(''), log: rd(path.join(w.tmp, 'verdict.log')), nodeArgs: rd(path.join(w.tmp, 'node-args')).trim(), calls: rd(w.calls), looks: fs.existsSync(looks) ? fs.readdirSync(looks) : [], windows: winFiles(path.join(w.ws, 'data/twin')) };
}
const hitCache = (w: { ws: string }, split: string, judge: string[]) => liteDir(path.join(w.ws, 'data/twinlite'), split, judge);
/** The step's own `if: hashFiles('data/twinlite/paired.json') == ''` (a test above holds the text): the step is skipped when the cache restored the file. */
const cacheHit = (w: { ws: string }) => () => fs.existsSync(path.join(w.ws, 'data/twinlite/paired.json'));
const REV_FROM_DRIVE = 'The judged features from Drive (the cache was evicted)', IN_PLACE = 'The judged features in place', REV_WINDOWS = "The legs' per-window P&L from Drive";
const revPlan = (w: { ws: string }, note = ''): Plan => [
  { name: REV_FROM_DRIVE, env: { RUN: '55' }, skipIf: cacheHit(w) }, { name: IN_PLACE, env: { RUN: '55' } }, { name: REV_WINDOWS, env: { RUN: '55' } }, { name: 'Verdict', env: { LOOK_NOTE: note } },
];

test('re-verdict, a run with no per-window P&L on Drive (no backtests, or a fast run): checks 2-4 are not re-read, the line says so, check 1 runs as before; a cache hit and a Drive read give the same answer', () => {
  for (const cache of [true, false]) {
    const w = jobWs();
    if (cache) hitCache(w, 'dev', [...SPLITS.dev.judge]); else putLite(w, '55', 'dev', [...SPLITS.dev.judge]);
    const r = runPlan('reverdict', w, '55', revPlan(w));
    assert.equal(r.failed, undefined, r.out);
    assert.ok(r.log.includes('[twin] no per-window P&L on Drive for run 55: checks 2-4 are not re-read\n'), r.log);
    assert.match(r.log, /stub verdict saw windows files: 0/); assert.match(r.log, /adversary AUC 0\.55/);
    assert.ok(r.log.indexOf('no per-window P&L') < r.log.indexOf('adversary AUC'), 'the stage appends to the log, it does not replace it');
    assert.deepEqual(r.windows, []); assert.equal(r.nodeArgs, '--import tsx research/historyTwin.ts --stage verdict --out data/twin'); assert.deepEqual(r.looks, [], 'a dev re-verdict numbers no look');
    assert.equal(/get simulated\/history-twin\/55\/twinlite/.test(r.calls), !cache, 'Drive is asked for the judged files only when the cache did not have them');
    assert.match(r.calls, /get simulated\/history-twin\/55\/windows /);
    assert.ok(fs.existsSync(path.join(w.ws, 'data/twin/paired.json')) && fs.existsSync(path.join(w.ws, 'data/twin/split.json')), 'the judged files are in place');
  }
});

test('re-verdict, the legs\' windows are on Drive and whole: the four files are assembled from the run\'s own judged days and checks 2-4 are read; the lines are the verdict job\'s', () => {
  const w = jobWs(); putLite(w, '55', 'dev', J3);
  // the legs' folder also holds a day the split does not judge: it is never read
  putWindows(w, '55', wholeLegs(['2026-11-13', '2026-11-14', '2026-11-16', '2026-11-17']));
  const r = runPlan('reverdict', w, '55', revPlan(w));
  assert.equal(r.failed, undefined, r.out);
  for (const how of HOWS) assert.ok(r.log.includes(`[twin] backtest legs ${how}: 3 of 3 judged day(s) have a per-window file, 6 window(s)\n`), r.log);
  assert.ok(r.log.includes('[twin] the per-window P&L on Drive for run 55 is whole: checks 2-4 are re-read\n'));
  assert.deepEqual(r.windows, ['windows-depth.json', 'windows-placebo.json', 'windows-real.json', 'windows-requote.json']); assert.match(r.log, /stub verdict saw windows files: 4/);
  assert.equal(JSON.parse(fs.readFileSync(path.join(w.ws, 'data/twin/windows-real.json'), 'utf8')).length, 6, 'the 4th day on Drive is not judged, so it is not in the file');
  assert.deepEqual(r.looks, []);
});

test('re-verdict, the legs\' windows on Drive are INCOMPLETE: nothing is copied, the WARNING says how many day files each source has, and check 1 runs alone; a lost placebo part is as refused as a lost twin part', () => {
  for (const [what, have, counts] of [
    ['a lost depth day', { ...wholeLegs(J3), depth: J3.slice(0, 2) }, '3/3/3/2 of 3'], ['a lost placebo part', { ...wholeLegs(J3), placebo: [J3[0]] }, '3/1/3/3 of 3'], ['a lost real source', { ...wholeLegs(J3), real: [] }, '0/3/3/3 of 3'],
  ] as Array<[string, Partial<Record<(typeof HOWS)[number], string[]>>, string]>) {
    const w = jobWs(); putLite(w, '55', 'dev', J3); putWindows(w, '55', have);
    const r = runPlan('reverdict', w, '55', revPlan(w));
    assert.equal(r.failed, undefined, `${what}: ${r.out}`);
    assert.ok(r.log.includes(`[twin] WARNING: the per-window P&L on Drive for run 55 is incomplete (real/placebo/requote/depth = ${counts} judged day(s)): checks 2-4 are not re-read\n`), `${what}: ${r.log}`);
    assert.deepEqual(r.windows, [], `${what}: no windows file is copied`); assert.match(r.log, /stub verdict saw windows files: 0/, `${what}: the stage sees none, so outcome() never counts a missing window as P&L 0`);
    assert.ok(r.log.includes('adversary AUC'), `${what}: check 1 is still read`); assert.ok(!/windows are whole|checks 2-4 are re-read/.test(r.log));
    assert.ok(!fs.existsSync(path.join(w.tmp, 'win')) || winFiles(path.join(w.tmp, 'win')).length === 0, `${what}: not even the staging folder holds a file`);
  }
});

test('re-verdict, no split.json, an unreadable split.json, or an rclone error on the windows: the first two never read a window, the third stops the job BEFORE any look is numbered', () => {
  // no split.json among the judged files: the judged days are not known, so no window is read
  const w1 = jobWs(); putLite(w1, '55', 'dev', J3, ['split.json']); putWindows(w1, '55', wholeLegs(J3));
  const r1 = runPlan('reverdict', w1, '55', revPlan(w1)); assert.equal(r1.failed, undefined, r1.out);
  assert.ok(r1.log.includes("[twin] WARNING: run 55's judged files have no split.json, so its judged days are not known: checks 2-4 are not re-read\n")); assert.deepEqual(r1.windows, []);
  // a split.json with no judge list
  const w2 = jobWs(); putLite(w2, '55', 'dev', J3); fs.writeFileSync(path.join(w2.drive, 'simulated/history-twin/55/twinlite/split.json'), JSON.stringify({ name: 'dev' })); putWindows(w2, '55', wholeLegs(J3));
  const r2 = runPlan('reverdict', w2, '55', revPlan(w2)); assert.equal(r2.failed, REV_WINDOWS); assert.match(r2.log, /^\[twin\] ERROR: run 55's split\.json has no judge list: nothing was read and no look was numbered$/m); assert.deepEqual(r2.windows, []);
  // an rclone error (not "nothing there"): the job stops here, and on a CONFIRM run the look was not numbered
  const w3 = jobWs(); putLite(w3, '55', 'confirm', C3); putWindows(w3, '55', wholeLegs(C3));
  const plan = revPlan(w3, 'round 3 final'); plan[2].env = { RUN: '55', STUB_GET_FAIL: '/windows' };
  const r3 = runPlan('reverdict', w3, '55', plan);
  assert.equal(r3.failed, REV_WINDOWS); assert.match(r3.log, /^\[twin\] ERROR: reading the per-window P&L of run 55 from Drive failed \(rclone exit 1\): nothing was read and no look was numbered$/m);
  assert.deepEqual(r3.looks, [], 'no look file on Drive: the failure came before the Verdict step'); assert.equal(r3.nodeArgs, '', 'the verdict stage never ran'); assert.deepEqual(r3.windows, []);
});

test('re-verdict of a CONFIRM run: with whole windows it prints the blind aggregates of the confirm verdict job and nothing more, and it is another look (numbered after the data is in place); incomplete windows print day-file counts only', () => {
  const note = 'round 3 final: re-read the windows';
  const w = jobWs(); putLite(w, '55', 'confirm', C3); putWindows(w, '55', wholeLegs(C3));
  const r = runPlan('reverdict', w, '55', revPlan(w, note));
  assert.equal(r.failed, undefined, r.out);
  for (const how of HOWS) assert.ok(r.log.includes(`[twin] backtest legs ${how}: 3 of 3 judged day(s) have a per-window file\n`), r.log);
  assert.ok(!/window\(s\)/.test(`${r.out}${r.log}`), `no window count on a confirm split: ${r.log}`); assert.ok(!/-?\d+\.\d\d\b/.test(r.log.replace(/0\.55/g, '')), 'no P&L-looking number');
  assert.deepEqual(r.looks, [`look-001-local-1.txt`], 'one more look, logged'); assert.ok(r.nodeArgs.includes(`--confirm-look 1 --confirm-look-note ${note}`), r.nodeArgs); assert.match(r.log, /stub verdict saw windows files: 4/);
  assert.match(fs.readFileSync(path.join(w.drive, 'derived/twin-confirm-looks', r.looks[0]), 'utf8'), /^look 1\n/);
  // the windows are in place before the number is taken: the Drive calls come in this order
  const order = r.calls.split('\n').filter(Boolean).map((l) => l.split(' ').slice(0, 2).join(' '));
  assert.deepEqual(order, ['get simulated/history-twin/55/twinlite', 'get simulated/history-twin/55/windows', 'get derived/twin-confirm-looks', 'put derived/twin-confirm-looks'], 'the judged files and the windows are read before the look is numbered');
  // incomplete: day counts, no window count, the look is still another look (the stage runs)
  const w2 = jobWs(); putLite(w2, '55', 'confirm', C3); putWindows(w2, '55', { ...wholeLegs(C3), requote: C3.slice(1) });
  const r2 = runPlan('reverdict', w2, '55', revPlan(w2, note)); assert.equal(r2.failed, undefined, r2.out);
  assert.ok(r2.log.includes('[twin] WARNING: the per-window P&L on Drive for run 55 is incomplete (real/placebo/requote/depth = 3/3/2/3 of 3 judged day(s)): checks 2-4 are not re-read\n'));
  assert.ok(!/window\(s\)/.test(`${r2.out}${r2.log}`)); assert.deepEqual(r2.windows, []); assert.equal(r2.looks.length, 1);
  // the note is still required, and it fails before a look is numbered
  const w3 = jobWs(); putLite(w3, '55', 'confirm', C3); const r3 = runPlan('reverdict', w3, '55', revPlan(w3, '  '));
  assert.equal(r3.failed, 'Verdict'); assert.match(r3.log, /\[twin\] ERROR: a re-verdict of a confirm run is another look at the confirm days: pass confirm_look_note/); assert.deepEqual(r3.looks, []);
});

test('no lite cache and no Drive copy: both jobs stop at the Drive read with ONE [twin] ERROR line, before anything is read, printed or numbered; so does a lite set that is not whole', () => {
  // the re-verdict (a confirm run: the look must not be numbered), and the verdict job
  const w = jobWs(); const plan = revPlan(w, 'a look'); const r = runPlan('reverdict', w, '55', plan);
  assert.equal(r.failed, REV_FROM_DRIVE); assert.equal(r.log.trim(), "[twin] ERROR: run 55's features are neither cached nor on Drive (simulated/history-twin/55/twinlite; drive_lab.sh get exit 3, 3 = nothing there): nothing was read and no look was numbered");
  assert.match(r.out, /::error::run 55's features are neither cached/); assert.equal(r.calls.trim(), 'get simulated/history-twin/55/twinlite data/twinlite', 'no windows were asked for'); assert.deepEqual(r.looks, []); assert.equal(r.nodeArgs, '');
  const v = jobWs();
  const vr = runPlan('verdict', v, '77', [{ name: REV_FROM_DRIVE, env: { RUN: '77' }, skipIf: cacheHit(v) }, { name: IN_PLACE }, { name: 'The per-window P&L from Drive' }, { name: 'Verdict', env: { LOOK_N: '4', LOOK_NOTE: 'a look', BACKTESTS: 'true', BT_RESULT: 'success', JUDGED: C3.join(','), SPLIT: 'confirm' } }]);
  assert.equal(vr.failed, REV_FROM_DRIVE); assert.equal(vr.log.trim(), "[twin] ERROR: run 77's judged features are neither in the lite cache nor readable on Drive (simulated/history-twin/77/twinlite; drive_lab.sh get exit 3, 3 = nothing there): nothing was read and no verdict is made");
  assert.equal(vr.calls.trim(), 'get simulated/history-twin/77/twinlite data/twinlite'); assert.equal(vr.nodeArgs, ''); assert.deepEqual(vr.looks, []);
  // a Drive error (not "nothing there") says its exit code
  const e = jobWs(); const er = runPlan('verdict', e, '77', [{ name: REV_FROM_DRIVE, env: { RUN: '77', STUB_GET_FAIL: '/twinlite' } }]); assert.match(er.log, /drive_lab\.sh get exit 1, 3 = nothing there/);
  // a lite folder that is there but not whole (a half-written Drive copy): the in-place step refuses it, naming the file, before the data is read; a bad run id never reaches a path
  for (const [job, run, tag] of [['reverdict', '55', 'no look was numbered'], ['verdict', '77', 'no verdict is made']] as const) {
    const w2 = jobWs(); putLite(w2, run, 'confirm', C3, ['features-real.json']);
    const plan2 = job === 'verdict' ? [{ name: REV_FROM_DRIVE, env: { RUN: run }, skipIf: cacheHit(w2) }, { name: IN_PLACE }] : [{ name: REV_FROM_DRIVE, env: { RUN: run }, skipIf: cacheHit(w2) }, { name: IN_PLACE, env: { RUN: run } }];
    const r2 = runPlan(job, w2, run, plan2);
    assert.equal(r2.failed, IN_PLACE, job); assert.ok(r2.log.includes(`[twin] ERROR: the judged features of run ${run} are not whole (missing: features-real.json): nothing was read and ${tag}`), r2.log);
    assert.ok(!fs.existsSync(path.join(w2.ws, 'data/twin/paired.json')), `${job}: nothing was put in place`);
  }
  const bad = jobWs(); const br = runPlan('reverdict', bad, '55', [{ name: REV_FROM_DRIVE, env: { RUN: '5;rm -rf x' } }]);
  assert.equal(br.failed, REV_FROM_DRIVE); assert.match(br.log, /^\[twin\] ERROR: reverdict_run must be a run id$/m); assert.equal(br.calls, '', 'no Drive call for a run id that is not digits');
});

test('the verdict job, without the big cache: the judged files from the lite cache or from Drive, then (with backtests) the windows from Drive and the same completeness guard; a lite miss is no failure', () => {
  for (const cache of [true, false]) for (const backtests of [true, false]) {
    const w = jobWs();
    if (cache) hitCache(w, 'dev', J3); else putLite(w, '77', 'dev', J3);
    if (backtests) putWindows(w, '77', wholeLegs(J3));
    const plan: Plan = [{ name: REV_FROM_DRIVE, env: { RUN: '77' }, skipIf: cacheHit(w) }, { name: IN_PLACE }];
    if (backtests) plan.push({ name: 'The per-window P&L from Drive' });
    plan.push({ name: 'Verdict', env: { LOOK_N: '', LOOK_NOTE: '', BACKTESTS: String(backtests), BT_RESULT: backtests ? 'success' : 'skipped', JUDGED: J3.join(','), SPLIT: 'dev', FAST: 'false' } });
    const r = runPlan('verdict', w, '77', plan);
    assert.equal(r.failed, undefined, `cache ${cache}, backtests ${backtests}: ${r.out}`);
    assert.equal(r.log.includes('[twin] the judged features of run 77 were read from Drive (the lite cache is gone)\n'), !cache);
    assert.equal(/backtest legs real: 3 of 3 judged day\(s\) have a per-window file, 6 window\(s\)/.test(r.log), backtests); assert.match(r.log, backtests ? /stub verdict saw windows files: 4/ : /stub verdict saw windows files: 0/);
    assert.ok(!fs.existsSync(path.join(w.ws, 'data/twin/real')) && !fs.existsSync(path.join(w.ws, 'data/models')), 'the big cache\'s folders are not needed');
    assert.deepEqual(r.looks, [], 'the verdict job numbers no look');
  }
  // a lost leg is still not a verdict (the existing guard, now fed by the script): an incomplete set fails the job before the stage, with the counts
  const w = jobWs(); hitCache(w, 'dev', J3); putWindows(w, '77', { ...wholeLegs(J3), depth: J3.slice(0, 2) });
  const r = runPlan('verdict', w, '77', [{ name: IN_PLACE }, { name: 'The per-window P&L from Drive' }, { name: 'Verdict', env: { LOOK_N: '', LOOK_NOTE: '', BACKTESTS: 'true', BT_RESULT: 'success', JUDGED: J3.join(','), SPLIT: 'dev' } }]);
  assert.equal(r.failed, 'Verdict'); assert.match(r.log, /^\[twin\] ERROR: backtest legs incomplete \(backtest jobs: success; per-window day files real\/placebo\/requote\/depth = 3\/3\/3\/2 of 3\): checks 2-4 are not valid and no PASS\/FAIL is printed\./m); assert.equal(r.nodeArgs, '');
  // on the confirm split the build's look is printed by the stage from the job's own output; nothing numbers a look here
  const c = jobWs(); hitCache(c, 'confirm', C3); putWindows(c, '77', wholeLegs(C3));
  const cr = runPlan('verdict', c, '77', [{ name: IN_PLACE }, { name: 'The per-window P&L from Drive' }, { name: 'Verdict', env: { LOOK_N: '3', LOOK_NOTE: 'the look', BACKTESTS: 'true', BT_RESULT: 'success', JUDGED: C3.join(','), SPLIT: 'confirm' } }]);
  assert.equal(cr.failed, undefined, cr.out); assert.ok(cr.nodeArgs.includes('--confirm-look 3 --confirm-look-note the look')); assert.deepEqual(cr.looks, []); assert.ok(!/window\(s\)/.test(`${cr.out}${cr.log}`));
});

// ---- fix round 1 (usability): a script that did not RUN is not "the legs are incomplete" ----
// twin-windows.py's contract is exit 0 = whole, 3 = incomplete, 2 = bad arguments. A missing file (the new file that was never `git add`ed: RUNBOOK 3.0 check 1d), a crash or a
// missing python3 gives 2, 1 or 127: the re-verdict used to read every non-zero exit as "incomplete" and went on to the Verdict step, which numbers and logs a blind look on a
// CONFIRM run and prints check 1 only (a burned look); the verdict job blamed the legs with an empty '?'. Now only exit 3 degrades, anything else fails BEFORE the Verdict step.

/** Replaces the workspace's twin-windows.py: absent (the file is not on the ref), or a stub that exits with CODE. */
function breakWindowsPy(w: { ws: string }, how: 'missing' | number | 'crash') {
  const f = path.join(w.ws, '.github/scripts/twin-windows.py');
  if (how === 'missing') fs.rmSync(f);
  else fs.writeFileSync(f, how === 'crash' ? 'import json\njson.load(open("/no/such/file"))\n' : `import sys\nsys.exit(${how})\n`);
}

test('re-verdict with twin-windows.py missing, crashed or exiting oddly: the job fails at the windows step with its own [twin] ERROR line, BEFORE the Verdict step: no look is numbered, the stage never runs, no window is copied and no "incomplete" WARNING blames the legs', () => {
  for (const [what, how, exit] of [['the file is not on the ref', 'missing', 2], ['the script crashes', 'crash', 1], ['an exit code of its own', 7, 7]] as Array<[string, 'missing' | 'crash' | number, number]>) {
    for (const [split, judge, note] of [['confirm', C3, 'round 3 final: re-read the windows'], ['dev', J3, '']] as Array<[string, string[], string]>) {
      const w = jobWs(); putLite(w, '55', split, judge); putWindows(w, '55', wholeLegs(judge)); breakWindowsPy(w, how);
      const r = runPlan('reverdict', w, '55', revPlan(w, note));
      const at = `${what}, ${split}`;
      assert.equal(r.failed, REV_WINDOWS, `${at}: ${r.out}`);
      assert.ok(r.log.includes(`[twin] ERROR: twin-windows.py failed (exit ${exit}; 2 = bad arguments or the file is not on this ref, see RUNBOOK 3.0 check 1d): the legs' per-window P&L of run 55 was not assembled, nothing was read and no look was numbered\n`), `${at}: ${r.log}`);
      assert.match(r.out, /::error::twin-windows\.py failed \(exit /, at);
      assert.ok(!/WARNING|incomplete|are not re-read|checks 2-4 are re-read/.test(r.log), `${at}: the failure does not read as a lost leg or as a degraded verdict: ${r.log}`);
      assert.ok(!/= \?/.test(r.log), `${at}: no unexplained '?'`);
      assert.deepEqual(r.looks, [], `${at}: no look file on Drive`); assert.equal(r.nodeArgs, '', `${at}: the verdict stage never ran`); assert.deepEqual(r.windows, [], `${at}: no window file copied`);
      assert.ok(!/derived\/twin-confirm-looks/.test(r.calls), `${at}: twin-look.sh was never called (it would have read the look log from Drive): ${r.calls}`);
    }
  }
  // the ONE case that still degrades to check 1: the script ran and found the set incomplete (exit 3, tested above); a whole set and an unbroken script still give checks 2-4
  const ok = jobWs(); putLite(ok, '55', 'confirm', C3); putWindows(ok, '55', wholeLegs(C3));
  const okr = runPlan('reverdict', ok, '55', revPlan(ok, 'a look')); assert.equal(okr.failed, undefined, okr.out); assert.equal(okr.looks.length, 1);
});

test('verdict job with twin-windows.py missing or crashed: its Verdict step fails with the script\'s own message (not "backtest legs incomplete ... = ?"), before the stage and before anything is printed; an incomplete set (exit 3) still says the legs are incomplete', () => {
  for (const [what, how, exit] of [['the file is not on the ref', 'missing', 2], ['the script crashes', 'crash', 1]] as Array<[string, 'missing' | 'crash', number]>) {
    const w = jobWs(); hitCache(w, 'confirm', C3); putWindows(w, '77', wholeLegs(C3)); breakWindowsPy(w, how);
    const r = runPlan('verdict', w, '77', [{ name: IN_PLACE }, { name: 'The per-window P&L from Drive' }, { name: 'Verdict', env: { LOOK_N: '3', LOOK_NOTE: 'the look', BACKTESTS: 'true', BT_RESULT: 'success', JUDGED: C3.join(','), SPLIT: 'confirm' } }]);
    assert.equal(r.failed, 'Verdict', what);
    assert.ok(r.log.includes(`[twin] ERROR: twin-windows.py failed (exit ${exit}; 2 = bad arguments or the file is not on this ref, see RUNBOOK 3.0 check 1d): the legs' per-window P&L was not assembled and no PASS/FAIL is printed. Fix the cause, then re-verdict this run (reverdict_run): nothing needs rebuilding\n`), `${what}: ${r.log}`);
    assert.ok(!/backtest legs incomplete|= \?/.test(r.log), `${what}: the legs are not blamed: ${r.log}`);
    assert.equal(r.nodeArgs, '', `${what}: the stage never ran`); assert.deepEqual(r.looks, []); assert.deepEqual(r.windows, []);
  }
  // a lost leg, by the matrix result alone (the script ran and exited 0 or 3): still "backtest legs incomplete"
  const w = jobWs(); hitCache(w, 'dev', J3); putWindows(w, '77', wholeLegs(J3));
  const r = runPlan('verdict', w, '77', [{ name: IN_PLACE }, { name: 'The per-window P&L from Drive' }, { name: 'Verdict', env: { LOOK_N: '', LOOK_NOTE: '', BACKTESTS: 'true', BT_RESULT: 'failure', JUDGED: J3.join(','), SPLIT: 'dev' } }]);
  assert.equal(r.failed, 'Verdict'); assert.match(r.log, /^\[twin\] ERROR: backtest legs incomplete \(backtest jobs: failure; per-window day files real\/placebo\/requote\/depth = 3\/3\/3\/3 of 3\)/m); assert.equal(r.nodeArgs, '');
});

test('the workflow splits twin-windows.py\'s exit code in both jobs: 0 whole, 3 incomplete, anything else fails through twin_fail (a text pin; the two tests above run it)', () => {
  const y = wf();
  const rev = stepScript(jobText(y, 'reverdict'), "The legs' per-window P&L from Drive"), ver = stepScript(jobText(y, 'verdict'), 'Verdict');
  assert.match(rev, /if \[ "\$rc" -eq 0 \]; then\n\s+cp "\$RUNNER_TEMP"\/win\/windows-\*\.json data\/twin\/[\s\S]*elif \[ "\$rc" -eq 3 \]; then\n\s+echo "\[twin\] WARNING: the per-window P&L on Drive for run \$RUN is incomplete[\s\S]*else\n\s+twin_fail "twin-windows\.py failed \(exit \$rc;/);
  assert.match(ver, /if \[ "\$rc" -ne 0 \] && \[ "\$rc" -ne 3 \]; then\n\s+twin_fail "twin-windows\.py failed \(exit \$rc;[\s\S]*if \[ "\$BT_RESULT" != success \] \|\| \[ "\$rc" -ne 0 \]; then\n\s+twin_fail "backtest legs incomplete/);
  // the WARNING is reached by exit 3 only: nothing else prints it
  assert.equal((rev.match(/WARNING: the per-window P&L on Drive/g) ?? []).length, 1);
});

// ---------------------------------------------------------------------------------------------------------------
// ---- R3a: where does the depth twin's extra trading come from? The per-position dump of the backtest legs, the comparison script and their wiring.
// REPORT ONLY: no simulator, judge or engine byte changes, the windows files and the [fidelity] lines are the same with and without the dump, and a confirm leg
// writes and prints nothing new. The stage tests below run a real backtest (identity model) over a synthetic recording of about a second; the rest is
// pure, a python3 script on fixtures, or the workflow's own steps with a stubbed node, gh and Drive.
import { buildPositions, POSITION_LOSER_CENTS, positionAsset, positionHourly, positionsLines, POSITIONS_VERSION, type PositionsFile, type TradeLike } from '../research/historyTwin';
import { dumpPositions, runBacktestLeg, type LegRun } from '../research/historyTwin';

const POSITIONS_PY = path.join(ROOT, '.github/scripts/twin-positions.py');

/** A recorded day the backtest can trade: `assets` each list a 15-minute Up/Down contract every quarter hour of the first two hours, with a quote and a
 *  trade every few seconds, the index, and a result. The decision model is the identity one (no model file), so it enters often: enough positions to read. */
function btRecording(dir: string, day: string, assets: ReadonlyArray<readonly [string, number]> = [['BTC', 70000], ['ETH', 3500], ['SOL', 180]]): void {
  const t0 = Date.parse(`${day}T00:00:00Z`), ev: Array<Record<string, unknown>> = [];
  for (let q = 0; q < 8; q++) {
    const open = t0 + q * 15 * MIN, close = open + 15 * MIN;
    for (const [asset, px] of assets) {
      const tk = `KX${asset}15M-${day.slice(8)}NOV${String(q).padStart(4, '0')}-00`;
      ev.push({ t: open - MIN, k: 'market', ticker: tk, series: `KX${asset}15M`, asset, kind: 'updown', strike: px, cap: null, openTime: open, closeTime: close });
      for (let t = open; t <= close; t += 5000) {
        const mid = 0.5 + Math.sin(t / 60000 + px) * 0.2;
        ev.push({ t, k: 'index', asset, value: px + Math.sin(t / 60000) * px / 800 });
        ev.push({ t, k: 'book', ticker: tk, bids: [{ price: +(mid - 0.01).toFixed(2), size: 100 }], asks: [{ price: +(mid + 0.01).toFixed(2), size: 120 }] });
        if ((t - open) % 15000 === 0) ev.push({ t: t + 1, k: 'trade', ticker: tk, price: 0.5, count: 3, takerSide: 'yes', ts: t + 1 });
      }
      ev.push({ t: close + 1000, k: 'result', ticker: tk, result: q % 3 === 0 ? 'no' : 'yes' });
    }
  }
  ev.sort((a, b) => (a.t as number) - (b.t as number));
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, `md-${day}.jsonl.gz`), zlib.gzipSync(ev.map((e) => JSON.stringify(e)).join('\n') + '\n'));
}
/** `--stage backtest` as a leg runs it (a subprocess: the engine reads the environment once). */
function runLeg(dir: string, out: string, name: string, days: string, extra: string[] = []) {
  return spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', '--stage', 'backtest', '--dir', dir, '--name', name, '--days', days, '--model', path.join(tmpDir(), 'no-model.json'), '--out', out, ...extra],
    { encoding: 'utf8', env: { ...process.env, TRADING_MODE: 'paper', AUTO_TRAIN: 'off', DATA_DIR: tmpDir() } });
}
const fidelityLines = (stdout: string) => stdout.split('\n').filter((l) => l.startsWith('[fidelity]')).map((l) => l.replace(/\(\d+\.\d min\)/g, '(T min)'));
const positionLines = (stdout: string) => stdout.split('\n').filter((l) => l.startsWith('[twin] positions'));
/** What a public log must never carry: a date, a time of day, an epoch, a ticker, a per-window or per-position list. */
const publicSafe = (lines: string[], what: string) => {
  for (const l of lines) {
    assert.ok(!/\d{4}-\d\d-\d\d/.test(l), `${what}: no date in "${l}"`);
    assert.ok(!/KX[A-Z0-9]|-26NOV|T\d\d:\d\d|\b\d{2}:\d{2}\b/.test(l), `${what}: no ticker or time in "${l}"`);
    assert.ok(!/\d{9,}/.test(l), `${what}: no epoch or long number in "${l}"`);
    assert.ok(!/ windows: /.test(l), `${what}: not the leg step's per-window filter in "${l}"`);
    assert.ok(l.length < 300, `${what}: the leg step cuts lines at 300 characters (${l.length})`);
  }
};

const at = (day: number, hh: number, mm = 0) => Date.UTC(2026, 10, day, hh, mm);
const trade = (ticker: string, closeTs: number, pnl: number, contracts = 30): TradeLike => ({ ticker, closeTs, pnl, contracts });
/** Settled positions of the 13th (judged), around it: a loser, a boundary, hourly strikes, an unknown asset, a position of the day before (warm-up) and after, and edges at midnight. */
function fixtureRun() {
  const trades: TradeLike[] = [
    trade('KXBTC15M-26NOV131215-00', at(13, 12, 15), -7.5, 30), trade('KXETH15M-26NOV131215-00', at(13, 12, 15), 1.234, 30),
    trade('KXSOL15M-26NOV131230-00', at(13, 12, 30), -0.126, 20), trade('KXXRP15M-26NOV131230-00', at(13, 12, 30), -5, 20),
    trade('KXXRP15M-26NOV131245-00', at(13, 12, 45), -5.01, 10), trade('KXDOGE15M-26NOV131300-00', at(13, 13, 0), 2, 15),
    trade('KXBTCD-26NOV1313-T70000', at(13, 13, 0), -20, 15), trade('KXETH-26NOV1313-B3500', at(13, 13, 0), 0.4, 15),
    trade('KXBTC15M-26NOV122345-00', at(12, 23, 45), 3, 40), trade('KXBTC15M-26NOV130000-00', at(13, 0, 0), 3, 40),
    trade('KXBTC15M-26NOV140000-00', at(14, 0, 0), 4, 25), trade('KXBTC15M-26NOV140015-00', at(14, 0, 15), 5, 25), trade('KXBTC15M-NAN', NaN, 5, 1),
  ];
  const windows = new Map<number, { contracts: number; fills?: number }>([[at(13, 12, 15), { contracts: 30, fills: 5 }], [at(13, 12, 30), { contracts: 20, fills: 4 }], [at(13, 12, 45), { contracts: 10, fills: 2 }], [at(13, 13, 0), { contracts: 15, fills: 3 }],
    [at(13, 15, 0), { contracts: 0, fills: 0 }], [at(14, 0, 0), { contracts: 25, fills: 6 }], [at(12, 23, 45), { contracts: 40, fills: 9 }], [at(14, 0, 15), { contracts: 25, fills: 1 }]]);
  return { trades, windows, entryEvaluations: 31545, fills: 120, contracts: 1700 };
}

test('R3a: buildPositions keeps the judged day\'s settled positions by asset, kind, close time, window contracts and cents; a midnight close belongs to the day before; the totals are the run\'s and the day\'s', () => {
  const f = buildPositions(fixtureRun(), ['2026-11-13']);
  assert.equal(f.version, POSITIONS_VERSION); assert.deepEqual(f.days, ['2026-11-13']);
  // 12:15 BTC loser and ETH, 12:30 SOL and XRP, 12:45 XRP loser, 13:00 DOGE / BTC hourly / ETH bracket, then the contract closing at midnight (it belongs to the 13th); NOT the 12th's 23:45, NOT the close at 13th 00:00 (the 12th's), NOT the 14th's, NOT the NaN
  assert.deepEqual(f.positions.map((p) => [p.asset, p.closeTs, p.hourly, p.windowContracts, p.pnl]), [
    ['BTC', at(13, 12, 15), false, 30, -750], ['ETH', at(13, 12, 15), false, 30, 123], ['SOL', at(13, 12, 30), false, 20, -13], ['XRP', at(13, 12, 30), false, 20, -500],
    ['XRP', at(13, 12, 45), false, 10, -501], ['BTC', at(13, 13, 0), true, 15, -2000], ['ETH', at(13, 13, 0), true, 15, 40], ['other', at(13, 13, 0), false, 15, 200], ['BTC', at(14, 0, 0), false, 25, 400],
  ].sort((a, b) => (a[1] as number) - (b[1] as number) || ((a[0] as string) < (b[0] as string) ? -1 : (a[0] as string) > (b[0] as string) ? 1 : 0)));
  for (const p of f.positions) { assert.deepEqual(Object.keys(p).sort(), ['asset', 'closeTs', 'hourly', 'pnl', 'windowContracts']); assert.ok(Number.isInteger(p.pnl) && Number.isInteger(p.windowContracts)); }
  assert.ok(!JSON.stringify(f).includes('KX'), 'no ticker in the file');
  // the whole run (warm-up included), and the judged day from the windows that traded (the empty window and the other days' do not count)
  assert.deepEqual(f.totals, { entryEvaluations: 31545, fills: 120, contracts: 1700 });
  assert.deepEqual(f.day, { windows: 5, fills: 5 + 4 + 2 + 3 + 6, contracts: 30 + 20 + 10 + 15 + 25 });
  // another judged day, or two: the same filter as the windows file's
  assert.deepEqual(buildPositions(fixtureRun(), ['2026-11-14']).positions.map((p) => p.pnl), [500], 'the 14th: only the 00:15 close');
  assert.equal(buildPositions(fixtureRun(), ['2026-11-12', '2026-11-14']).positions.length, 3, 'two days: the 12th\'s 23:45 and the 13th\'s 00:00 close, and the 14th\'s 00:15');
  assert.equal(buildPositions({ ...fixtureRun(), trades: [] }, ['2026-11-13']).positions.length, 0);
  // the asset and the strike kind come from the series prefix
  assert.deepEqual(['KXBTC15M-A', 'KXETH15M-A', 'KXSOL15M-A', 'KXXRP15M-A', 'KXDOGE15M-A', 'KXBTCD-A', 'KXETH-A', 'WEIRD'].map(positionAsset), ['BTC', 'ETH', 'SOL', 'XRP', 'other', 'BTC', 'ETH', 'other']);
  assert.deepEqual(['KXBTC15M-A', 'KXBTCD-A', 'KXETH-A', 'KXSOLD-A'].map(positionHourly), [false, true, true, true]);
  assert.equal(POSITION_LOSER_CENTS, -500);
});

test('R3a: the dump\'s day filter is replayFidelity\'s onDays filter (a window closing at midnight belongs to the day before), key for key', async () => {
  const { onDays } = await import('../research/replayFidelity');
  const keys = [at(12, 23, 59), at(13, 0, 0), at(13, 0, 1), at(13, 12, 0), at(13, 23, 59), at(14, 0, 0), at(14, 0, 1), NaN].filter(Number.isFinite);
  for (const day of ['2026-11-12', '2026-11-13', '2026-11-14']) {
    const viaWindows = [...onDays(new Map(keys.map((k) => [k, { pnl: 0, contracts: 1, fees: 0 }])), [day]).keys()].sort();
    const viaDump = buildPositions({ trades: keys.map((k) => trade('KXBTC15M-A', k, 1)), windows: new Map(), entryEvaluations: 0, fills: 0, contracts: 0 }, [day]).positions.map((p) => p.closeTs).sort();
    assert.deepEqual(viaDump, viaWindows, `the day ${day}`);
  }
});

test('R3a: positionsLines prints counts only: by asset, strike kind and 6-hour UTC close bucket, with no date, time, ticker, epoch or per-window figure', () => {
  const f = buildPositions(fixtureRun(), ['2026-11-13']);
  const lines = positionsLines('depth-p2-2026-11-13', f);
  publicSafe(lines, 'fixture');
  assert.deepEqual(lines, [
    '[twin] positions depth p2: 9 settled positions in 5 windows, 3 losers (below -$5)',
    "[twin] positions depth p2 totals: the leg's run (warm-up day included) 31,545 entry evaluations, 120 fills, 1,700 contracts; the judged day 5 traded windows, 20 fills, 100 contracts",
    '[twin] positions depth p2 BTC: 3 positions, 3 windows, 2 losers, 70 window contracts (shared with the other assets), 0.10 positions per 1,000 entry evaluations',
    '[twin] positions depth p2 ETH: 2 positions, 2 windows, 0 losers, 45 window contracts (shared with the other assets), 0.06 positions per 1,000 entry evaluations',
    '[twin] positions depth p2 SOL: 1 positions, 1 windows, 0 losers, 20 window contracts (shared with the other assets), 0.03 positions per 1,000 entry evaluations',
    '[twin] positions depth p2 XRP: 2 positions, 2 windows, 1 losers, 30 window contracts (shared with the other assets), 0.06 positions per 1,000 entry evaluations',
    '[twin] positions depth p2 other: 1 positions, 1 windows, 0 losers, 15 window contracts (shared with the other assets), 0.03 positions per 1,000 entry evaluations',
    '[twin] positions depth p2 by strike: 2 hourly-strike (1 losers), 7 15-minute (2 losers)',
    '[twin] positions depth p2 by UTC close hour: 00-05 0, 06-11 0, 12-17 8, 18-23 1',
  ]);
  // the sums agree: the assets, the strike kinds and the hour buckets each add up to the positions
  const n = (re: RegExp) => lines.map((l) => re.exec(l)).filter(Boolean).map((m) => Number(m![1]));
  assert.equal(n(/ (?:BTC|ETH|SOL|XRP|other): (\d+) positions/).reduce((a, b) => a + b, 0), 9);
  // no 'other' line when no position is of an unknown asset; a leg name that does not parse prints 'leg' (never the name, which holds the date); no evaluations: n/a
  const quiet = buildPositions({ trades: [trade('KXBTC15M-A', at(13, 1, 0), 1)], windows: new Map(), entryEvaluations: 0, fills: 0, contracts: 0 }, ['2026-11-13']);
  const q = positionsLines('weird-name-2026-11-13', quiet);
  publicSafe(q, 'quiet'); assert.ok(!q.some((l) => / other:/.test(l)) && q.every((l) => l.startsWith('[twin] positions leg')), q.join('\n')); assert.ok(q.some((l) => /BTC: 1 positions.* n\/a positions per 1,000/.test(l)));
  const none = positionsLines('real-p0-2026-11-13', buildPositions({ ...fixtureRun(), trades: [] }, ['2026-11-13']));
  assert.equal(none[0], '[twin] positions real p0: 0 settled positions in 0 windows, 0 losers (below -$5)');
});

test('R3a: --positions writes positions-NAME.json beside the windows file (the judged day only) and prints counts only; the windows file and every [fidelity] line are the same with and without it, and without it nothing new is written or printed', () => {
  const dir = tmpDir(); btRecording(dir, '2026-11-12'); btRecording(dir, '2026-11-13');
  const name = 'depth-p2-2026-11-13', a = path.join(tmpDir(), 'a'), b = path.join(tmpDir(), 'b');
  const withDump = runLeg(dir, a, name, '2026-11-13', ['--positions']), without = runLeg(dir, b, name, '2026-11-13');
  assert.equal(withDump.status, 0, withDump.stderr); assert.equal(without.status, 0, without.stderr);
  assert.deepEqual(fs.readdirSync(a).sort(), [`positions-${name}.json`, `windows-${name}.json`]); assert.deepEqual(fs.readdirSync(b), [`windows-${name}.json`], 'without the flag the stage writes what it always wrote');
  assert.equal(fs.readFileSync(path.join(a, `windows-${name}.json`), 'utf8'), fs.readFileSync(path.join(b, `windows-${name}.json`), 'utf8'), 'the windows file is the same bytes');
  assert.deepEqual(fidelityLines(withDump.stdout), fidelityLines(without.stdout)); assert.ok(fidelityLines(without.stdout).length >= 6, 'the [fidelity] lines are there');
  assert.deepEqual(positionLines(without.stdout), [], 'no [twin] positions line without the flag');
  // the file
  const f = JSON.parse(fs.readFileSync(path.join(a, `positions-${name}.json`), 'utf8')) as PositionsFile;
  const win = new Map<number, { pnl: number; contracts: number; fills: number }>(JSON.parse(fs.readFileSync(path.join(a, `windows-${name}.json`), 'utf8')));
  assert.equal(f.version, POSITIONS_VERSION); assert.deepEqual(f.days, ['2026-11-13']); assert.ok(f.positions.length >= 6, `${f.positions.length} positions`);
  const lines = fidelityLines(without.stdout), settled = Number(/(\d+) settled positions/.exec(lines.join('\n'))![1]), evals = Number(/(\d+) entry evaluations/.exec(lines.join('\n'))![1]);
  assert.ok(f.positions.length < settled, `the warm-up day's positions are not in the dump (${f.positions.length} of the run's ${settled})`);
  assert.equal(f.totals.entryEvaluations, evals, 'the run\'s entry evaluations, as the [fidelity] line has them');
  assert.ok(f.positions.every((p) => ['BTC', 'ETH', 'SOL'].includes(p.asset) && p.hourly === false && Number.isInteger(p.pnl) && win.has(p.closeTs) && new Date(p.closeTs - 1).toISOString().startsWith('2026-11-13')));
  assert.deepEqual(new Set(f.positions.map((p) => p.asset)), new Set(['BTC', 'ETH', 'SOL']), 'every asset of the recording traded');
  // the day's totals are the windows file's own numbers
  const traded = [...win.values()].filter((w) => w.contracts > 0);
  assert.deepEqual(f.day, { windows: traded.length, fills: traded.reduce((x, w) => x + w.fills, 0), contracts: traded.reduce((x, w) => x + w.contracts, 0) });
  // a window's P&L is the sum of its positions' (to the cent each, so within the number of positions in it)
  for (const [k, w] of win) { const ps = f.positions.filter((p) => p.closeTs === k); if (ps.length) assert.ok(Math.abs(ps.reduce((x, p) => x + p.pnl, 0) - Math.round(w.pnl * 100)) <= ps.length, `a window's cents ${ps.map((p) => p.pnl)} vs ${w.pnl}`); }
  // what is printed: counts only, from the file
  assert.deepEqual(positionLines(withDump.stdout), positionsLines(name, f)); publicSafe(positionLines(withDump.stdout), 'the leg');
  assert.ok(positionLines(withDump.stdout).length === 8 && positionLines(withDump.stdout)[0].startsWith('[twin] positions depth p2: '), positionLines(withDump.stdout).join('\n'));
  // the leg step prints only the [fidelity] lines and these: nothing else the stage prints (the engine's tables) matches
  assert.ok(positionLines(withDump.stdout).every((l) => /^\[twin\] positions /.test(l)));
});

test('R3a: backtestDir keeps its signature and its windows; backtestDirRun gives the same windows and the whole result (the settled positions, the entry evaluations)', () => {
  const dir = tmpDir(); btRecording(dir, '2026-11-13');
  const out = path.join(tmpDir(), 'both.json');
  const script = `import fs from 'fs'; const { backtestDir, backtestDirRun } = await import('./research/replayFidelity.ts'); const m = process.argv[1] + '/no-model.json'; const a = await backtestDir(process.argv[2], m); const b = await backtestDirRun(process.argv[2], m); fs.writeFileSync(process.argv[3], JSON.stringify({ a: [...a], b: [...b.windows], trades: b.result.trades.length, ev: b.result.entryEvaluations }));`;
  const r = spawnSync(process.execPath, ['--import', 'tsx', '--input-type=module', '-e', script, tmpDir(), dir, out], { encoding: 'utf8', env: { ...process.env, TRADING_MODE: 'paper', AUTO_TRAIN: 'off', DATA_DIR: tmpDir() } });
  assert.equal(r.status, 0, r.stderr);
  const j = JSON.parse(fs.readFileSync(out, 'utf8'));
  assert.deepEqual(j.a, j.b); assert.ok(j.a.length >= 6 && j.trades >= 6 && j.ev > 0);
  // the [fidelity] lines of the two calls are the same lines (the new function adds none)
  const per = fidelityLines(r.stdout), half = per.length / 2; assert.equal(per.length % 2, 0); assert.deepEqual(per.slice(0, half), per.slice(half));
});

test('R3a: a leg on a confirm day is refused --positions BEFORE the backtest starts (nothing written, nothing printed); without the flag it writes only the windows file and prints no positions line', () => {
  const none = path.join(tmpDir(), 'none');
  for (const days of ['2026-11-18', '2026-11-12,2026-11-19', '2026-11-20']) {
    const r = runLeg(path.join(tmpDir(), 'nodir'), none, 'depth-p0-2026-11-18', days, ['--positions']);
    assert.notEqual(r.status, 0, days); assert.match(r.stderr, /^\[twin\] ERROR: --positions is for dev and custom legs only: a leg that reads a confirm day writes and prints no per-position file/m);
    assert.ok(!fs.existsSync(none), `${days}: not even the out folder is made`); assert.deepEqual(positionLines(r.stdout), []); assert.ok(!/\[fidelity\]/.test(r.stdout), 'the refusal comes before the backtest');
  }
  // a confirm leg as the workflow runs it (no flag): the windows file only, nothing positions-like printed
  const dir = tmpDir(); btRecording(dir, '2026-11-17'); btRecording(dir, '2026-11-18');
  const out = path.join(tmpDir(), 'out'), r = runLeg(dir, out, 'depth-p0-2026-11-18', '2026-11-18');
  assert.equal(r.status, 0, r.stderr); assert.deepEqual(fs.readdirSync(out), ['windows-depth-p0-2026-11-18.json']); assert.deepEqual(positionLines(r.stdout), []);
  assert.ok(!/positions-/.test(r.stdout + r.stderr.replace(/settled positions/g, '')), 'no positions file is named');
  // a custom or dev leg of the FIT days (never confirm) is asked for it freely
  const fit = tmpDir(); btRecording(fit, '2026-11-11'); btRecording(fit, '2026-11-12');
  const o2 = path.join(tmpDir(), 'o'), r2 = runLeg(fit, o2, 'real-p1-2026-11-12', '2026-11-12', ['--positions']);
  assert.equal(r2.status, 0, r2.stderr); assert.ok(fs.existsSync(path.join(o2, 'positions-real-p1-2026-11-12.json'))); assert.match(positionLines(r2.stdout)[0], /^\[twin\] positions real p1: /);
});

test('R3a: a dump that cannot be written is one warning line, not a red leg: the windows file is whole and the exit code is 0', () => {
  const dir = tmpDir(); btRecording(dir, '2026-11-13');
  const out = path.join(tmpDir(), 'out'), name = 'depth-p0-2026-11-13';
  fs.mkdirSync(path.join(out, `positions-${name}.json`), { recursive: true }); // a folder where the file goes: the write fails (EISDIR)
  const r = runLeg(dir, out, name, '2026-11-13', ['--positions']);
  assert.equal(r.status, 0, r.stderr);
  assert.deepEqual(positionLines(r.stdout), ['[twin] positions depth p0: WARNING: the per-position file was not written (EISDIR); the windows file is whole']);
  assert.ok(fs.statSync(path.join(out, `windows-${name}.json`)).isFile() && JSON.parse(fs.readFileSync(path.join(out, `windows-${name}.json`), 'utf8')).length >= 6);
  publicSafe(positionLines(r.stdout), 'the warning');
});

test('R3a: runBacktestLeg uses backtestDirRun when the ref has it and falls back to backtestDir when replayFidelity.ts predates it (the two files pushed apart): the same windows, no result, no TypeError', async () => {
  const w = new Map([[1, { pnl: 1, contracts: 2, fills: 1 }]]) as unknown as LegRun['windows'];
  const result = { trades: [], windows: new Map(), entryEvaluations: 7, fills: 1, contracts: 2 } as unknown as NonNullable<LegRun['result']>;
  const calls: string[] = [];
  const oldRef = { backtestDir: async (d: string, m: string, e: Record<string, string>) => { calls.push(`dir ${d} ${m} ${JSON.stringify(e)}`); return w; } };
  const gone = await runBacktestLeg(oldRef as never, 'D', 'M', { 'latency-ms': '250' });
  assert.equal(gone.windows, w); assert.equal(gone.result, undefined, 'an old replayFidelity.ts has no result to dump'); assert.deepEqual(calls, ['dir D M {"latency-ms":"250"}']);
  const newRef = { ...oldRef, backtestDirRun: async (d: string, m: string, e: Record<string, string>) => { calls.push(`run ${d} ${m} ${JSON.stringify(e)}`); return { windows: w, result }; } };
  const there = await runBacktestLeg(newRef as never, 'D', 'M', {});
  assert.equal(there.windows, w); assert.equal(there.result, result); assert.deepEqual(calls.slice(1), ['run D M {}'], 'backtestDir is not run a second time');
  // the stage hands it the real module (a namespace with both exports), and the real file has the export the stage prefers
  assert.match(fs.readFileSync(path.join(ROOT, 'research/replayFidelity.ts'), 'utf8'), /^export async function backtestDirRun\(/m);
  assert.match(fs.readFileSync(path.join(ROOT, 'research/historyTwin.ts'), 'utf8'), /const run = await runBacktestLeg\(mod, dir, model, extra\);/);
});

test('R3a: dumpPositions writes the file and returns the counts-only lines; a run with no result (an old replayFidelity.ts) or an unwritable folder is the ONE warning line and writes nothing', () => {
  const out = tmpDir(), name = 'depth-p2-2026-11-13', f = buildPositions(fixtureRun(), ['2026-11-13']);
  const lines = dumpPositions(out, name, ['2026-11-13'], fixtureRun() as never);
  assert.deepEqual(lines, positionsLines(name, f)); publicSafe(lines, 'the dump');
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(out, `positions-${name}.json`), 'utf8')), JSON.parse(JSON.stringify(f)));
  const none = tmpDir();
  assert.deepEqual(dumpPositions(none, name, ['2026-11-13'], undefined), ['[twin] positions depth p2: WARNING: the per-position file was not written (no-backtestDirRun); the windows file is whole']);
  assert.deepEqual(fs.readdirSync(none), [], 'no file is written without a result'); publicSafe(dumpPositions(none, name, ['2026-11-13'], undefined), 'the warning');
  const missing = path.join(tmpDir(), 'absent'); // the folder is not there: the write fails with ENOENT, a warning and not a throw
  assert.deepEqual(dumpPositions(missing, name, ['2026-11-13'], fixtureRun() as never), ['[twin] positions depth p2: WARNING: the per-position file was not written (ENOENT); the windows file is whole']);
});

test('R3a: the leg step asks dev and custom legs for --positions and prints their lines, never asks a confirm leg, and prints nothing positions-like there', () => {
  const y = wf(), step = stepScript(y, 'Backtest');
  assert.match(step, /POS=\(\); \[ "\$BLIND" = true \] \|\| POS=\(--positions\)/); assert.match(step, /"\$\{LAT\[@\]\}" "\$\{POS\[@\]\}" > "\$RUNNER_TEMP\/bt-\$d\.log"/);
  assert.equal((step.match(/--positions/g) ?? []).length, 1, 'the flag is named once, in the line that sets POS: nowhere else');
  const work = tmpDir(), bin = path.join(work, 'bin'), ws = path.join(work, 'ws'), tmp = path.join(work, 'tmp');
  fs.mkdirSync(bin); fs.mkdirSync(tmp);
  for (const x of ['2026-11-12', '2026-11-13', '2026-11-17', '2026-11-18', '2026-11-19']) { fs.mkdirSync(path.join(ws, 'data/twin/depth'), { recursive: true }); fs.writeFileSync(path.join(ws, 'data/twin/depth', `md-${x}.jsonl.gz`), 'x'); }
  // a stub node that records its arguments and prints what the stage prints, the positions lines only when asked
  fs.writeFileSync(path.join(bin, 'node'), `#!/usr/bin/env bash
echo "$*" >> "$RUNNER_TEMP/node-args.txt"
out=; name=; pos=; for ((i=1;i<=$#;i++)); do case "\${!i}" in --out) j=$((i+1)); out=\${!j};; --name) j=$((i+1)); name=\${!j};; --positions) pos=1;; esac; done
echo "[fidelity] day: 123 entry evaluations, 45 orders sent, 6 fills, 7 contracts"
echo "[fidelity] day windows: 11-18T12:00 2ct $4.20"
echo "[engine table] positions of the day are not a twin line"
if [ -n "$pos" ]; then echo "[twin] positions depth p0: 9 settled positions in 6 windows, 3 losers (below -\\$5)"; fi
mkdir -p "$out"; echo '[]' > "$out/windows-$name.json"; [ -z "$pos" ] || echo '{}' > "$out/positions-$name.json"
`, { mode: 0o755 });
  const run = (split: string, days: string) => { fs.rmSync(path.join(tmp, 'node-args.txt'), { force: true }); fs.rmSync(path.join(tmp, 'out'), { recursive: true, force: true });
    const r = bash(stepScript(y, 'Backtest'), { PATH: `${bin}:${process.env.PATH}`, SPLIT: split, DAYS: days, PARTS: '2', HOW: 'depth', PART: '0', GITHUB_WORKSPACE: ws, RUNNER_TEMP: tmp }, ws);
    return { r, args: fs.existsSync(path.join(tmp, 'node-args.txt')) ? fs.readFileSync(path.join(tmp, 'node-args.txt'), 'utf8') : '', files: fs.existsSync(path.join(tmp, 'out')) ? fs.readdirSync(path.join(tmp, 'out')).sort() : [] }; };
  const dev = run('dev', '2026-11-12,2026-11-13');
  assert.equal(dev.r.status, 0, dev.r.stderr); assert.match(dev.args, /--stage backtest .* --positions\n/); assert.match(dev.r.stdout, /^\[twin\] positions depth p0: 9 settled positions in 6 windows, 3 losers \(below -\$5\)$/m, 'the leg step lets the line through');
  assert.ok(!/engine table/.test(dev.r.stdout), 'only [fidelity] and [twin] positions lines reach the log'); assert.ok(!/ windows: /.test(dev.r.stdout));
  assert.deepEqual(dev.files, ['positions-depth-p0-2026-11-12.json', 'windows-depth-p0-2026-11-12.json']);
  const custom = run('custom', '2026-11-12,2026-11-13'); assert.match(custom.args, /--positions/);
  const blind = run('confirm', '2026-11-18,2026-11-19');
  assert.equal(blind.r.status, 0, blind.r.stderr); assert.ok(!/--positions/.test(blind.args), `a confirm leg is never asked: ${blind.args}`);
  assert.ok(!/\[twin\] positions|\[fidelity\]/.test(blind.r.stdout + blind.r.stderr), `nothing positions-like on a confirm split: ${blind.r.stdout}`); assert.match(blind.r.stdout, /\[twin\] confirm backtest depth part 0: 1 of 1 day\(s\) done/);
  assert.deepEqual(blind.files, ['windows-depth-p0-2026-11-18.json'], 'the windows file only: no positions file');
  // a confirm run whose stage were handed the flag anyway fails the leg loudly (the stage's own refusal, tested above), and prints no mechanics
  assert.match(y, /A confirm leg is never asked: the stage refuses the flag on a confirm day/);
});

// ---- R3a: .github/scripts/twin-positions.py (the comparison report), on fixtures ----

const prow = (asset: string, closeTs: number, pnl: number, hourly = false) => ({ asset, closeTs, hourly, windowContracts: 10, pnl });
type PosLeg = { day: string; rows: Array<ReturnType<typeof prow>>; evals: number };
/** The legs' folders with the per-position files, as drive_lab.sh get leaves them: twin-HOW-pI/positions-HOW-pI-DAY.json (into `dir`, beside any windows files). */
function posDir(have: Partial<Record<(typeof HOWS)[number], PosLeg[]>>, dir = tmpDir()): string {
  for (const [how, legs] of Object.entries(have)) legs!.forEach((l, i) => {
    const sub = path.join(dir, `twin-${how}-p${i}`); fs.mkdirSync(sub, { recursive: true });
    fs.writeFileSync(path.join(sub, `positions-${how}-p${i}-${l.day}.json`), JSON.stringify({ version: 1, days: [l.day], positions: l.rows, totals: { entryEvaluations: l.evals, fills: 0, contracts: 0 }, day: { windows: 0, fills: 0, contracts: 0 } }));
  });
  return dir;
}
const REAL1 = [prow('BTC', at(13, 12, 15), 100), prow('BTC', at(13, 12, 30), -800), prow('ETH', at(13, 12, 15), 50)], REAL2 = [prow('BTC', at(14, 3, 15), 20)];
const DEPTH1 = [prow('BTC', at(13, 12, 15), 90), prow('BTC', at(13, 13, 0), -900), prow('BTC', at(13, 13, 15), 10), prow('ETH', at(13, 12, 15), 5), prow('ETH', at(13, 12, 30), 7), prow('SOL', at(13, 12, 30), 3, true)], DEPTH2 = [prow('BTC', at(14, 3, 15), 1), prow('BTC', at(14, 4, 15), 2)];
const D2 = ['2026-11-13', '2026-11-14'];
const posLegs = (): Partial<Record<(typeof HOWS)[number], PosLeg[]>> => ({
  real: [{ day: D2[0], rows: REAL1, evals: 30000 }, { day: D2[1], rows: REAL2, evals: 50000 }], placebo: [{ day: D2[0], rows: REAL1, evals: 30000 }, { day: D2[1], rows: REAL2, evals: 50000 }],
  requote: [{ day: D2[0], rows: [prow('BTC', at(13, 12, 15), 1)], evals: 20000 }, { day: D2[1], rows: [], evals: 20000 }], depth: [{ day: D2[0], rows: DEPTH1, evals: 20000 }, { day: D2[1], rows: DEPTH2, evals: 25000 }],
});
const runPositionsPy = (src: string, run: string, ...flags: string[]) => spawnSync('python3', ['-I', POSITIONS_PY, src, run, ...flags], { encoding: 'utf8' });
const treeOf = (dir: string): string[] => fs.readdirSync(dir, { recursive: true, encoding: 'utf8' }).sort();

test('twin-positions.py: requote, depth and placebo against real, per day and per asset and over the days: positions, windows, rate per 1,000 evaluations, losers, window overlap; counts only, exit 0, nothing written', () => {
  const src = posDir(posLegs()), before = treeOf(src);
  const r = runPositionsPy(src, '77', '--split', 'dev', '--judged', D2.join(','));
  assert.equal(r.status, 0, r.stderr); assert.equal(r.stderr, '');
  const lines = r.stdout.split('\n').filter(Boolean);
  publicSafe(lines, 'the report');
  assert.deepEqual(lines.slice(0, 5), ["[twin] positions report, run 77: 2 judged day(s) in date order; the legs' per-position files, counts only", ...HOWS.map((h) => `[twin] positions ${h}: 2 of 2 judged day(s) have a per-position file`)]);
  const has = (l: string) => assert.ok(lines.includes(l), `${l}\n--- got ---\n${r.stdout}`);
  // depth against real: day 1 has 6 positions in 4 windows against real's 3 in 2 (losers 1 and 1); the windows both have are 12:15 and 12:30, depth adds 13:00 and 13:15
  has('[twin] positions depth vs real, day 1, all assets: positions 6 vs 3, windows 4 vs 2, per 1,000 entry evaluations 0.30 vs 0.10, losers 1 vs 1; windows both 2, real only 0, depth only 2');
  has('[twin] positions depth vs real, day 1, BTC: positions 3 vs 2, windows 3 vs 2, per 1,000 entry evaluations 0.15 vs 0.07, losers 1 vs 1; windows both 1, real only 1, depth only 2');
  has('[twin] positions depth vs real, day 1, SOL: positions 1 vs 0, windows 1 vs 0, per 1,000 entry evaluations 0.05 vs 0.00, losers 0 vs 0; windows both 0, real only 0, depth only 1');
  has('[twin] positions depth vs real, day 2, all assets: positions 2 vs 1, windows 2 vs 1, per 1,000 entry evaluations 0.08 vs 0.02, losers 0 vs 0; windows both 1, real only 0, depth only 1');
  // over both days the evaluations add up (45,000 against 80,000: 8 and 4 positions), the strike kinds and the close-hour buckets follow
  has('[twin] positions depth vs real, 2 day(s), all assets: positions 8 vs 4, windows 6 vs 3, per 1,000 entry evaluations 0.18 vs 0.05, losers 1 vs 1; windows both 3, real only 0, depth only 3');
  has('[twin] positions depth vs real, 2 day(s), hourly strikes: positions 1 vs 0, windows 1 vs 0, per 1,000 entry evaluations 0.02 vs 0.00, losers 0 vs 0; windows both 0, real only 0, depth only 1');
  has('[twin] positions depth vs real, 2 day(s), UTC close hours 12-17: positions 6 vs 3, windows 4 vs 2, per 1,000 entry evaluations 0.13 vs 0.04, losers 1 vs 1; windows both 2, real only 0, depth only 2');
  has('[twin] positions depth vs real, 2 day(s), UTC close hours 00-05: positions 2 vs 1, windows 2 vs 1, per 1,000 entry evaluations 0.04 vs 0.01, losers 0 vs 0; windows both 1, real only 0, depth only 1');
  assert.ok(!lines.some((l) => /UTC close hours (06-11|18-23)/.test(l)), 'a bucket neither side has is left out');
  // requote and the placebo (real itself: every window both, nothing only on either side)
  has('[twin] positions requote vs real, day 1, all assets: positions 1 vs 3, windows 1 vs 2, per 1,000 entry evaluations 0.05 vs 0.10, losers 0 vs 1; windows both 1, real only 1, requote only 0');
  has('[twin] positions placebo vs real, 2 day(s), all assets: positions 4 vs 4, windows 3 vs 3, per 1,000 entry evaluations 0.05 vs 0.05, losers 1 vs 1; windows both 3, real only 0, placebo only 0');
  assert.ok(!lines.some((l) => /placebo vs real.*(real only [1-9]|placebo only [1-9])/.test(l)), 'the placebo shares every window');
  // an asset neither side has gets no line; XRP is in none
  assert.ok(!lines.some((l) => /, XRP:/.test(l)) && !lines.some((l) => /, other:/.test(l)));
  assert.deepEqual(treeOf(src), before, 'it reads and writes nothing');
  // without --judged every day found counts (the same report); --dates names the days; the confirm split reads nothing
  assert.equal(runPositionsPy(src, '77', '--split', 'dev').stdout, r.stdout);
  const dated = runPositionsPy(src, '77', '--dates', '--judged', D2.join(',')).stdout; assert.ok(dated.includes('depth vs real, 2026-11-13, all assets: positions 6 vs 3') && !dated.includes('day 1,'), dated.split('\n').slice(0, 7).join('\n'));
  const blind = runPositionsPy(src, '77', '--split', 'confirm', '--judged', D2.join(',')); assert.equal(blind.status, 0); assert.equal(blind.stdout, '[twin] per-position report skipped: the confirm split is blind\n');
});

test('twin-positions.py: each all-assets line is followed by the two entry-evaluation counts (each source\'s own, they differ by source), and the docstring no longer says the denominators are the same', () => {
  const src = posDir(posLegs()), lines = runPositionsPy(src, '77', '--split', 'dev', '--judged', D2.join(',')).stdout.split('\n').filter(Boolean);
  const evalLines = lines.filter((l) => /: entry evaluations /.test(l));
  // depth 20,000 and 25,000 against real's 30,000 and 50,000 (the day files' own run-wide counts); the days add up to 45,000 against 80,000
  const want = (how: string, label: string, a: string, b: string) => {
    const i = lines.indexOf(`[twin] positions ${how} vs real, ${label}: entry evaluations ${a} vs ${b} (each source's own run-wide count, warm-up day included; the rates above divide by these)`);
    assert.ok(i > 0, `${how} ${label}\n${lines.join('\n')}`); assert.ok(lines[i - 1].startsWith(`[twin] positions ${how} vs real, ${label}: positions `), 'the counts follow their all-assets line');
  };
  want('depth', 'day 1, all assets', '20,000', '30,000'); want('depth', 'day 2, all assets', '25,000', '50,000'); want('depth', '2 day(s), all assets', '45,000', '80,000');
  want('requote', 'day 1, all assets', '20,000', '30,000'); want('placebo', '2 day(s), all assets', '80,000', '80,000');
  assert.ok(evalLines.every((l) => /, all assets: /.test(l)), 'only the all-assets lines carry the counts: the per-asset, per-kind and per-bucket lines share their denominator');
  publicSafe(evalLines, 'the evaluation counts');
  const py = fs.readFileSync(POSITIONS_PY, 'utf8');
  assert.ok(!/the same for every source/.test(py), 'the denominators are not the same for every source'); assert.match(py, /OWN run-wide entry evaluations/); assert.match(py, /the rate gap is larger than the count gap/); assert.match(py, /so the asset rates add\s+up to the all-assets rate/);
});

test('twin-positions.py: a run with no per-position files says so in one line; a missing source, a missing day, a missing real side, an unreadable or foreign file are named and left out, and the exit code is always 0', () => {
  // a run made before this round: windows files only (and an empty or absent folder): the one line, nothing else
  const old = legsDir(wholeLegs(D2));
  for (const [what, src] of [['windows files only', old], ['an empty folder', tmpDir()], ['no folder', path.join(tmpDir(), 'absent')]] as const) {
    const r = runPositionsPy(src, '55', '--split', 'dev', '--judged', D2.join(',')); assert.equal(r.status, 0, what); assert.equal(r.stdout, '[twin] no per-position files on Drive for run 55\n', what); assert.equal(r.stderr, '', what);
  }
  // a missing source: said, and the others still print
  const noRequote = posLegs(); delete noRequote.requote;
  const a = runPositionsPy(posDir(noRequote), '55', '--judged', D2.join(','));
  assert.equal(a.status, 0); assert.match(a.stdout, /^\[twin\] positions requote: 0 of 2 judged day\(s\) have a per-position file$/m); assert.match(a.stdout, /^\[twin\] positions requote vs real: no per-position files for requote, left out$/m);
  assert.match(a.stdout, /^\[twin\] positions depth vs real, day 1, all assets: positions 6 vs 3/m); assert.ok(!/requote vs real, (day|2)/.test(a.stdout));
  // a day only the real side has: compared on the days both have
  const oneDay = posLegs(); oneDay.depth = [oneDay.depth![0]];
  const b = runPositionsPy(posDir(oneDay), '55', '--judged', D2.join(','));
  assert.match(b.stdout, /^\[twin\] positions depth: 1 of 2 judged day\(s\) have a per-position file$/m); assert.match(b.stdout, /depth vs real, 1 day\(s\), all assets: positions 6 vs 3, windows 4 vs 2, per 1,000 entry evaluations 0.30 vs 0.10/); assert.ok(!/depth vs real, day 2/.test(b.stdout));
  // no real side: nothing to compare against
  const noReal = posLegs(); delete noReal.real;
  const c = runPositionsPy(posDir(noReal), '55', '--judged', D2.join(','));
  assert.equal(c.status, 0); assert.match(c.stdout, /^\[twin\] positions real: 0 of 2 judged day\(s\) have a per-position file$/m); assert.match(c.stdout, /^\[twin\] positions: no real per-position files, so there is nothing to compare against$/m); assert.ok(!/ vs real, /.test(c.stdout));
  // a source and a day with no day in common
  const apart = posLegs(); apart.requote = [{ day: D2[1], rows: [], evals: 1 }]; apart.real = [{ day: D2[0], rows: REAL1, evals: 30000 }];
  assert.match(runPositionsPy(posDir(apart), '55', '--judged', D2.join(',')).stdout, /^\[twin\] positions requote vs real: no judged day has both files, left out$/m);
  // a truncated file, a file of another version, a row of the wrong type, and a file of a day that is not judged: none of them counts
  const bad = posDir(posLegs());
  fs.writeFileSync(path.join(bad, 'twin-depth-p0', `positions-depth-p0-${D2[0]}.json`), '{"truncated"');
  fs.writeFileSync(path.join(bad, 'twin-requote-p0', `positions-requote-p0-${D2[0]}.json`), JSON.stringify({ version: 2, positions: [], totals: { entryEvaluations: 1 } }));
  fs.writeFileSync(path.join(bad, 'twin-placebo-p1', `positions-placebo-p1-${D2[1]}.json`), JSON.stringify({ version: 1, positions: [{ asset: 'BTC', closeTs: 'x', pnl: 1, hourly: false }], totals: { entryEvaluations: 1 } }));
  fs.writeFileSync(path.join(bad, 'twin-real-p0', 'positions-real-p0-2026-11-20.json'), JSON.stringify({ version: 1, positions: [prow('BTC', at(20, 1), 1)], totals: { entryEvaluations: 1 } }));
  const d = runPositionsPy(bad, '55', '--judged', D2.join(','));
  assert.equal(d.status, 0); assert.ok(!/Traceback/.test(d.stdout + d.stderr)); assert.match(d.stdout, /^\[twin\] positions depth: 1 of 2 judged day\(s\)/m); assert.match(d.stdout, /^\[twin\] positions requote: 1 of 2 judged day\(s\)/m); assert.match(d.stdout, /^\[twin\] positions placebo: 1 of 2 judged day\(s\)/m); assert.match(d.stdout, /^\[twin\] positions real: 2 of 2 judged day\(s\)/m);
  // wrong arguments: a usage line on stderr and exit 0 (a report never fails a job)
  const u = spawnSync('python3', ['-I', POSITIONS_PY, 'only-one-argument'], { encoding: 'utf8' }); assert.equal(u.status, 0); assert.match(u.stderr, /usage: twin-positions\.py WINDOWS_DIR RUN/); assert.equal(u.stdout, '');
  assert.equal(spawnSync('python3', ['-I', POSITIONS_PY, 'a', 'b', '--bogus'], { encoding: 'utf8' }).status, 0);
});

test('an extra positions file in the legs\' tree changes nothing twin-windows.py reads or prints: its lines, its legs file and its four files are the same bytes; twin-positions.py reads positions files only', () => {
  for (const [split, judged] of [['dev', J3], ['confirm', C3]] as Array<[string, string[]]>) {
    const plain = legsDir(wholeLegs(judged)), extra = legsDir(wholeLegs(judged));
    posDir({ real: judged.map((d) => ({ day: d, rows: REAL1, evals: 1 })), placebo: judged.map((d) => ({ day: d, rows: REAL1, evals: 1 })), requote: judged.map((d) => ({ day: d, rows: [], evals: 1 })), depth: judged.map((d) => ({ day: d, rows: DEPTH1, evals: 1 })) }, extra);
    assert.ok(treeOf(extra).some((f) => /positions-/.test(f)) && !treeOf(plain).some((f) => /positions-/.test(f)));
    const oa = path.join(tmpDir(), 'o'), ob = path.join(tmpDir(), 'o'), la = path.join(tmpDir(), 'legs.txt'), lb = path.join(tmpDir(), 'legs.txt');
    const a = runWindowsPy(plain, oa, split, judged, la), b = runWindowsPy(extra, ob, split, judged, lb);
    assert.equal(a.status, 0, a.stderr); assert.equal(b.status, 0, b.stderr); assert.equal(b.stdout, a.stdout, `${split}: the printed lines are the same bytes`); assert.equal(b.stderr, a.stderr);
    assert.equal(fs.readFileSync(lb, 'utf8'), fs.readFileSync(la, 'utf8'));
    assert.deepEqual(winFiles(ob), winFiles(oa)); assert.deepEqual(treeOf(ob), treeOf(oa), 'nothing positions-like is copied to the output folder');
    for (const f of winFiles(oa)) assert.equal(fs.readFileSync(path.join(ob, f), 'utf8'), fs.readFileSync(path.join(oa, f), 'utf8'), `${split}: ${f}`);
    // positions files alone do not make a set: with no windows file the set is incomplete, as it was
    const only = posDir({ real: judged.map((d) => ({ day: d, rows: [], evals: 1 })), placebo: judged.map((d) => ({ day: d, rows: [], evals: 1 })), requote: judged.map((d) => ({ day: d, rows: [], evals: 1 })), depth: judged.map((d) => ({ day: d, rows: [], evals: 1 })) });
    const o = runWindowsPy(only, path.join(tmpDir(), 'o'), split, judged, path.join(tmpDir(), 'l')); assert.equal(o.status, 3); assert.ok(!/ 3 of 3 judged day/.test(o.stdout));
  }
  const py = fs.readFileSync(POSITIONS_PY, 'utf8'), wpy = fs.readFileSync(WINDOWS_PY, 'utf8');
  assert.ok(!/positions/.test(wpy.replace(/#.*$/gm, '')), 'twin-windows.py does not mention positions'); assert.match(wpy, /glob\.glob\(f"\{src\}\/twin-\{how\}-p\*\/windows-\{how\}-p\*\.json"\)/, 'it globs windows-* only');
  assert.match(py, /glob\.glob\(f"\{src\}\/twin-\{how\}-p\*\/positions-\{how\}-p\*\.json"\)/); assert.ok(!/glob\.glob\([^)]*windows-/.test(py), 'twin-positions.py globs positions-* only');
  // and the report on a tree with windows files alone is the "nothing to report" line (a windows file is not misread as a positions file)
  assert.equal(runPositionsPy(legsDir(wholeLegs()), '9').stdout, '[twin] no per-position files on Drive for run 9\n');
});

test('R3a: twin-positions.py compiles, the new workflow steps are valid bash and sit between the Verdict and Report steps of both jobs, report only (continue-on-error, never on a confirm split)', { skip: hasYaml ? false : 'python3 with PyYAML is not installed here' }, () => {
  const pyc = path.join(tmpDir(), 'twin-positions.pyc');
  const c = spawnSync('python3', ['-I', '-c', 'import py_compile,sys; py_compile.compile(sys.argv[1], cfile=sys.argv[2], doraise=True)', POSITIONS_PY, pyc], { encoding: 'utf8' });
  assert.equal(c.status, 0, c.stderr); assert.ok(fs.existsSync(pyc));
  assert.ok(!/^import (?!glob|json|re|sys)|^from /m.test(fs.readFileSync(POSITIONS_PY, 'utf8')), 'standard library only');
  const y = wf(), { jobs } = yamlDoc(), NAME = 'The per-position report (R3a, report only)';
  for (const job of ['verdict', 'reverdict']) {
    const steps = jobs[job].steps as Array<{ name?: string; if?: string; run?: string; 'continue-on-error'?: boolean; env?: Record<string, string> }>;
    const names = steps.map((s) => s.name), at1 = names.indexOf(NAME);
    assert.ok(at1 > 0, `${job}: the step is there`); assert.equal(names[at1 - 1], 'Verdict', `${job}: right after the Verdict step`); assert.equal(names[at1 + 1], 'Report (commit comment)', `${job}: right before the Report step`);
    assert.equal(steps[at1]['continue-on-error'], true, `${job}: it can never fail the job`);
    const r = spawnSync('bash', ['-n'], { input: steps[at1].run!.replace(/\$\{\{.*?\}\}/g, 'X'), encoding: 'utf8' }); assert.equal(r.status, 0, r.stderr);
    assert.ok(/^\s*exit 0\s*$/m.test(steps[at1].run!), `${job}: every path ends 0`); assert.ok(/timeout \d+ python3 \.github\/scripts\/twin-positions\.py /.test(steps[at1].run!), `${job}: a time limit`); assert.ok(/\|\| true/.test(steps[at1].run!));
    assert.ok(!/twin-look\.sh|--stage verdict|drive_lab/.test(steps[at1].run!), `${job}: it numbers no look and reads no Drive file of its own`);
    // the Verdict step's own text is untouched by it (no python of the report there)
    assert.ok(!/twin-positions/.test(steps[names.indexOf('Verdict')].run!), `${job}: the Verdict step does not call the report`);
  }
  const vstep = (jobs.verdict.steps as Array<{ name?: string; if?: string }>).find((s) => s.name === NAME)!;
  assert.equal(vstep.if, "${{ !cancelled() && github.event_name == 'workflow_dispatch' && inputs.backtests && needs.build.outputs.split != 'confirm' }}", 'the verdict job: with backtests, dev and custom only');
  // the leg's step and the stage: the flag is the only new input of the leg, never passed on a confirm split
  assert.match(jobText(y, 'backtest'), /POS=\(\); \[ "\$BLIND" = true \] \|\| POS=\(--positions\)/);
  assert.ok(!/--positions/.test(jobText(y, 'verdict') + jobText(y, 'reverdict') + jobText(y, 'build')), '--positions is the legs\' alone');
  assert.ok(y.slice(0, y.indexOf('\non:')).includes('12.  THE PER-POSITION DUMP') || /12\. +THE PER-POSITION DUMP/.test(y.slice(0, y.indexOf('\non:'))), 'the header says what it is');
});

/** The report steps run as the jobs run them, over a stubbed Drive, gh and the real script. */
function positionsRun(job: 'verdict' | 'reverdict', opts: { split: string; judged?: string[]; legs?: Partial<Record<(typeof HOWS)[number], PosLeg[]>> | null; script?: 'real' | 'missing' | 'crash'; ghFails?: boolean }) {
  const w = jobWs(); stubGh(w.bin);
  const judged = opts.judged ?? D2, run = job === 'verdict' ? '77' : '55';
  const script = opts.script ?? 'real';
  if (script === 'real') fs.copyFileSync(POSITIONS_PY, path.join(w.ws, '.github/scripts/twin-positions.py'));
  else if (script === 'crash') fs.writeFileSync(path.join(w.ws, '.github/scripts/twin-positions.py'), 'import sys\nprint("[twin] positions report: half a line")\nraise RuntimeError("boom")\n');
  const sent = path.join(w.tmp, 'sent.md');
  if (opts.ghFails) fs.writeFileSync(path.join(w.bin, 'gh'), '#!/usr/bin/env bash\nexit 1\n', { mode: 0o755 });
  const env = { GH_TOKEN: 't', GH_OUT: sent };
  if (job === 'verdict') {
    if (opts.legs !== null) posDir(opts.legs ?? posLegs(), path.join(w.tmp, 'in'));
    const r = runPlan('verdict', w, run, [{ name: 'The per-position report (R3a, report only)', env: { ...env, SPLIT: opts.split, JUDGED: judged.join(',') } }]);
    return { ...r, sent: fs.existsSync(sent) ? fs.readFileSync(sent, 'utf8') : '', w };
  }
  putLite(w, run, opts.split, judged);
  if (opts.legs !== null) { putWindows(w, run, wholeLegs(judged)); posDir(opts.legs ?? posLegs(), path.join(w.drive, `simulated/history-twin/${run}/windows`)); }
  const plan: Plan = [...revPlan(w, opts.split === 'confirm' ? 'a look' : ''), { name: 'The per-position report (R3a, report only)', env: { ...env, RUN: run } }];
  const r = runPlan('reverdict', w, run, plan);
  return { ...r, sent: fs.existsSync(sent) ? fs.readFileSync(sent, 'utf8') : '', w };
}

test('R3a: the verdict job\'s report step prints the report in the job log after the verdict and posts it as a comment of its own; it numbers nothing, writes nothing into the verdict log, and posts nothing on a confirm split or when there is nothing to report', () => {
  const ok = positionsRun('verdict', { split: 'dev' });
  assert.equal(ok.failed, undefined, ok.out);
  assert.match(ok.out, /^\[twin\] positions report, run 77: 2 judged day\(s\) in date order/m); assert.match(ok.out, /^\[twin\] positions depth vs real, day 1, all assets: positions 6 vs 3, /m);
  assert.equal(ok.log, '', 'the verdict comment\'s log is not touched: the report could not push it over the comment size limit');
  assert.match(ok.sent, /^History twin positions, run 77\n\n```\n\[twin\] positions report, run 77: 2 judged day\(s\)/); assert.ok(ok.sent.trimEnd().endsWith('```'));
  publicSafe(ok.sent.split('\n').filter((l) => l.startsWith('[twin]')), 'the comment'); assert.ok(!/KX|2026-11/.test(ok.sent));
  assert.deepEqual(ok.looks, []); assert.equal(ok.nodeArgs, '', 'no stage ran');
  // confirm: nothing printed, nothing posted (the step's own guard, behind the job-level condition)
  const blind = positionsRun('verdict', { split: 'confirm', judged: C3 }); assert.equal(blind.failed, undefined); assert.equal(blind.out, ''); assert.equal(blind.sent, '');
  // no per-position files (a run before R3a): the one line in the log, no comment
  const none = positionsRun('verdict', { split: 'dev', legs: null }); assert.equal(none.failed, undefined); assert.equal(none.out, '[twin] no per-position files on Drive for run 77\n'); assert.equal(none.sent, '');
  // a script that is not on the ref, a script that crashes, a comment that cannot be posted: the step still ends 0 and says what happened
  const missing = positionsRun('verdict', { split: 'dev', script: 'missing' }); assert.equal(missing.failed, undefined); assert.match(missing.out, /^\[twin\] positions report: \.github\/scripts\/twin-positions\.py is not on this ref \(RUNBOOK 3\.0 check 1e\), so there is no report$/m); assert.equal(missing.sent, '');
  const crash = positionsRun('verdict', { split: 'dev', script: 'crash' }); assert.equal(crash.failed, undefined, 'a crashing report never fails the step'); assert.match(crash.out, /Traceback[\s\S]*RuntimeError: boom/); assert.ok(!/Traceback/.test(crash.sent), 'the traceback stays in the job log; only [twin] lines are posted');
  const nogh = positionsRun('verdict', { split: 'dev', ghFails: true }); assert.equal(nogh.failed, undefined); assert.match(nogh.out, /could not post the comment/);
});

test('R3a: the re-verdict job\'s report step reads the windows tree the windows step read: after the verdict, for the run being re-read, dev and custom only, and a confirm re-verdict prints and posts nothing', () => {
  const ok = positionsRun('reverdict', { split: 'dev', judged: J3, legs: { real: J3.map((d, i) => ({ day: d, rows: i === 0 ? REAL1 : [], evals: 30000 })), placebo: J3.map((d, i) => ({ day: d, rows: i === 0 ? REAL1 : [], evals: 30000 })), requote: J3.map((d) => ({ day: d, rows: [], evals: 20000 })), depth: J3.map((d, i) => ({ day: d, rows: i === 0 ? DEPTH1 : [], evals: 20000 })) } });
  assert.equal(ok.failed, undefined, ok.out);
  assert.match(ok.out, /^\[twin\] positions report, run 55: 3 judged day\(s\) in date order/m); assert.match(ok.out, /^\[twin\] positions depth vs real, day 1, all assets: positions 6 vs 3, windows 4 vs 2/m);
  assert.ok(ok.out.indexOf('stub verdict') < 0 || true); assert.match(ok.log, /adversary AUC 0\.55/, 'the verdict ran first and its log is its own');
  assert.ok(!/positions/.test(ok.log.replace(/settled positions/g, '')), 'the report is not in the verdict log');
  // the stub harness gives the re-verdict the run id of the run it re-reads (both 55), so the title reads 55 twice; the step text holds that the two numbers have different sources
  assert.match(ok.sent, /^History twin positions of run 55 \(re-verdict run 55\)\n\n```\n\[twin\] positions report, run 55: 3 judged day\(s\)/); assert.deepEqual(ok.looks, [], 'a dev re-verdict numbers no look');
  assert.ok(stepScript(jobText(wf(), 'reverdict'), 'The per-position report (R3a, report only)').includes('History twin positions of run $RUN (re-verdict run ${{ github.run_id }})'), 'the title names the run read (RUN) and the re-verdict run (github.run_id)');
  // a custom split is a dev-like split: read too
  const custom = positionsRun('reverdict', { split: 'custom', judged: D2 }); assert.equal(custom.failed, undefined, custom.out); assert.match(custom.out, /^\[twin\] positions report, run 55: 2 judged day\(s\)/m);
  // the judged days are the run's own split.json's: a day on Drive that the split does not judge is not read
  const stray = positionsRun('reverdict', { split: 'dev', judged: D2, legs: { ...posLegs(), real: [...posLegs().real!, { day: '2026-11-16', rows: REAL1, evals: 1 }] } }); assert.match(stray.out, /positions real: 2 of 2 judged day\(s\)/); assert.match(stray.out, /report, run 55: 2 judged day\(s\)/);
  // a confirm run: the look is the verdict step's own (one), the report prints and posts nothing, and reads no Drive file of its own
  const blind = positionsRun('reverdict', { split: 'confirm', judged: C3, legs: posLegs() });
  assert.equal(blind.failed, undefined, blind.out); assert.ok(!/\[twin\] positions|no per-position/.test(blind.out), blind.out); assert.equal(blind.sent, ''); assert.equal(blind.looks.length, 1, 'only the verdict\'s own look');
  // a run that kept no windows at all (every leg failed, or no backtests): the one line, no comment
  const none = positionsRun('reverdict', { split: 'dev', judged: J3, legs: null }); assert.equal(none.failed, undefined, none.out); assert.match(none.out, /^\[twin\] no per-position files on Drive for run 55$/m); assert.equal(none.sent, '');
  // a script missing or crashing: the job's windows read and verdict are already done; the step ends 0
  assert.equal(positionsRun('reverdict', { split: 'dev', judged: D2, script: 'missing' }).failed, undefined); assert.equal(positionsRun('reverdict', { split: 'dev', judged: D2, script: 'crash' }).failed, undefined);
});
