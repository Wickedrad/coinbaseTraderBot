import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { rng } from '../research/stats';
import { ATLAS_FEATURE_SCHEMA, type AtlasFeatureFrame } from '../research/opportunity/features';
import { TANET_SCHEMA } from '../bot/ta/taNet';
import { buildContractObservation, digest, labelContract, type ContractObservation, type IndexEvidence, type TimelyMoveDefinition } from '../research/opportunity/contractDataset';
import { contractRows, fitContractModel, scoreContractModel, contractProbabilities, contractModelSupports, missingRequiredInputs, validateContractModel, type ContractExample, type ContractStudyPlan } from '../research/opportunity/contractLearner';
import { runContractStudy, contractBounds, holmRetained, type ContractStudy } from '../research/opportunity/contractStudy';
import { AtlasRegistry, createAtlasProduct } from '../research/opportunity/registry';
import { evaluatePaperPosition, type PaperPolicy, type PaperQuote } from '../research/opportunity/paper';
import { assembleContractDataset, exportContractStudy, exportPaperShadow, exportRecordingInputs, loadContractDataset, type AssemblySpec, type RecordedDecision } from '../research/opportunity/productCli';
import { FROZEN_FINAL_FROM, sha256File } from '../research/opportunity/jointPathData';
import { TapeWriter } from '../research/snnTape';
import { replayAtlasSnnTape } from '../research/opportunity/snnReplay';
import { SnnNetwork } from '../bot/snn/network';
import { DEFAULT_SNN, stageFlags } from '../bot/snn/params';
import { captureSnnState } from '../research/opportunity/snnState';
import type { ContractPathForecast } from '../research/opportunity/contractTiming';
import { compareSnnStudies, qualifySnnStudy } from '../research/opportunity/snnComparison';

const MIN = 60000, start = Date.UTC(2023, 0, 2), sha = 'a'.repeat(64);
const policy: PaperPolicy = { minimumMoveLowerBound: 0.8, minimumJointLowerBound: 0.7, minimumEntryEdge: 0.02, maximumQuoteAgeMs: 2000, maximumPosition: 10 };
const event: TimelyMoveDefinition = { id: 'fixture-turn', direction: 'up', kind: 'move', thresholdBps: 20, sustainSec: 3, sustainFraction: 0.8, priorWindowSec: 0, priorDriftBps: 0 };
function frame(at: number, x = 0, z = 0): AtlasFeatureFrame {
  return { schema: ATLAS_FEATURE_SCHEMA, taSchema: TANET_SCHEMA, engine: 'builtin', asset: 'BTC', decisionAt: at, session: 'asia', gapsSeen: 0,
    groups: { spot_1m: { source: 'fixture', sha256: sha, timeframe: '1m', status: 'ready', bars: 1, firstOpen: at - MIN, lastOpen: at - MIN,
      knownAt: at, publicationLagMs: 0, timing: 'fixture', values: { x, z } } } };
}
function example(at: number, move: boolean, pays: boolean, x = 0, z = 0): ContractExample {
  const index: IndexEvidence = { asset: 'BTC', reference: 'fixture-index', sourceSha256: sha, basis: 'synthetic-fixture',
    prints: Array.from({ length: 121 }, (_, s) => ({ ts: at + s * 1000, knownAt: at + s * 1000,
      value: s === 0 ? 100 : s >= 60 ? pays ? 100.08 : 99.98 : move && s >= 20 ? 100.3 : 100 })) };
  const observation = buildContractObservation(frame(at, x, z), { ticker: `FIXTURE-${at}`, asset: 'BTC', openTime: at - 780000, closeTime: at + 120000,
    termsKnownAt: at - 780000, terms: { kind: 'greater', strike: 100.05 }, settlementReference: index.reference }, event, index,
    { side: 'yes', executionBufferMs: 10000, termsSourceSha256: sha });
  const outcome = labelContract(observation, index, at + 130000, { yes: pays, knownAt: at + 120000 });
  assert.equal(outcome.category, Number(move) + 2 * Number(pays));
  const quote: PaperQuote = { ticker: observation.query.contract.ticker, side: 'yes', at, knownAt: at, bid: 0.39, ask: 0.4, bidSize: 10, askSize: 10,
    entryFee: 0.01, exitFee: 0.01, settlementFee: 0, slippage: 0.005, sourceSha256: sha };
  return { observation, outcome, quote };
}
const plan: ContractStudyPlan = {
  train: { from: start, through: start + 360 * 3 * MIN },
  stopping: { from: start + 361 * 3 * MIN, through: start + 421 * 3 * MIN },
  calibration: { from: start + 422 * 3 * MIN, through: start + 522 * 3 * MIN },
  selection: { from: start + 523 * 3 * MIN, through: start + 623 * 3 * MIN },
  audit: { from: start + 624 * 3 * MIN, through: start + 724 * 3 * MIN }, embargoMs: 3 * MIN,
};
let cachedExamples: ContractExample[];
function planted() {
  if (cachedExamples) return cachedExamples;
  const random = rng(71);
  cachedExamples = Array.from({ length: 725 }, (_, i) => {
    const x = random() * 2 - 1, z = random() * 2 - 1, p = 1 / (1 + Math.exp(-7 * x * z));
    return example(start + i * 3 * MIN, random() < p, random() < p, x, z);
  });
  return cachedExamples;
}
let models: { smooth: ReturnType<typeof fitContractModel>; baseline: ReturnType<typeof fitContractModel> };
function fitted() {
  if (models) return models;
  const examples = planted(), rows = { train: contractRows(examples, plan.train), stopping: contractRows(examples, plan.stopping), calibration: contractRows(examples, plan.calibration) };
  models = { smooth: fitContractModel(rows, plan, 'smooth', ['ta'], { epochs: 150, hidden: 12 }), baseline: fitContractModel(rows, plan, 'temporal-linear', [], { epochs: 50 }) };
  return models;
}

test('smooth joint contract heads learn an interaction and produce coherent dependent outcomes', () => {
  const { smooth, baseline } = fitted(), rows = contractRows(planted(), plan.selection);
  const mean = (m: typeof smooth) => { const scores = scoreContractModel(m, rows); return scores.reduce((s, r) => s + r.loss, 0) / scores.length; };
  assert.ok(mean(smooth) < mean(baseline) - 0.03, `${mean(smooth)} vs ${mean(baseline)}`);
  const a = contractProbabilities(smooth, { 'value:spot_1m:x': 0.8, 'value:spot_1m:z': 0.8 }), b = contractProbabilities(smooth, { 'value:spot_1m:x': -0.8, 'value:spot_1m:z': 0.8 });
  assert.ok(a.both > b.both + 0.1);
  for (const p of [a, b]) assert.ok(Math.abs(Object.values(p).reduce((s, v) => s + v, 0) - 1) < 1e-12);
  const c = contractProbabilities(smooth, { 'value:spot_1m:x': 0.800001, 'value:spot_1m:z': 0.8 });
  assert.ok(Math.abs(c.both - a.both) < 0.0001, 'continuous response rather than indicator votes');
  assert.ok(missingRequiredInputs(smooth, { 'value:spot_1m:z': 0.8 }).includes('value:spot_1m:x'), 'unseen missing TA cannot obtain confidence from its training mean');
  const copy = JSON.parse(JSON.stringify(smooth)); validateContractModel(copy); assert.deepEqual(contractProbabilities(copy, {}), contractProbabilities(smooth, {}));
  copy.heads.move.calibration.c += 1; assert.throws(() => validateContractModel(copy), /model\/ID/);
});

test('full-span purging, final withholding and training-only normalization prevent temporal leakage', () => {
  const rows = contractRows(planted(), plan.train);
  assert.ok(rows.every((r) => r.outcome.plannedThrough <= plan.train.through && r.outcome.knownAt <= plan.train.through));
  const crossing = structuredClone(planted()[0]); crossing.outcome.knownAt = plan.train.through + 1;
  assert.equal(contractRows([crossing], plan.train).length, 0);
  const final = example(FROZEN_FINAL_FROM, true, true);
  assert.throws(() => contractRows([...planted(), final], plan.train), /reserved-final/);
  const altered = structuredClone(planted());
  for (const row of altered) if (row.observation.query.asOf >= plan.audit.from) { row.outcome.category = 0; row.outcome.sidePays = false; row.outcome.timelyMove = false; }
  const rows2 = { train: contractRows(altered, plan.train), stopping: contractRows(altered, plan.stopping), calibration: contractRows(altered, plan.calibration) };
  assert.deepEqual(fitContractModel(rows2, plan, 'smooth', ['ta'], { epochs: 150, hidden: 12 }), fitted().smooth);
});

let study: ContractStudy;
function studied() { return study ??= runContractStudy(planted(), plan, policy, { epochs: 30, hidden: 6, trees: 12 }); }
test('relationship retention preserves insufficient evidence and never qualifies a short synthetic study', () => {
  const s = studied();
  assert.equal(s.status, 'research-fit'); assert.ok(s.blockers.some((b) => /Synthetic/.test(b)));
  assert.ok(s.retention.length > 0); assert.ok(s.retention.every((r) => r.decision === 'insufficient-evidence'));
  assert.deepEqual(s.selected!.included, []);
  assert.ok(s.retention.every((r) => r.fullParentModelId.length === 64 && r.ablatedModelId.length === 64));
  assert.deepEqual([...holmRetained([0.001, 0.02, 0.9])], [0, 1]);
  assert.equal(holmRetained([0.02]).size, 1);
  assert.equal(holmRetained([0.02], 0.05, 3).size, 0, 'a parent chosen among three families is not an independently fixed parent');
  const b = contractBounds(s.calibration!, s.selected!.support[0].key, 'pays', 0.8);
  assert.equal(b.supported, false); assert.deepEqual(b.bounds, { probability: 0.8, lower: 0, upper: 1 });
});

test('registry enforces publication, identity, coverage, calibration and content IDs', () => {
  const s = studied(), product = createAtlasProduct(s, { source: sha }, { dataset: sha }, plan.audit.through), registry = new AtlasRegistry();
  registry.register(product);
  const o = example(plan.audit.through + 3 * MIN, true, true).observation;
  const result = registry.query(product.id, o, { maximumCalibrationAgeMs: 86400000 });
  assert.equal(result.status, 'unqualified'); assert.equal(result.forecast!.calibrationRef, null); assert.equal(result.liveEntryAllowed, false);
  assert.equal(registry.query(product.id, o, { maximumCalibrationAgeMs: 1000 }).status, 'expired');
  const futurePublication = createAtlasProduct(s, { source: sha }, {}, o.query.asOf + 1), r2 = new AtlasRegistry(); r2.register(futurePublication);
  assert.equal(r2.query(futurePublication.id, o, { maximumCalibrationAgeMs: 86400000 }).forecast, null);
  assert.ok(r2.query(futurePublication.id, o, { maximumCalibrationAgeMs: 86400000, mode: 'historical-audit' }).forecast,
    'post-audit retrospective queries require an explicit mode and never establish forward publication');
  const evidence: IndexEvidence = { asset: 'BTC', reference: 'fixture-index', sourceSha256: sha, basis: 'synthetic-fixture',
    prints: [{ ts: o.query.asOf, knownAt: o.query.asOf, value: 100 }] };
  const differentDeadline = buildContractObservation(o.frame, o.query.contract, event, evidence,
    { side: 'yes', executionBufferMs: 0, termsSourceSha256: sha });
  assert.equal(registry.query(product.id, differentDeadline, { maximumCalibrationAgeMs: 86400000 }).status, 'unsupported',
    'a changed execution buffer changes the movement deadline, even for the same remaining contract time');
  const olderFrame = buildContractObservation(frame(o.query.asOf - 30000), o.query.contract, event, evidence,
    { side: 'yes', executionBufferMs: 10000, termsSourceSha256: sha, asOf: o.query.asOf });
  assert.equal(registry.query(product.id, olderFrame, { maximumCalibrationAgeMs: 86400000 }).status, 'unsupported',
    'a model fitted only on current frames cannot silently substitute a thirty-second-old frame');
  const tampered = structuredClone(product); tampered.study.selected!.heads.move.calibration.c += 1;
  assert.throws(() => registry.register(tampered), /content ID/);
  const wrong = structuredClone(o); wrong.query.contract.terms.strike = 90;
  assert.throws(() => registry.query(product.id, wrong, { maximumCalibrationAgeMs: 86400000 }), /observation/);
});

test('locked selected and baseline models cannot switch study policy or fitting dates inside an otherwise hashed artifact', () => {
  for (const kind of ['selected', 'baseline'] as const) {
    const s = structuredClone(studied()), { id: _modelId, ...core } = s[kind]!;
    const changed = { ...core, studyPolicyId: 'prospective-2026-11-09-v1' };
    s[kind] = { ...changed, id: digest(changed) };
    const { id: _studyId, ...studyCore } = s; s.id = digest(studyCore);
    assert.throws(() => createAtlasProduct(s, {}, {}), /partition registration/);
  }
  const s = structuredClone(studied()), { id: _modelId, ...core } = s.selected!;
  const changed = { ...core, trainedThrough: core.trainedThrough + MIN }; s.selected = { ...changed, id: digest(changed) };
  const { id: _studyId, ...studyCore } = s; s.id = digest(studyCore);
  assert.throws(() => createAtlasProduct(s, {}, {}), /fitting dates/);
});

function confident(o: ContractObservation, p = 0.95): ContractPathForecast {
  const b = { probability: p, lower: p - 0.02, upper: Math.min(1, p + 0.02) };
  return { kind: 'contract-path', id: 'synthetic-qualified-only-for-policy-test', modelId: 'fixture', asset: o.query.asset, asOf: o.query.asOf,
    featuresKnownAt: o.query.featuresKnownAt, byAt: o.query.effectBy, direction: o.query.direction, eventDefinitionId: o.event.id,
    contract: o.query.contract, side: o.query.side, settlementBasis: 'official-index-average', calibrationRef: 'fixture',
    moveBy: b, sidePays: b, timelyMoveAndSidePays: { probability: Math.max(0, 2 * p - 1), lower: Math.max(0, 2 * p - 1.02), upper: p } };
}
test('paper entry obeys exact timing, fees, liquidity and caller risk budgets', () => {
  const e = planted()[0], o = e.observation, q = e.quote!, f = confident(o);
  const evaluate = (forecast = f, quote = q, remainingRiskDollars = 1) => evaluatePaperPosition(o, forecast, quote, null, policy, { riskApprovedQuantity: 3, remainingRiskDollars });
  const entry = evaluate(); assert.equal(entry.action, 'enter'); assert.equal(entry.quantityChange, 2); assert.equal(entry.liveEntryAllowed, false);
  assert.equal(evaluate({ ...f, byAt: o.query.asOf + 60 * MIN }).action, 'abstain', 'hour signal cannot authorize this short contract');
  assert.equal(evaluate({ ...f, calibrationRef: null }).action, 'abstain');
  assert.equal(evaluate(f, { ...q, at: q.at - 5000 }).action, 'abstain');
  assert.equal(evaluate(f, { ...q, ask: 0.98, bid: 0.97 }, 10).action, 'wait');
  assert.equal(evaluate(f, { ...q, askSize: 1 }, 10).quantityChange, 1);
});
test('paper hold versus exit excludes sunk entry costs and handles partial reductions', () => {
  const e = planted()[0], o = e.observation, q = { ...e.quote!, bid: 0.9, ask: 0.91 }, f = confident(o, 0.7);
  const evaluate = (cost: number, bidSize = 10, limit = 10) => evaluatePaperPosition(o, f, { ...q, bidSize },
    { ticker: q.ticker, side: q.side, quantity: 5, averageEntryCost: cost }, policy, { riskApprovedQuantity: limit, remainingRiskDollars: 0 });
  assert.equal(evaluate(0.1).action, 'exit'); assert.deepEqual(evaluate(0.1), evaluate(0.99));
  assert.equal(evaluate(0.5, 2).action, 'reduce'); assert.equal(evaluate(0.5, 2).targetQuantity, 3);
  assert.equal(evaluate(0.5, 2, 3).reason, 'caller risk allowance requires reduction');
  const hold = evaluatePaperPosition(o, confident(o), e.quote!, { ticker: q.ticker, side: q.side, quantity: 1, averageEntryCost: 0.99 }, policy,
    { riskApprovedQuantity: 10, remainingRiskDollars: 10 });
  assert.equal(hold.action, 'hold'); assert.equal(hold.quantityChange, 0);
});

test('actual SNN tape adapter advances old inputs before new arrivals and freezes learning at the cutoff', (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-tape-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const tape = path.join(dir, 'fixture.tape'), w = new TapeWriter(tape), params = { ...DEFAULT_SNN, nE: 16, nI: 4, nL1: 8 };
  const a = [{ key: 'BTC-15m', asset: 'BTC', price: 100, mid: undefined, values: {} }], b = [{ ...a[0], price: 200 }];
  w.step(start, a); w.step(start + 5000, b); w.close();
  const states: ReturnType<typeof captureSnnState>[] = [];
  const report = replayAtlasSnnTape(tape, { variant: 'S5', sourceSha256: sha, inputLagMs: 0, maximumInputGapMs: 10000, everyMs: 1000, params, learningBefore: start + 3000, onState: (s) => states.push(s) });
  const net = new SnnNetwork({ ...params, flags: stageFlags('S5') });
  net.step(start, a); net.step(start + 2000, []); net.pauseLearning = true; net.step(start + 4000, []); net.step(start + 5000, b);
  const expected = captureSnnState(net, start + 5000, { ...states[1].provenance });
  assert.deepEqual(states[1].columns, expected.columns); assert.equal(report.learnedThrough, start + 2000); assert.ok(report.gaps > 0);
  const legacy = path.join(dir, 'legacy.tape'), l = new TapeWriter(legacy);
  l.step(start, a); l.settle('ungraded', undefined, start + 600); l.step(start + 1000, b); l.close();
  const delayed: ReturnType<typeof captureSnnState>[] = [];
  const guarded = replayAtlasSnnTape(legacy, { variant: 'S5', sourceSha256: sha, everyMs: 1000, params, onState: (s) => delayed.push(s) });
  assert.equal(guarded.inputLagMs, 1000); assert.deepEqual(delayed.map((s) => s.asOf), [start + 1000, start + 2000]);
  assert.equal(delayed[1].provenance.inputKnownAt, start + 2000, 'rounded tape calls cannot claim subsecond availability');
});

test('unobserved SNN intervals cannot grade pending calls on stale held or later prices', (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-tape-gap-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'gapped.tape'), w = new TapeWriter(file), states: ReturnType<typeof captureSnnState>[] = [];
  const input = (price: number) => [{ key: 'BTC-15m', asset: 'BTC', price, mid: undefined, values: {} }];
  w.step(start, input(100)); w.step(start + 1000, input(110)); w.step(start + 1801000, input(200)); w.close();
  const result = replayAtlasSnnTape(file, { variant: 'S6', sourceSha256: sha, inputLagMs: 0, everyMs: 1000,
    params: { ...DEFAULT_SNN, nE: 8, nI: 2, nL1: 4 }, onState: (s) => states.push(s) });
  assert.equal(result.gapResets, 1); assert.equal(result.maximumInputGapMs, 3000);
  assert.equal(states.at(-1)!.columns[0].values.readout_labelled, 0, 'missing horizon must not become a direction-learning example');
  assert.equal(states.at(-1)!.provenance.maximumInputGapMs, 3000);
});

test('native tapes may start before any asset input, without publishing an invented empty state', (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-tape-start-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'startup.tape'), w = new TapeWriter(file), states: ReturnType<typeof captureSnnState>[] = [];
  w.step(start, []); w.score(start, [], []);
  w.step(start + 1000, [{ key: 'BTC-15m', asset: 'BTC', price: 100, mid: undefined, values: {} }]); w.close();
  const r = replayAtlasSnnTape(file, { variant: 'S5', sourceSha256: sha, everyMs: 1000,
    params: { ...DEFAULT_SNN, nE: 8, nI: 2, nL1: 4 }, onState: (s) => states.push(s) });
  assert.equal(r.unavailableSnapshots, 1); assert.equal(states.length, 1);
  assert.equal(states[0].asOf, start + 2000); assert.equal(states[0].columns[0].asset, 'BTC');
});

test('assembly, persisted study, registry query and shadow logging run end to end with checked receipts', async (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-product-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const first = planted()[0], at = first.observation.query.asOf;
  const prints = Array.from({ length: 121 }, (_, s) => ({ ts: at + s * 1000, knownAt: at + s * 1000, value: s < 20 ? 100 : 100.3 }));
  const indexFile = path.join(dir, 'index.jsonl'), decisionsFile = path.join(dir, 'decisions.jsonl');
  fs.writeFileSync(indexFile, prints.map((p) => JSON.stringify(p)).join('\n') + '\n');
  const d: RecordedDecision = { frame: first.observation.frame, contract: first.observation.query.contract, event, side: 'yes', executionBufferMs: 10000, quote: first.quote };
  fs.writeFileSync(decisionsFile, JSON.stringify(d) + '\n');
  const spec: AssemblySpec = { schema: 'opportunity-recording-spec-v1', knownBy: at + 500000,
    indices: [{ file: 'index.jsonl', sha256: await sha256File(indexFile), asset: 'BTC', reference: 'fixture-index', basis: 'synthetic-fixture' }],
    decisions: { file: 'decisions.jsonl', sha256: await sha256File(decisionsFile) } };
  const specFile = path.join(dir, 'spec.json'); fs.writeFileSync(specFile, JSON.stringify(spec));
  const dataset = path.join(dir, 'dataset'), mf = await assembleContractDataset(specFile, dataset);
  assert.equal(mf.counts.complete, 1); const loaded = await loadContractDataset(dataset);
  assert.equal(loaded.examples[0].outcome.knownAt, at + 120000, 'label arrival comes from the required prints, not the later processing time');
  const planFile = path.join(dir, 'plan.json'), policyFile = path.join(dir, 'policy.json');
  fs.writeFileSync(planFile, JSON.stringify(plan)); fs.writeFileSync(policyFile, JSON.stringify(policy));
  const output = path.join(dir, 'study'), report = await exportContractStudy(dataset, planFile, policyFile, output);
  assert.equal(report.status, 'blocked-insufficient-data');
  const requestsFile = path.join(dir, 'requests.jsonl'); fs.writeFileSync(requestsFile, JSON.stringify({ observation: loaded.examples[0].observation, quote: first.quote,
    position: null, allowance: { riskApprovedQuantity: 1, remainingRiskDollars: 1 } }) + '\n');
  await assert.rejects(exportPaperShadow(path.join(output, 'product.json'), requestsFile, policyFile, path.join(dir, 'fake-forward'), 86400000), /forward-paper capture/);
  assert.ok(!fs.existsSync(path.join(dir, 'fake-forward')), 'historical requests cannot publish a forward paper ledger');
  const shadow = await exportPaperShadow(path.join(output, 'product.json'), requestsFile, policyFile, path.join(dir, 'shadow'), 86400000, 'historical-audit');
  assert.equal(shadow.requests, 1); assert.equal(shadow.actions.abstain, 1);
  await assert.rejects(() => assembleContractDataset(specFile, dataset), /new path/);
  fs.appendFileSync(indexFile, '{}\n'); await assert.rejects(() => assembleContractDataset(specFile, path.join(dir, 'corrupt')), /hash mismatch/);
  assert.equal(fs.existsSync(path.join(dir, 'corrupt')), false);
});

test('streamed assembly isolates predeclared windows and withholds every final-period outcome', async (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-final-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const reserved = example(FROZEN_FINAL_FROM + 60000, true, true).observation;
  const prints = Array.from({ length: 121 }, (_, sec) => ({ ts: reserved.query.asOf + sec * 1000, knownAt: reserved.query.asOf + sec * 1000, value: sec ? 999 : 100 }));
  const old = Array.from({ length: 1000 }, (_, i) => ({ ts: start + i * 1000, knownAt: start + i * 1000, value: 10 }));
  const indexFile = path.join(dir, 'index.jsonl'), decisionFile = path.join(dir, 'decisions.jsonl');
  fs.writeFileSync(indexFile, [...old, ...prints].map((p) => JSON.stringify(p)).join('\n') + '\n');
  fs.writeFileSync(decisionFile, JSON.stringify({ frame: reserved.frame, contract: reserved.query.contract, event, side: 'yes', executionBufferMs: 10000 }) + '\n');
  const spec: AssemblySpec = { schema: 'opportunity-recording-spec-v1', knownBy: prints.at(-1)!.ts,
    indices: [{ file: 'index.jsonl', sha256: await sha256File(indexFile), asset: 'BTC', reference: 'fixture-index', basis: 'synthetic-fixture' }],
    decisions: { file: 'decisions.jsonl', sha256: await sha256File(decisionFile) } };
  const specFile = path.join(dir, 'spec.json'); fs.writeFileSync(specFile, JSON.stringify(spec));
  const report = await assembleContractDataset(specFile, path.join(dir, 'dataset'));
  assert.equal(report.counts.withheld, 1); assert.equal(report.counts.complete, 0);
  const d = await loadContractDataset(path.join(dir, 'dataset'));
  assert.equal(d.examples[0].outcome.category, null); assert.equal(d.examples[0].outcome.settlementAverage, null);
  assert.equal(d.examples[0].observation.index.value, 100, 'future 999 prints cannot become current features');
});

test('native recording import retains arrival latency, both sides, exact books and complete capped labels', async (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-recordings-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const recordingDir = path.join(dir, 'recordings'); fs.mkdirSync(recordingDir);
  const entries: object[] = [{ t: start - 60000, k: 'market', ticker: 'OBSERVED-FIXTURE', asset: 'BTC', series: 'fixture', kind: 'greater',
    openTime: start - 780000, closeTime: start + 120000, strike: 100.05 }];
  entries.unshift({ t: start - 60000, k: 'market', ticker: 'KXBTC-23JAN0201-B115', asset: 'BTC', series: 'fixture', kind: 'greater',
    openTime: start - 780000, closeTime: start + 120000, strike: 110, cap: 120 });
  for (let sec = -60; sec <= 130; sec++) {
    const at = start + sec * 1000 + 200;
    entries.push({ t: at, k: 'index', asset: 'BTC', value: sec >= 20 ? 100.3 : 100, ts: at - 200, src: 'kalshi' });
    if (sec === 0) entries.push({ t: at, k: 'candles', asset: 'BTC', tf: '1m', rows: Array.from({ length: 16 }, (_, i) =>
      [(start - (16 - i) * MIN) / 1000, 99, 101, 100, 100, 1, 0.4]) });
    if (sec === 0) entries.push({ t: at, ts: at - 100, k: 'perp', asset: 'BTC', mark: 1, contractSize: 0.01, fundingRate: 0, openInterest: 123 },
      { t: at, ts: at - 100, k: 'dominance', btcd: 60, usdtd: 6, covered: 0.8 });
    if (sec === 1) entries.push({ t: at, k: 'delta', ticker: 'OBSERVED-FIXTURE', side: 'yes', price: 0.4, delta: -1 },
      { t: at, ts: at, k: 'perp', asset: 'BTC', mark: 1, contractSize: 0.01, fundingRate: 0, openInterest: 124 });
    else entries.push({ t: at, k: 'book', ticker: 'OBSERVED-FIXTURE', bids: [{ price: 0.4, size: 5 }], asks: [{ price: 0.5, size: 6 }] });
    if (sec === 130) entries.push({ t: at, k: 'result', ticker: 'OBSERVED-FIXTURE', result: 'yes' });
  }
  fs.writeFileSync(path.join(recordingDir, 'md-2023-01-02.jsonl'), entries.map((e) => JSON.stringify(e)).join('\n') + '\n');
  const config = path.join(dir, 'config.json'); fs.writeFileSync(config, JSON.stringify({ assets: ['BTC'], events: [event], everyMs: 60000,
    executionBufferMs: 10000, maximumDecisions: 2, costs: { entryFee: 0.01, exitFee: 0.01, settlementFee: 0, slippage: 0 } }));
  const out = path.join(dir, 'inputs'), report = await exportRecordingInputs(recordingDir, config, out);
  assert.equal(report.counts.decisions, 2); assert.equal(report.stoppedEarly, true);
  assert.equal(report.counts.rangeKindCanonicalized, 1);
  const manifest = await assembleContractDataset(path.join(out, 'spec.json'), path.join(dir, 'dataset'));
  assert.equal(manifest.counts.complete, 2, 'row cap must not truncate selected future labels');
  const ds = await loadContractDataset(path.join(dir, 'dataset')), [yes, no] = ds.examples;
  assert.equal(yes.observation.query.asOf, start + 200); assert.equal(yes.observation.frame.decisionAt, start + 200);
  assert.equal(yes.observation.frame.groups.spot_1m.knownAt, start + 200);
  assert.equal(yes.observation.anchor!.atrBps, 200, 'native second timestamps and low/high/open order must reach the ATR anchor');
  assert.equal(yes.observation.frame.groups.micro_perp.values.open_interest_contracts, 123);
  assert.equal(yes.observation.frame.groups.micro_perp.values.mark_per_coin, 100);
  assert.equal(yes.observation.frame.groups.micro_perp.values.funding_rate, 0);
  assert.equal(yes.observation.frame.groups.observed_dominance.values.btcd, 60);
  assert.equal(yes.quote!.ask, 0.5); assert.equal(no.quote!.ask, 0.6);
  assert.equal(yes.outcome.sidePays, true); assert.equal(no.outcome.sidePays, false); assert.equal(yes.outcome.officialResultConfirmed, true);
  const sampledConfig = path.join(dir, 'sampled-config.json');
  fs.writeFileSync(sampledConfig, JSON.stringify({ ...JSON.parse(fs.readFileSync(config, 'utf8')), maximumDecisions: 4, sampleEveryMs: 3600000, maximumContractsPerAsset: 1 }));
  const sampled = await exportRecordingInputs(recordingDir, sampledConfig, path.join(dir, 'sampled-inputs'));
  assert.equal(sampled.counts.decisions, 2, 'predeclared sampling cadence and geometry limit govern all later observations');
  assert.equal(sampled.stoppedEarly, false);
  const rangesConfig = path.join(dir, 'ranges-config.json');
  fs.writeFileSync(rangesConfig, JSON.stringify({ ...JSON.parse(fs.readFileSync(config, 'utf8')), maximumDecisions: 4 }));
  await exportRecordingInputs(recordingDir, rangesConfig, path.join(dir, 'ranges-inputs'));
  await assembleContractDataset(path.join(dir, 'ranges-inputs/spec.json'), path.join(dir, 'ranges-dataset'));
  const ranges = (await loadContractDataset(path.join(dir, 'ranges-dataset'))).examples.filter((e) => e.observation.query.contract.ticker.endsWith('-B115'));
  assert.equal(ranges.length, 2); assert.equal(ranges[0].observation.query.contract.terms.kind, 'between');
  assert.equal(ranges[0].observation.query.contract.terms.cap, 120); assert.equal(ranges[0].outcome.sidePays, false);
  const invalidatedConfig = path.join(dir, 'invalidated-config.json');
  fs.writeFileSync(invalidatedConfig, JSON.stringify({ ...JSON.parse(fs.readFileSync(config, 'utf8')), maximumDecisions: 4,
    everyMs: 1000, sampleEveryMs: 1000, maximumContractsPerAsset: 1 }));
  await exportRecordingInputs(recordingDir, invalidatedConfig, path.join(dir, 'invalidated-inputs'));
  const invalidated = fs.readFileSync(path.join(dir, 'invalidated-inputs/decisions.jsonl'), 'utf8').trim().split('\n').map((s) => JSON.parse(s));
  assert.ok(invalidated[0].quote); assert.equal(invalidated[2].asOf, start + 1200);
  assert.equal(invalidated[2].quote, undefined, 'an observed delta invalidates economic snapshot evidence until a new full snapshot');
  const snapshotConfig = path.join(dir, 'snapshot-config.json');
  fs.writeFileSync(snapshotConfig, JSON.stringify({ ...JSON.parse(fs.readFileSync(config, 'utf8')), maximumDecisions: 1000,
    everyMs: 1000, snapshotDecisionsOnly: true }));
  const only = path.join(dir, 'snapshot-inputs');
  const onlyReport = await exportRecordingInputs(recordingDir, snapshotConfig, only);
  const snapshotRows = fs.readFileSync(path.join(only, 'snapshots.jsonl'), 'utf8').trim().split('\n').map((s) => JSON.parse(s));
  const snapshotDecisions = fs.readFileSync(path.join(only, 'decisions.jsonl'), 'utf8').trim().split('\n').map((s) => JSON.parse(s));
  assert.equal(onlyReport.sampling.snapshotDecisionsOnly, true);
  assert.ok(snapshotRows.length > 2); assert.ok(snapshotDecisions.every((d) => d.quote && d.quote.knownAt === d.asOf));
  assert.ok(snapshotDecisions.every((d) => d.contract.ticker === 'OBSERVED-FIXTURE'));
  assert.equal(fs.readFileSync(path.join(only, 'results.jsonl'), 'utf8'), '', 'snapshot research does not read settlement results');
});

test('S5 and S6 are compared on identical contract observations and short evidence cannot qualify either', (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-variants-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const tape = path.join(dir, 'fixture.tape'), writer = new TapeWriter(tape);
  for (const e of planted()) writer.step(e.observation.query.asOf, [{ key: 'BTC-15m', asset: 'BTC', price: 100, mid: undefined, values: {} }]);
  writer.close();
  const data: Record<string, ContractExample[]> = {}, studies: Record<string, ContractStudy> = {};
  for (const variant of ['S5', 'S6'] as const) {
    const states = new Map<number, ReturnType<typeof captureSnnState>>();
    replayAtlasSnnTape(tape, { variant, sourceSha256: sha, inputLagMs: 0, everyMs: 60000, learningBefore: plan.train.through,
      params: { ...DEFAULT_SNN, nE: 8, nI: 2, nL1: 4 }, onState: (s) => states.set(s.asOf, s) });
    data[variant] = planted().map((r) => {
      const { id, ...o } = r.observation, core = { ...o, snn: states.get(o.query.asOf)! };
      const observation = { ...core, id: digest(core) };
      return { ...r, observation, outcome: { ...r.outcome, observationId: observation.id } };
    });
    studies[variant] = runContractStudy(data[variant], plan, policy, { epochs: 5, hidden: 3, trees: 2 });
  }
  const comparison = compareSnnStudies(studies.S5, data.S5, studies.S6, data.S6);
  assert.ok(comparison.rows > 0); assert.equal(comparison.recommended, 'none');
  assert.equal(comparison.liveEntryAllowed, false);
  const parent = studies.S5.candidates.find((c) => c.model.included.includes('snn'))!.model;
  const original = data.S5.find((e) => contractModelSupports(parent, e.observation))!.observation;
  const replaced = structuredClone(original);
  replaced.snn!.provenance.checkpointSha256 = 'f'.repeat(64);
  const { id: _id, ...core } = replaced; replaced.id = digest(core);
  assert.equal(contractModelSupports(parent, replaced), false, 'matching parameters cannot substitute a different starting SNN checkpoint');
  assert.throws(() => qualifySnnStudy(studies.S5, comparison), /does not qualify/);
  const changed = structuredClone(data.S6); changed.at(-1)!.outcome.category = 0;
  assert.throws(() => compareSnnStudies(studies.S5, data.S5, studies.S6, changed), /matching datasets/);
});
