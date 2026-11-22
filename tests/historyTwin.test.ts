import assert from 'node:assert/strict';
import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import crypto from 'crypto';
import {
  assertDisjoint, assertModelFitDays, assertHeldOut, auc, CONFIRM_DAYS, checkReal15m, corrMatrix, dayRows, discriminate, discriminatePerDay, FEATURES, isBlind, MIN_CUSTOM_JUDGED_DAYS,
  outcome, parseDays, parseFailedSteps, prepDay, prepReport, prepStatus, quantile, quantiles3, real15mError, real15mTag, REAL15M_VERSION, resolveSplit, type Row, SPLITS, stageVerdict, stressAuc,
  topCorrDiffs, twinSource,
} from '../research/historyTwin';
import { tmpDir } from './helpers';

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
  assert.equal([...y.matchAll(/max-parallel: 7\b/g)].length, 2, 'the prep and the backtest matrices are both 7 wide');
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
function verdictStep(opts: { split: string; backtests?: boolean; result?: string; judged?: string[]; have?: Record<string, string[]>; parts?: number }) {
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
  const r = bash(stepScript(y, 'Verdict'), { PATH: `${bin}:${process.env.PATH}`, RUNNER_TEMP: tmp, LOOK_N: '', LOOK_NOTE: '', BACKTESTS: opts.backtests === false ? 'false' : 'true', BT_RESULT: opts.result ?? 'success', JUDGED: judged.join(','), SPLIT: opts.split }, ws);
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
