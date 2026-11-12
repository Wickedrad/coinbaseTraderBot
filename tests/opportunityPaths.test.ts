import './tmpScope'; // one temp folder per run, removed at exit
import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { buildAtlas } from '../research/opportunity/train';
import { HORIZONS_MIN, type MinuteCandle, type OpportunityEntry } from '../research/opportunity/atlas';
import { defaultPathConfig, hypotheticalPayoff, PathLabeler, pathPartition, PATH_LABEL_SCHEMA,
  type PathCosts, type PathLabel, type PathLabelConfig } from '../research/opportunity/pathLabels';

const MIN = 60_000;
const bar = (i: number, c: number, h = c, l = c, o = c): MinuteCandle => ({ ts: i * MIN, o, h, l, c, v: 1 });
const entry = (b: MinuteCandle): OpportunityEntry => ({ ts: b.ts + MIN, asset: 'BTC', price: b.c,
  f: { rsi: 30, macdBps: 1, bbPctB: 0.3, atrBps: 100, knownAt: b.ts + MIN,
    session: 'new_york', etHour: 10, btcdDailyChange: NaN, usdtdDailyChange: NaN } });
const config = (patch: Partial<PathLabelConfig> = {}): PathLabelConfig => ({
  ...defaultPathConfig('test-observed-ohlc', 10_000 * MIN, 20_000 * MIN),
  horizonsMin: [1, 3], targetsAtr: [1], stopsAtr: [1], ...patch,
});
const run = (future: MinuteCandle[], patch: Partial<PathLabelConfig> = {}): PathLabel[] => {
  const L = new PathLabeler(config(patch));
  const b = bar(0, 100, 200, 1);
  assert.equal(L.push(b, entry(b)).length, 0);
  return future.flatMap((b) => L.push(b));
};

test('path horizons use exactly the following minutes, preserve earlier rows and label both sides', () => {
  const rows = run([bar(1, 100, 100.5, 99.5, 100), bar(2, 101, 102, 100, 100), bar(3, 99, 101, 98, 101)]);
  assert.equal(rows.length, 4);
  const h1 = rows.find((r) => r.horizonMin === 1 && r.side === 'long')!;
  assert.equal(h1.firstHit, 'none');
  assert.equal(h1.firstTargetMinute, null);
  assert.ok(Math.abs(h1.mfeBps - 50) < 1e-8);
  assert.ok(Math.abs(h1.maeBps - 50) < 1e-8);
  assert.equal(h1.provenance.futureStartsAt, MIN);
  assert.equal(h1.provenance.labelKnownAt, 2 * MIN);
  const long = rows.find((r) => r.horizonMin === 3 && r.side === 'long')!;
  const short = rows.find((r) => r.horizonMin === 3 && r.side === 'short')!;
  assert.equal(long.firstHit, 'target'); assert.equal(short.firstHit, 'stop');
  assert.equal(long.firstTargetMinute, 2); assert.equal(long.firstStopMinute, 3);
  assert.deepEqual(long.firstHitWindow, { startsAt: 2 * MIN, knownAt: 3 * MIN });
  assert.ok(Math.abs(long.mfeBps - 200) < 1e-8);
  assert.ok(Math.abs(short.maeBps - 200) < 1e-8);
  assert.equal(h1.firstTargetMinute, null, 'later bars cannot mutate exported shorter horizons');
});

test('same-minute double touches remain ambiguous; their hypothetical payoff takes the stop', () => {
  for (const side of ['long', 'short']) {
    const r = run([bar(1, 100, 102, 98, 100)]).find((r) => r.side === side)!;
    assert.equal(r.firstHit, 'ambiguous');
    assert.equal(r.firstTargetMinute, 1); assert.equal(r.firstStopMinute, 1);
    assert.equal(r.exitPrice, side === 'long' ? 99 : 101);
    assert.ok(Math.abs(r.grossReturnBps! + 100) < 1e-8);
    assert.equal(r.provenance.ambiguity, 'stop-first-lower-bound');
    assert.equal(r.payoffBasis, 'ambiguous-lower-bound');
  }
});

test('the observed open orders gap touches; stops use the adverse open and targets their limit', () => {
  for (const [open, expectedLong, expectedShort] of [[103, 'target', 'stop'], [97, 'stop', 'target']] as const) {
    const rows = run([bar(1, 100, 104, 96, open)]);
    const long = rows.find((r) => r.side === 'long')!;
    const short = rows.find((r) => r.side === 'short')!;
    assert.equal(long.firstHit, expectedLong); assert.equal(short.firstHit, expectedShort);
    assert.equal(long.exitPrice, open === 103 ? 101 : 97);
    assert.equal(short.exitPrice, open === 103 ? 103 : 99);
  }
});

test('unit-position costs charge both legs, including fees on exit notional, on long and short', () => {
  const costs: PathCosts = { feePerSideBps: 10, halfSpreadBps: 2, slippagePerSideBps: 3 };
  const long = hypotheticalPayoff(100, 102, 1, costs);
  const short = hypotheticalPayoff(100, 98, -1, costs);
  const expected = (a: number, b: number, direction: number) => (direction * (b - a) - 0.001 * (a + b)) / a * 10000;
  assert.ok(Math.abs(long.netReturnBps - expected(100.05, 101.949, 1)) < 1e-8);
  assert.ok(Math.abs(short.netReturnBps - expected(99.95, 98.049, -1)) < 1e-8);
  assert.ok(long.netReturnBps < long.grossReturnBps);
  const r = run([bar(1, 102)], { costs }).find((r) => r.side === 'long')!;
  assert.deepEqual(r.provenance.costAssumptions, costs);
  assert.equal(r.netReturnBps, hypotheticalPayoff(100, 101, 1, costs).netReturnBps);
});

test('gaps and EOF censor incomplete horizons without invented prices or negative event labels', () => {
  const L = new PathLabeler(config({ horizonsMin: [3, 5] }));
  const b = bar(0, 100); L.push(b, entry(b)); L.push(bar(1, 100));
  const rows = L.push(bar(3, 110));
  assert.equal(rows.length, 4);
  for (const r of rows) {
    assert.equal(r.censorReason, 'gap'); assert.equal(r.observedMinutes, 1);
    assert.equal(r.provenance.observedThrough, 2 * MIN);
    assert.equal(r.provenance.labelKnownAt, 4 * MIN);
    assert.equal(r.firstHit, 'none'); assert.equal(r.payoffAvailable, false);
    assert.equal(r.netReturnBps, null); assert.equal(r.mfeBps, 0);
    assert.ok(r.reversals.every((r) => r.occurred === null));
  }
  assert.deepEqual(L.finish(), []);
  const last = bar(4, 100); L.push(last, entry(last));
  const eof = L.finish();
  assert.ok(eof.every((r) => r.censorReason === 'end-of-input' && r.observedMinutes === 0));
  assert.deepEqual(L.finish(), [], 'finishing twice must not duplicate censored rows');
});

test('an already observed barrier payoff survives censoring of the remaining horizon', () => {
  const L = new PathLabeler(config({ horizonsMin: [5] }));
  const b = bar(0, 100); L.push(b, entry(b)); L.push(bar(1, 101));
  const r = L.finish('processing-limit').find((r) => r.side === 'long')!;
  assert.equal(r.censorReason, 'processing-limit');
  assert.equal(r.firstHit, 'target'); assert.equal(r.payoffAvailable, true);
  assert.equal(r.exitPrice, 101);
  assert.ok(r.netReturnBps! > 0);
});

test('reversal and continuation require a causal preceding drift, turn and consecutive sustained closes', () => {
  for (const direction of [1, -1]) {
    const L = new PathLabeler(config({ horizonsMin: [1, 3, 5], reversals: [
      { id: 'turn', lookbackMin: 2, precedingDriftAtr: 0.5, turnAtr: 0.5, sustainMin: 2 },
    ] }));
    L.push(bar(0, 100 + direction * 2)); L.push(bar(1, 100 + direction));
    const b = bar(2, 100); L.push(b, entry(b));
    // First turn fails to sustain; a new run starts at minute 3 and confirms at 4.
    const closes = [100 + direction, 100, 100 + direction, 100 + direction, 100 + direction];
    const rows = closes.flatMap((c, i) => L.push(bar(i + 3, c)));
    const h1 = rows.find((r) => r.horizonMin === 1 && r.side === (direction === 1 ? 'long' : 'short'))!;
    assert.equal(h1.reversals[0].occurred, false);
    assert.equal(h1.reversals[0].onsetMinute, null, 'an unconfirmed candidate is not a reversal onset');
    const h5 = rows.find((r) => r.horizonMin === 5 && r.side === h1.side)!;
    assert.equal(h5.reversals[0].context, 'reversal');
    assert.equal(h5.reversals[0].onsetMinute, 3);
    assert.equal(h5.reversals[0].confirmedMinute, 4);
    assert.equal(h5.reversals[0].occurred, true);
    assert.ok(h5.reversals[0].priorMoveAtr! < 0);
    assert.equal(h1.reversals[0].confirmedMinute, null);
  }
  const L = new PathLabeler(config({ horizonsMin: [1], reversals: [
    { id: 'continue', lookbackMin: 1, precedingDriftAtr: 0.5, turnAtr: 0.5, sustainMin: 1 },
  ] }));
  L.push(bar(0, 99)); const b = bar(1, 100); L.push(b, entry(b));
  const r = L.push(bar(2, 101)).find((r) => r.side === 'long')!;
  assert.equal(r.reversals[0].context, 'continuation');
  assert.equal(r.reversals[0].occurred, true);
});

test('split crossing is purged on the planned horizon even for early hits and censored prefixes', () => {
  const splits = { trainBefore: 3 * MIN, finalFrom: 5 * MIN };
  assert.equal(pathPartition(MIN, 3 * MIN, splits), 'train');
  assert.equal(pathPartition(MIN, 4 * MIN, splits), 'purged');
  assert.equal(pathPartition(3 * MIN, 5 * MIN, splits), 'development');
  assert.equal(pathPartition(4 * MIN, 6 * MIN, splits), 'purged');
  assert.equal(pathPartition(5 * MIN, 7 * MIN, splits), 'final');
  const rows = run([bar(1, 101)], splits);
  assert.equal(rows[0].partition, 'train');
  const L = new PathLabeler(config({ ...splits, horizonsMin: [5] }));
  const b = bar(0, 100); L.push(b, entry(b)); L.push(bar(1, 101));
  assert.ok(L.finish().every((r) => r.partition === 'purged'));
});

test('malformed candles, future features, nonpositive barriers and invalid grids fail before changing state', () => {
  assert.throws(() => new PathLabeler(config({ targetsAtr: [1, 1] })), /grids/);
  assert.throws(() => new PathLabeler(config({ horizonsMin: [5, 1] })), /horizons/);
  assert.throws(() => new PathLabeler(config({ costs: { feePerSideBps: NaN, halfSpreadBps: 0, slippagePerSideBps: 0 } })), /cost/);
  const L = new PathLabeler(config()); const b = bar(0, 100); const e = entry(b);
  assert.throws(() => L.push({ ...b, ts: 1 }), /candle/);
  assert.throws(() => L.push(b, { ...e, f: { ...e.f, knownAt: 2 * MIN } }), /entry/);
  assert.throws(() => L.push(b, { ...e, f: { ...e.f, atrBps: 10000 } }), /barrier/);
  L.push(b, e);
  assert.throws(() => L.push(b), /increasing/);
  const r = L.push(bar(1, 101))[0];
  assert.equal(r.observedMinutes, 1);
});

test('constructor and entry inputs are snapshotted against later mutation', () => {
  const cfg = config(); const L = new PathLabeler(cfg);
  const b = bar(0, 100); const e = entry(b); L.push(b, e);
  cfg.targetsAtr[0] = 9; cfg.costs.feePerSideBps = 999; e.f.atrBps = 900;
  const r = L.push(bar(1, 102))[0];
  assert.equal(r.targetPrice, 101); assert.equal(r.entry.f.atrBps, 100);
  assert.equal(r.provenance.costAssumptions.feePerSideBps, 0);
});

test('all horizons and target/stop pairs match independent direct scans on randomized observed OHLC', () => {
  let seed = 92;
  const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 2 ** 32; };
  const bars = [bar(0, 100, 1000, 1)];
  for (let i = 1; i <= 1440; i++) {
    const o = 100 + (random() - 0.5) * 2, c = 100 + (random() - 0.5) * 2;
    bars.push(bar(i, c, Math.max(o, c) + random(), Math.min(o, c) - random(), o));
  }
  const cfg = config({ horizonsMin: [...HORIZONS_MIN], targetsAtr: [0.5, 1, 2], stopsAtr: [0.5, 1, 2] });
  const rows = run(bars.slice(1), cfg);
  assert.equal(rows.length, 2 * 8 * 3 * 3);
  for (const r of rows) {
    const dir = r.side === 'long' ? 1 : -1;
    const future = bars.slice(1, r.horizonMin + 1);
    const targetAt = future.findIndex((b) => dir === 1 ? b.h >= r.targetPrice : b.l <= r.targetPrice);
    const stopAt = future.findIndex((b) => dir === 1 ? b.l <= r.stopPrice : b.h >= r.stopPrice);
    assert.equal(r.firstTargetMinute, targetAt < 0 ? null : targetAt + 1);
    assert.equal(r.firstStopMinute, stopAt < 0 ? null : stopAt + 1);
    let hit: PathLabel['firstHit'] = 'none', exit = future.at(-1)!.c;
    if (targetAt >= 0 || stopAt >= 0) {
      const i = Math.min(targetAt < 0 ? Infinity : targetAt, stopAt < 0 ? Infinity : stopAt);
      const first = future[i];
      if (dir * (first.o - r.targetPrice) >= 0) { hit = 'target'; exit = r.targetPrice; }
      else if (dir * (first.o - r.stopPrice) <= 0) { hit = 'stop'; exit = first.o; }
      else if (targetAt === stopAt) { hit = 'ambiguous'; exit = r.stopPrice; }
      else if (i === targetAt) { hit = 'target'; exit = r.targetPrice; }
      else { hit = 'stop'; exit = r.stopPrice; }
    }
    assert.equal(r.firstHit, hit); assert.equal(r.exitPrice, exit);
    const high = Math.max(100, ...future.map((b) => b.h)), low = Math.min(100, ...future.map((b) => b.l));
    assert.ok(Math.abs(r.mfeBps - (dir === 1 ? high / 100 - 1 : 1 - low / 100) * 10000) < 1e-8);
    assert.ok(Math.abs(r.maeBps - (dir === 1 ? 1 - low / 100 : high / 100 - 1) * 10000) < 1e-8);
    assert.equal(r.netReturnBps, hypotheticalPayoff(100, exit, dir, cfg.costs).netReturnBps);
  }
});

function historyFixture(): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-paths-'));
  const dir = path.join(root, 'history', 'binance-1m', 'BTC'); fs.mkdirSync(dir, { recursive: true });
  const rows = ['ts,o,h,l,c,v'];
  for (let i = 0; i < 2200; i++) {
    if (i === 1000) continue;
    const c = 100 + Math.sin(i / 50); rows.push(`${i * MIN},${c},${c + 1},${c - 1},${c},1`);
  }
  fs.writeFileSync(path.join(dir, '1m.csv'), rows.join('\n') + '\n');
  return root;
}

test('shared history stream exports censored path rows without changing the Phase 1 fit or scores', async () => {
  const root = historyFixture();
  try {
    const options = { historyDir: path.join(root, 'history'), assets: ['BTC'], trainBefore: 1200 * MIN,
      finalFrom: 1800 * MIN, maxMinutes: 2000 };
    const baseline = await buildAtlas(options);
    const rows: PathLabel[] = [];
    const actual = await buildAtlas({ ...options, pathLabels: { config: { targetsAtr: [1], stopsAtr: [1] },
      onLabels: (batch) => { rows.push(...batch); } } });
    assert.deepEqual(actual, baseline);
    assert.ok(rows.some((r) => r.censorReason === 'gap'));
    assert.ok(rows.some((r) => r.censorReason === 'processing-limit'));
    assert.ok(rows.some((r) => r.partition === 'train'));
    assert.ok(rows.some((r) => r.partition === 'development'));
    assert.ok(rows.some((r) => r.partition === 'final'));
    const e = rows[0].entry.ts;
    assert.equal(rows.filter((r) => r.entry.ts === e).length, HORIZONS_MIN.length * 2);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test('CLI exports a self-describing label dataset and cleans temporary output on failed input', () => {
  const root = historyFixture();
  const invoke = (args: string[]) => spawnSync(process.execPath, ['--import', 'tsx', 'research/opportunity/train.ts',
    '--history', path.join(root, 'history'), '--source', 'binance-1m', '--train-before', new Date(1200 * MIN).toISOString(),
    '--final-from', new Date(1800 * MIN).toISOString(), '--path-targets-atr', '1', '--path-stops-atr', '1', ...args],
  { cwd: process.cwd(), encoding: 'utf8', timeout: 30000 });
  try {
    const labels = path.join(root, 'labels.jsonl'), report = path.join(root, 'report.json');
    const r = invoke(['--assets', 'BTC', '--out', report, '--path-labels', labels, '--max-minutes', '2000', '--path-fee-bps', '4']);
    assert.equal(r.status, 0, r.stderr);
    const records = fs.readFileSync(labels, 'utf8').trim().split('\n').map((s) => JSON.parse(s));
    const metadata = records.shift();
    assert.equal(metadata.schema, PATH_LABEL_SCHEMA); assert.equal(metadata.executable, false);
    assert.equal(metadata.config.costs.feePerSideBps, 4);
    assert.equal(JSON.parse(fs.readFileSync(report, 'utf8')).pathLabels.rows, records.length);
    assert.ok(records.length > 0);
    const failed = path.join(root, 'failed.jsonl');
    const fail = invoke(['--assets', 'BTC,ETH', '--out', report, '--path-labels', failed, '--max-minutes', '2000']);
    assert.notEqual(fail.status, 0);
    assert.equal(fs.existsSync(failed), false);
    assert.equal(fs.readdirSync(root).some((name) => name.endsWith('.tmp')), false);
    const unsafe = invoke(['--assets', 'BTC', '--out', report, '--path-labels', path.join(root, 'history', 'labels.jsonl')]);
    assert.notEqual(unsafe.status, 0); assert.match(unsafe.stderr, /outside the input/);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});


test('gap detection cannot make a censored label available before the gap was observed', () => {
  const L = new PathLabeler(config({ horizonsMin: [2], trainBefore: 3 * MIN, finalFrom: 5 * MIN }));
  const b = bar(0, 100); L.push(b, entry(b)); L.push(bar(1, 100));
  const rows = L.push(bar(4, 100));
  for (const r of rows) {
    assert.equal(r.provenance.plannedThrough, 3 * MIN);
    assert.equal(r.provenance.observedThrough, 2 * MIN);
    assert.equal(r.provenance.labelKnownAt, 5 * MIN);
    assert.equal(r.partition, 'purged');
  }
});
