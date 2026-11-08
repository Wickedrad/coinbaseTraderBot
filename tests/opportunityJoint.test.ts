import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { rng } from '../research/stats';
import { exportDecisionDataset } from '../research/opportunity/decisionDatasetCli';
import { exportJointPathStudy } from '../research/opportunity/jointPathCli';
import { encodePathFrame, FROZEN_FINAL_FROM, FROZEN_TRAIN_BEFORE, loadJointPathDataset, pathQueryValues, riskRows, selectPathEpisodes,
  type JointPathDataset, type PathDecision, type PathObservation } from '../research/opportunity/jointPathData';
import { JOINT_PATH_SCHEMA, planRiskFolds, predictJointPath, trainJointPaths, validateRiskModel, type FoldPlan } from '../research/opportunity/jointPathLearner';
import { ATLAS_FEATURE_SCHEMA, type AtlasFeatureFrame, type MinuteEntryAnchor } from '../research/opportunity/features';
import { TANET_SCHEMA } from '../bot/ta/taNet';

const MIN = 60000, start = Date.UTC(2023, 0, 2), anchorDefinition = 'builtin-ATR14-over-last-1440-contiguous-1m-bars' as const;
const plan: FoldPlan = { trainMs: 1000 * MIN, stoppingMs: 300 * MIN, calibrationMs: 300 * MIN,
  evaluationMs: 500 * MIN, stepMs: 500 * MIN, embargoMs: 3 * MIN, maxFolds: 1 };
const params = { nTrees: 48, maxDepth: 3, minLeafWeight: 5, learningRate: 0.12, featureFraction: 1, maxBins: 12 };
function frame(at: number, x = 0.8, z = 0.8): AtlasFeatureFrame {
  return { schema: ATLAS_FEATURE_SCHEMA, taSchema: TANET_SCHEMA, engine: 'builtin', asset: 'BTC', decisionAt: at,
    session: 'asia', gapsSeen: 0, groups: { micro: { source: 'synthetic', sha256: null, timeframe: 'micro',
      status: 'ready', bars: 1, firstOpen: at - MIN, lastOpen: at - MIN, knownAt: at, publicationLagMs: 0,
      timing: 'synthetic fixture', values: { x, z } } } };
}
const anchor = (at: number): MinuteEntryAnchor => ({ price: 100, atrBps: 100, knownAt: at, firstOpen: at - MIN, definition: anchorDefinition });
function planted(): JointPathDataset {
  const random = rng(49), decisions = new Map<string, PathDecision>(), paths: PathObservation[] = [];
  for (let i = 0; i < 2400; i++) {
    const at = start + i * MIN, id = `synthetic-${i}`, x = random() * 2 - 1, z = random() * 2 - 1;
    decisions.set(id, { id, at, asset: 'BTC', values: encodePathFrame(frame(at, x, z)), engine: 'builtin', inputSha256: 'synthetic', price: 100, atrBps: 100, anchorDefinition });
    for (const side of ['long', 'short'] as const) {
      let hitMinute: number | null = null;
      for (let minute = 1; minute <= 3; minute++) if (random() < 0.32 + minute * 0.02) { hitMinute = minute; break; }
      // Continuous joint state with a conditional sign change, rather than indicator votes.
      const signed = (side === 'long' ? 1 : -1) * x * (1.2 + 4 * z);
      const cause = hitMinute === null ? 'none' : random() < 0.1 ? 'ambiguous' : random() < 1 / (1 + Math.exp(-signed)) ? 'target' : 'stop';
      paths.push({ decisionId: id, at, asset: 'BTC', side, targetAtr: 1, stopAtr: 1, horizonMin: 3, observedMinutes: 3,
        cause, hitMinute, plannedThrough: at + 3 * MIN, knownAt: at + 3 * MIN, censored: false });
    }
  }
  return { decisions, paths, runId: 'synthetic', manifestSha256: 'synthetic', inputHashes: {}, trainBefore: FROZEN_TRAIN_BEFORE,
    finalFrom: FROZEN_FINAL_FROM, maxHorizonMin: 3, counts: { decisions: decisions.size, reserved: 0, paths: paths.length, eligiblePaths: paths.length } };
}
let cached: ReturnType<typeof trainJointPaths> | undefined;
const fitted = () => cached ??= trainJointPaths(planted(), { plan, params });

test('joint risk learner learns the planted conditional relationship beyond the geometry baseline', async () => {
  const r = await fitted();
  assert.equal(r.folds.length, 1);
  const f = r.folds[0];
  assert.ok(f.modelLoss < f.baselineLoss - 0.015, `${f.modelLoss} vs ${f.baselineLoss}`);
  assert.ok(f.model.featureNames.includes('value:micro:x')); assert.ok(f.model.featureNames.includes('value:micro:z'));
  assert.ok(f.model.heads.targetGivenClear.model.trees.length > 0);
  assert.equal(r.weeklyEvidence.pairedLogLossGain, null, 'one short interval is not independent weekly validation');
  assert.equal(r.liveEntryAllowed, false); assert.equal(r.calibrationRef, null);
});

test('competing first-hit curves sum to one, remain nested across horizons and preserve ambiguous order', async () => {
  const model = (await fitted()).folds[0].model, at = model.knownAt + MIN;
  const q = { side: 'long' as const, targetAtr: 1, stopAtr: 1, horizonMin: 3 };
  const p = predictJointPath(model, frame(at), anchor(at), q)!;
  assert.ok(p); assert.equal(p.kind, 'spot-barrier-first-hit');
  let previous = { none: 1, target: 0, stop: 0, ambiguous: 0 };
  for (const current of p.curve) {
    assert.ok(Math.abs(Object.values(current).reduce((a, b) => a + b, 0) - 1) < 1e-12);
    assert.ok(current.none <= previous.none);
    for (const key of ['target', 'stop', 'ambiguous'] as const) assert.ok(current[key] >= previous[key]);
    previous = current;
  }
  assert.deepEqual(p.curve[0], predictJointPath(model, frame(at), anchor(at), { ...q, horizonMin: 1 })!.probabilities);
  assert.ok(p.targetFirstOrderRange.includingAmbiguous > p.targetFirstOrderRange.identified);
  assert.equal(p.calibrationRef, null); assert.equal(p.liveEntryAllowed, false);
});

test('serialization keeps prediction parity and rejects unsupported times, parameters and corrupt models', async () => {
  const model = (await fitted()).folds[0].model, copy = JSON.parse(JSON.stringify(model)), at = model.knownAt + MIN;
  validateRiskModel(copy);
  const q = { side: 'long' as const, targetAtr: 1, stopAtr: 1, horizonMin: 3 };
  assert.deepEqual(predictJointPath(copy, frame(at), anchor(at), q), predictJointPath(model, frame(at), anchor(at), q));
  assert.equal(predictJointPath(model, frame(model.knownAt - MIN), anchor(model.knownAt - MIN), q), null);
  for (const patch of [{ horizonMin: 1.5 }, { horizonMin: 4 }, { targetAtr: 2 }]) assert.equal(predictJointPath(model, frame(at), anchor(at), { ...q, ...patch }), null);
  assert.equal(predictJointPath(model, frame(at), { ...anchor(at), atrBps: 20000 }, q), null);
  assert.equal(predictJointPath(model, { ...frame(at), engine: 'talib' }, anchor(at), q), null);
  copy.heads.event.model.baseScore += 1;
  assert.throws(() => validateRiskModel(copy), /content ID/);
  const cycle = structuredClone(model);
  cycle.heads.event.model.trees = [[{ f: 0, t: 0, l: 1, r: 1, ml: false, v: 0 }, { f: 0, t: 0, l: 1, r: 1, ml: false, v: 0 }]];
  assert.throws(() => validateRiskModel(cycle), /cyclic/);
});

test('evaluation labels and evaluation-only input columns cannot change fitting or calibration', async () => {
  const data = planted(), windows = planRiskFolds(data, plan), cut = windows[0].evaluation.from;
  for (const d of data.decisions.values()) if (d.at >= cut) d.values['value:micro:future_only'] = 999;
  for (const p of data.paths) if (p.at >= cut) { p.cause = 'none'; p.hitMinute = null; }
  const changed = await trainJointPaths(data, { plan, params }), original = await fitted();
  assert.deepEqual(changed.folds[0].model, original.folds[0].model);
  assert.ok(!changed.folds[0].model.featureNames.includes('value:micro:future_only'));
  assert.equal(changed.folds[0].model.knownAt, windows[0].calibration.through);
});

test('risk sets deduplicate horizons, respect full-span purging and never invent survival after censoring', () => {
  const data = planted(), p = data.paths[0];
  data.paths = [{ ...p, horizonMin: 1, observedMinutes: 1, plannedThrough: p.at + MIN, knownAt: p.at + MIN, cause: 'none', hitMinute: null },
    { ...p, observedMinutes: 2, censored: true, cause: 'none', hitMinute: null }];
  assert.equal(selectPathEpisodes(data, { from: p.at, through: p.at + MIN }).length, 1, 'longer planned span is purged');
  const chosen = selectPathEpisodes(data, { from: p.at, through: p.at + 3 * MIN });
  assert.equal(chosen.length, 1); assert.equal(chosen[0].horizonMin, 3);
  assert.deepEqual(riskRows(data, chosen).map((r) => r.minute), [1, 2]);
  const hit = { ...chosen[0], cause: 'ambiguous' as const, hitMinute: 1 };
  assert.deepEqual(riskRows(data, [hit]).map((r) => r.cause), ['ambiguous']);
  assert.throws(() => riskRows(data, chosen, 1), /limit/);
  assert.deepEqual(pathQueryValues(p, 9)['query:minute'], Math.log1p(9));
});

test('numeric encoding never reads hashes, raw timestamps, source labels or future feature groups', () => {
  const f = frame(start);
  const values = encodePathFrame(f);
  assert.ok(Object.keys(values).every((k) => /^(asset|status|age|value|missing):/.test(k)));
  assert.ok(!Object.keys(values).some((k) => /sha|knownAt|decisionAt|label|returnBps/i.test(k)));
  const missing = { ...f, groups: { micro: { ...f.groups.micro, values: { x: null, z: 0 } } } };
  assert.ok(Number.isNaN(encodePathFrame(missing)['value:micro:x']));
  assert.equal(encodePathFrame(missing)['missing:micro:x'], 1);
  assert.throws(() => encodePathFrame({ ...f, groups: { micro: { ...f.groups.micro, knownAt: start + MIN } } }), /noncausal/);
});

test('fold plans keep disjoint purged stages inside original training dates and reject unsafe limits', async () => {
  const data = planted(), folds = planRiskFolds(data, plan);
  for (const f of folds) {
    assert.ok(f.train.through < f.stopping.from && f.stopping.through < f.calibration.from && f.calibration.through < f.evaluation.from);
    assert.ok(f.evaluation.through <= FROZEN_TRAIN_BEFORE);
  }
  assert.throws(() => planRiskFolds(data, { ...plan, stepMs: MIN }), /plan/);
  await assert.rejects(trainJointPaths(data, { params: { nTrees: Infinity } }), /parameters/);
  await assert.rejects(trainJointPaths(data, { maxRiskRows: NaN }), /limits/);
  await assert.rejects(trainJointPaths({ ...data, finalFrom: Date.parse('2027-01-01') }), /frozen/);
});

async function bundle(parent: string, year = 2024) {
  const archive = path.join(parent, `archive-${year}`), name = 'binance-1m/BTC/1m.csv', file = path.join(archive, 'history', name);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const csv = 'ts,o,h,l,c,v\n' + Array.from({ length: 40 }, (_, i) => `${Date.UTC(year, 0, 2) + i * MIN},100,101,99,100,1\n`).join('');
  fs.writeFileSync(file, csv);
  fs.writeFileSync(path.join(archive, 'archive-validation.json'), JSON.stringify({ schema: 'atlas-archive-audit-v1', files: [{ path: name, ready: true, source: 'binance-1m', rows: 40, sha256: createHash('sha256').update(csv).digest('hex') }] }));
  const outDir = path.join(parent, `dataset-${year}`);
  await exportDecisionDataset({ archiveDir: archive, assets: ['BTC'], outDir, path: { horizonsMin: [1, 3] }, referencePeriodsMin: [] });
  return outDir;
}

test('dataset reader verifies bundles/joins and the fitting CLI publishes no model for insufficient history', async () => {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'joint-path-'));
  try {
    const dir = await bundle(parent), data = await loadJointPathDataset(dir, { maxHorizonMin: 3 });
    assert.equal(data.decisions.size, 40); assert.ok(data.paths.length > 0);
    const outDir = path.join(parent, 'study'), report = await exportJointPathStudy({ datasetDir: dir, outDir });
    assert.equal(report.status, 'blocked-insufficient-history-or-rows');
    assert.deepEqual(fs.readdirSync(outDir), ['report.json']);
    await assert.rejects(exportJointPathStudy({ datasetDir: dir, outDir }), /already exists/);
    await assert.rejects(exportJointPathStudy({ datasetDir: dir, outDir: path.join(dir, 'study') }), /outside/);
    fs.appendFileSync(path.join(dir, 'paths.jsonl'), '{}\n');
    await assert.rejects(loadJointPathDataset(dir), /hash/);
    await assert.rejects(exportJointPathStudy({ datasetDir: dir, outDir: path.join(parent, 'broken') }), /hash/);
    assert.ok(!fs.existsSync(path.join(parent, 'broken')));
  } finally { fs.rmSync(parent, { recursive: true, force: true }); }
});

test('final-period values are never encoded and forged final outcomes are refused even with updated hashes', async () => {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'joint-final-'));
  try {
    const development = await loadJointPathDataset(await bundle(parent, 2025));
    assert.equal(development.decisions.size, 0); assert.equal(development.paths.length, 0, 'the original 2025 development period is not reused for internal fitting');
    const dir = await bundle(parent, 2026), data = await loadJointPathDataset(dir);
    assert.equal(data.decisions.size, 0); assert.equal(data.paths.length, 0); assert.equal(data.counts.reserved, 40);
    const report = await trainJointPaths(data, { smokeTest: true }); assert.equal(report.folds.length, 0);
    const d = JSON.parse(fs.readFileSync(path.join(dir, 'decisions.jsonl'), 'utf8').trim().split('\n')[1]);
    const file = path.join(dir, 'paths.jsonl'); fs.appendFileSync(file, JSON.stringify({ entry: { decisionId: d.decisionId } }) + '\n');
    const manifestFile = path.join(dir, 'manifest.json'), m = JSON.parse(fs.readFileSync(manifestFile, 'utf8'));
    m.outputs.paths.sha256 = createHash('sha256').update(fs.readFileSync(file)).digest('hex'); m.outputs.paths.rows = 1;
    fs.writeFileSync(manifestFile, JSON.stringify(m));
    await assert.rejects(loadJointPathDataset(dir), /final path/);
  } finally { fs.rmSync(parent, { recursive: true, force: true }); }
});

test('interned decision values reconstruct the exact frame and cannot inherit unversioned future columns', async () => {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'joint-vocabulary-'));
  try {
    const dir = await bundle(parent), file = path.join(dir, 'decisions.jsonl');
    const lines = fs.readFileSync(file, 'utf8').trim().split('\n'), data = await loadJointPathDataset(dir);
    for (const line of lines.slice(1)) {
      const d = JSON.parse(line), expected = encodePathFrame(d.frame), actual = data.decisions.get(d.decisionId)!.values;
      for (const [key, value] of Object.entries(expected)) assert.ok(Object.is(actual[key], value), key);
    }
    const changed = JSON.parse(lines.at(-1)!); changed.frame.groups.micro.values.future_column = 999;
    lines[lines.length - 1] = JSON.stringify(changed); fs.writeFileSync(file, lines.join('\n') + '\n');
    const mf = path.join(dir, 'manifest.json'), m = JSON.parse(fs.readFileSync(mf, 'utf8'));
    m.outputs.decisions.sha256 = createHash('sha256').update(fs.readFileSync(file)).digest('hex'); fs.writeFileSync(mf, JSON.stringify(m));
    await assert.rejects(loadJointPathDataset(dir), /vocabulary/);
  } finally { fs.rmSync(parent, { recursive: true, force: true }); }
});
