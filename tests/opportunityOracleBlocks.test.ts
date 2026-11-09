import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { gunzipSync } from 'node:zlib';
import { test } from 'node:test';
import { rsi } from '../bot/ta/indicators';
import { FifteenMinuteIndicators, OpportunityLabeler, type Outcome } from '../research/opportunity/atlas';
import { buildFullOracle, queryFullOracle, walkFullOracle } from '../research/opportunity/oracleBlocksCli';
import { ORACLE_AXES, ORACLE_EMBARGO_MS, ORACLE_HORIZON_SIZE, ORACLE_STATS, ORACLE_SURFACES, OracleFeatures, OracleMatrix,
  oracleAnswer, oracleCoordinates, oracleEntry, oracleQuarter, ORACLE_LAYOUT_ID } from '../research/opportunity/oracleMatrix';
import { ORACLE_BLOCK_STUDY_ID, PROSPECTIVE_STUDY_ID, studyPolicy } from '../research/opportunity/studyPolicy';

const MIN = 60000;
const bar = (ts: number, c = 100) => ({ ts, o: c, h: c + 0.1, l: c - 0.1, c, v: 10 });
test('dense closed-bar indicators preserve native RSI and original 15m defaults', () => {
  const fast = new FifteenMinuteIndicators(1), original = new FifteenMinuteIndicators(), explicit = new FifteenMinuteIndicators(15), closes: number[] = [];
  for (let j = 0; j < 1000; j++) {
    const b = bar(j * MIN, 100 + Math.sin(j / 9)); closes.push(b.c);
    const a = fast.push(b)!;
    if (j >= 20) assert.ok(Math.abs(a.rsi - rsi(closes).at(-1)!) < 1e-8);
    assert.deepEqual(original.push(b), explicit.push(b));
  }
  assert.throws(() => new FifteenMinuteIndicators(0), /period/);
});
test('Oracle horizons use exact future minutes and omit an entry candle high; gaps censor rather than label sideways', () => {
  const f = new OracleFeatures(), labeler = new OpportunityLabeler([15, 60]); let checked = 0;
  for (let j = 0; j < 1000; j++) {
    const b = bar(j * MIN, 100 + j / 1000), feature = f.push(b);
    const rows = labeler.push(b, oracleEntry('BTC', b, feature));
    for (const o of rows) {
      assert.equal(o.resolvedAt, o.entry.ts + o.horizonMin * MIN); assert.ok([15, 60].includes(o.horizonMin));
      assert.ok(Math.abs(o.returnBps - 10000 * Math.log(b.c / o.entry.price)) < 1e-9); checked++;
    }
  }
  assert.ok(checked > 1000);
  const before = f.push(bar(1001 * MIN)); assert.equal(f.gaps, 1); assert.ok(Number.isNaN(before.atrBps));
  assert.equal(labeler.push(bar(1001 * MIN)).length, 0);
  assert.throws(() => labeler.push(bar(1001 * MIN)), /non-increasing/);
});
test('up/down/sideways answers have an explicit causal volatility-relative neutral band', () => {
  const outcome = { entry: { ts: MIN, f: { atrBps: 20 } }, resolvedAt: 16 * MIN, horizonMin: 15, returnBps: 4, maxUpBps: 8, maxDownBps: 2 } as Outcome;
  assert.equal(oracleAnswer(outcome).category, 1); assert.equal(oracleAnswer(outcome).neutralBps, 5);
  assert.equal(oracleAnswer({ ...outcome, returnBps: 6 }).category, 0);
  assert.equal(oracleAnswer({ ...outcome, returnBps: -6 }).category, 2);
  assert.equal(oracleAnswer({ ...outcome, horizonMin: 60, resolvedAt: 61 * MIN }).neutralBps, 10);
});
test('all single/pair tables conserve fractional evidence and missing values earn no relationship evidence', () => {
  const m = new OracleMatrix(), raw = ORACLE_AXES.map(() => 0.3), c = oracleCoordinates(raw);
  const y = { at: MIN, knownAt: 16 * MIN, horizon: 15 as const, neutralBps: 1, category: 0 as const, returnBps: 3, maxUpBps: 5, maxDownBps: 2 };
  m.add(y, c);
  assert.equal(ORACLE_SURFACES.length, 406);
  for (const s of ORACLE_SURFACES) {
    let count = 0; for (let cell = 0; cell < s.cells; cell++) count += m.data[s.offset + cell * ORACLE_STATS.length];
    assert.ok(Math.abs(count - 1) < 1e-10);
  }
  assert.equal(m.data[ORACLE_HORIZON_SIZE], 0);
  const missing = new OracleMatrix(); missing.add(y, oracleCoordinates(raw.map(() => NaN)));
  assert.equal(missing.rows(15), 1); assert.ok(missing.data.slice(7).every((v) => v === 0));
  assert.throws(() => m.predict(15, c, y.knownAt), /future/);
});
test('continuous pair responses can preserve an XOR relationship invisible to either marginal', () => {
  const m = new OracleMatrix();
  for (let n = 0; n < 800; n++) for (const a of [0, 100]) for (const b of [-2, 2]) {
    const raw = ORACLE_AXES.map(() => NaN); raw[0] = a; raw[1] = b;
    const up = (a === 100) !== (b === 2);
    m.add({ at: MIN, knownAt: 16 * MIN, horizon: 15, neutralBps: 1, category: up ? 0 : 2, returnBps: up ? 10 : -10, maxUpBps: 10, maxDownBps: 10 }, oracleCoordinates(raw));
  }
  const raw = ORACLE_AXES.map(() => NaN); raw[0] = 100; raw[1] = -2;
  const q = m.predict(15, oracleCoordinates(raw), 16 * MIN + ORACLE_EMBARGO_MS);
  assert.ok(q.p[0] > q.baseline[0] + 0.08); assert.ok(Math.abs(q.p.reduce((a, b) => a + b, 0) - 1) < 1e-12);
  const near = [...raw]; near[0] -= 1e-6;
  assert.ok(Math.abs(m.predict(15, oracleCoordinates(near), 16 * MIN + ORACLE_EMBARGO_MS).p[0] - q.p[0]) < 1e-6);
});
test('quarter storage checkpoints preserve features; the new registration preserves the older study and fresh final boundary', () => {
  const a = new OracleFeatures(), b = new OracleFeatures(), start = Date.UTC(2020, 2, 31, 16);
  for (let j = 0; j < 1100; j++) {
    const candle = bar(start + j * MIN, 100 + Math.sin(j / 17));
    const x = a.push(candle); if (oracleQuarter(x.at).id === '2020-Q2') JSON.stringify(a.checkpoint());
    assert.deepEqual(x.raw, b.push(candle).raw);
  }
  assert.equal(studyPolicy(PROSPECTIVE_STUDY_ID).trainBefore, Date.parse('2026-10-29'));
  assert.equal(studyPolicy(ORACLE_BLOCK_STUDY_ID).finalFrom, Date.parse('2026-11-09'));
});
async function fixture(root: string, futureScale: number) {
  const archive = path.join(root, 'archive'), file = path.join(archive, 'history/archive-binance-1m-quarantined-v1/BTC/1m.csv');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  let csv = 'ts,o,h,l,c,v\n';
  for (const [segment, start] of [Date.UTC(2017, 8, 28), Date.UTC(2017, 9, 1), Date.UTC(2018, 0, 1)].entries()) {
    for (let j = 0; j < 900; j++) {
      const c = 100 + (segment === 2 ? futureScale : 1) * Math.sin(j / 19) + j / 1000;
      csv += [start + j * MIN, c, c + 0.1, c - 0.1, c, 10].join(',') + '\n';
    }
  }
  csv += [Date.parse('2026-11-09'), 100, 101, 99, 100, 10].join(',') + '\n';
  fs.writeFileSync(file, csv);
  fs.writeFileSync(path.join(archive, 'archive-validation.json'), JSON.stringify({ schema: 'atlas-archive-audit-v1', files: [
    { path: 'archive-binance-1m-quarantined-v1/BTC/1m.csv', ready: true, sha256: createHash('sha256').update(csv).digest('hex') },
  ] }));
  const oracle = await buildFullOracle({ archive, asset: 'BTC', out: path.join(root, 'oracle') });
  const walk = await walkFullOracle({ archive, asset: 'BTC', oracle: path.join(root, 'oracle'), out: path.join(root, 'walk'), minimumTrainingDays: 1 });
  return { oracle, walk };
}
test('Oracle-first block exports and unseen-to-fold replay exclude future blocks, reserved final labels, SNN claims and invented contract profit', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-oracle-blocks-')); t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const first = await fixture(path.join(root, 'a'), 1), changedFuture = await fixture(path.join(root, 'b'), 4);
  assert.equal(first.oracle.observedMinutes, 2700); assert.equal(first.oracle.blocks.length, 3);
  assert.ok(first.oracle.completedAnswers[15] > 1800); assert.ok(first.oracle.completedAnswers[60] > 1700);
  const earlier = first.walk.folds.find((f) => f.quarter === '2017-Q4')!;
  assert.ok(earlier.targets[15].rows > 500); assert.deepEqual(earlier, changedFuture.walk.folds.find((f) => f.quarter === earlier.quarter));
  assert.deepEqual(first.walk.frozenModels[1], changedFuture.walk.frozenModels[1]);
  for (const s of first.walk.frozenModels) {
    const match = /^(\d{4})-Q([1-4])$/.exec(String(s.quarter))!;
    assert.ok(Number(s.trainedThrough) + ORACLE_EMBARGO_MS <= Date.UTC(Number(match[1]), (Number(match[2]) - 1) * 3, 1));
  }
  assert.equal(first.walk.contractProfitVerified, false); assert.equal(first.walk.nativeSnnTrained, false); assert.equal(first.walk.finalHoldoutUsed, false);
  const model = path.join(root, 'a/walk/model.json'), at = Date.UTC(2018, 0, 2);
  const request = { asset: 'BTC', source: 'archive-binance-1m-quarantined-v1', asOf: at, featuresKnownAt: at, layoutId: ORACLE_LAYOUT_ID, horizon: 15 as const, raw: ORACLE_AXES.map(() => 0.5) };
  const q = await queryFullOracle(model, request);
  assert.ok(Math.abs(Object.values(q.probabilities).reduce((a, b) => a + b, 0) - 1) < 1e-9); assert.equal(q.liveEntryAllowed, false);
  await assert.rejects(queryFullOracle(model, { ...request, asOf: Date.UTC(2017, 9, 1), featuresKnownAt: Date.UTC(2017, 9, 1) }), /future/);
  await assert.rejects(queryFullOracle(model, { ...request, featuresKnownAt: at + MIN }), /clock/);
  await assert.rejects(queryFullOracle(model, { ...request, source: 'tvdatafeed-coinbase' }), /source/);
  const csv = gunzipSync(fs.readFileSync(path.join(root, 'a/walk/relationship-spectra.csv.gz'))).toString();
  assert.ok(csv.startsWith('horizon_min,relationship')); assert.ok(csv.includes('m1:rsi x m1:macd_hist_atr'));
  const manifest = path.join(root, 'a/oracle/2017-Q3/manifest.json'); fs.appendFileSync(manifest, ' ');
  await assert.rejects(walkFullOracle({ archive: path.join(root, 'a/archive'), asset: 'BTC', oracle: path.join(root, 'a/oracle'), out: path.join(root, 'bad') }), /block changed/);
});
