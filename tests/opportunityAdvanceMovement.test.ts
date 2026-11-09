import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { ATLAS_FEATURE_SCHEMA, type AtlasFeatureFrame } from '../research/opportunity/features';
import { TANET_SCHEMA } from '../bot/ta/taNet';
import { buildContractObservation, digest, labelContract, labelTimelyMovement, type ContractObservation, type IndexEvidence } from '../research/opportunity/contractDataset';
import { encodeAdvanceMovement, fitAdvanceModel, movementObservationKey, movementRows, runAdvanceStudy, createAdvanceProduct, validateAdvanceProduct,
  queryAdvanceProduct, compareAdvanceSnn, type MovementExample } from '../research/opportunity/movementStudy';
import { evaluateProfitExit, profitAtSideBid, profitClock, profitExitBy, profitTargetPrice, type ProfitExitRequest, type ProfitPolicy } from '../research/opportunity/profitExit';
import { assembleMovementDataset, exportAdvanceStudy, exportMovementShadow, loadMovementDataset, movementLeadAfterPublication } from '../research/opportunity/movementCli';
import { writeProductDemoInputs } from '../research/opportunity/demo';
import { FROZEN_FINAL_FROM } from '../research/opportunity/jointPathData';
import { binaryResponseProbability, type ContractStudyPlan } from '../research/opportunity/contractLearner';
import { rng } from '../research/stats';
import { TapeWriter } from '../research/snnTape';
import { replayAtlasSnnTape } from '../research/opportunity/snnReplay';
import { DEFAULT_SNN } from '../bot/snn/params';
import type { AtlasSnnState } from '../research/opportunity/snnState';
import { pairedContractEvidence, pairedPredictiveEvidence } from '../research/opportunity/contractStudy';
import type { ContractScore } from '../research/opportunity/contractLearner';

const sha = 'a'.repeat(64), MIN = 60000, start = Date.UTC(2023, 0, 2, 15);
const policy = JSON.parse(fs.readFileSync('research/opportunity/examples/profit-policy.json', 'utf8')) as ProfitPolicy;
function observation(at: number, moveAt: number | null = 10, x = 0, z = 0, side: 'yes' | 'no' = 'yes', strike = 100.05) {
  const frame: AtlasFeatureFrame = { schema: ATLAS_FEATURE_SCHEMA, taSchema: TANET_SCHEMA, engine: 'builtin', asset: 'BTC', decisionAt: at,
    session: 'new_york', gapsSeen: 0, groups: { spot_1m: { source: 'synthetic-fixture', sha256: sha, timeframe: '1m', status: 'ready', bars: 1,
      firstOpen: at - MIN, lastOpen: at - MIN, knownAt: at, publicationLagMs: 0, timing: 'fixture', values: { x, z } } } };
  const index: IndexEvidence = { asset: 'BTC', reference: 'fixture-index', sourceSha256: sha, basis: 'synthetic-fixture',
    prints: Array.from({ length: 31 }, (_, s) => ({ ts: at + s * 1000, knownAt: at + s * 1000, value: moveAt !== null && s >= moveAt ? 100.3 : 100 })) };
  const o = buildContractObservation(frame, { ticker: `FIXTURE-${at}-${strike}`, asset: 'BTC', openTime: at - 780000, closeTime: at + 120000,
    termsKnownAt: at - 780000, terms: { kind: 'greater', strike }, settlementReference: index.reference },
  { id: 'advance-fixture', kind: 'move', direction: 'up', thresholdBps: 20, sustainSec: 3, sustainFraction: 0.8, priorWindowSec: 0 }, index,
  { side, executionBufferMs: 90000, termsSourceSha256: sha });
  return { o, index, byAt: at + 30000 };
}
function example(at: number, move: boolean, x = 0, z = 0): MovementExample {
  const { o, index, byAt } = observation(at, move ? 10 : null, x, z);
  return { observation: o, byAt, outcome: labelTimelyMovement(o, index, at + 40000, byAt, policy.minimumLeadMs) };
}
const plan: ContractStudyPlan = { train: { from: start, through: start + 360 * 3 * MIN }, stopping: { from: start + 361 * 3 * MIN, through: start + 421 * 3 * MIN },
  calibration: { from: start + 422 * 3 * MIN, through: start + 522 * 3 * MIN }, selection: { from: start + 523 * 3 * MIN, through: start + 623 * 3 * MIN },
  audit: { from: start + 624 * 3 * MIN, through: start + 724 * 3 * MIN }, embargoMs: 3 * MIN };
let plantedCache: MovementExample[];
function planted() {
  const random = rng(71);
  return plantedCache ??= Array.from({ length: 725 }, (_, i) => { const x = random() * 2 - 1, z = random() * 2 - 1;
    return example(start + i * 3 * MIN, random() < 1 / (1 + Math.exp(-7 * x * z)), x, z); });
}
let studyCache: ReturnType<typeof runAdvanceStudy>;
function studied() { return studyCache ??= runAdvanceStudy(planted(), plan, policy, { epochs: 60, hidden: 8, trees: 12 }); }

test('advance movement completes before settlement without any settlement-window prints or reported result', () => {
  const { o, index, byAt } = observation(start);
  const movement = labelTimelyMovement(o, index, start + 40000, byAt, 5000);
  assert.equal(movement.status, 'complete'); assert.equal(movement.advanceMove, true);
  assert.equal(movement.firstMoveAt, start + 10000); assert.equal(movement.leadMs, 10000); assert.equal(movement.knownAt, byAt);
  assert.equal(labelContract(o, index, start + 130000).status, 'missing-index');
  assert.equal(labelTimelyMovement(o, index, byAt - 1, byAt, 5000).status, 'pending');
  const late = observation(start, 3);
  const y = labelTimelyMovement(late.o, late.index, start + 40000, byAt, 5000);
  assert.equal(y.timelyMove, true); assert.equal(y.advanceMove, false, 'already-imminent moves do not earn sufficient advance credit');
});
test('movement gaps stay unavailable and YES/NO/strike changes cannot change the physical forecast', () => {
  const a = observation(start), b = observation(start, 10, 0, 0, 'no', 200);
  assert.deepEqual(encodeAdvanceMovement(a.o, a.byAt, policy), encodeAdvanceMovement(b.o, b.byAt, policy));
  assert.equal(movementObservationKey(a.o, a.byAt), movementObservationKey(b.o, b.byAt));
  assert.ok(Object.keys(encodeAdvanceMovement(a.o, a.byAt, policy)).every((k) => !k.startsWith('contract:')));
  const gap = { ...a.index, prints: a.index.prints.filter((p) => p.ts < start + 12000 || p.ts > start + 19000) };
  assert.equal(labelTimelyMovement(a.o, gap, start + 40000, a.byAt, 5000).status, 'missing-index');
  assert.throws(() => movementRows([example(start, true), { ...example(start, true), observation: b.o, outcome: { ...example(start, true).outcome, observationId: b.o.id } }], plan.train, policy), /duplicate/);
});
test('independent movement heads learn continuous interactions with purged fitting and no payout or quote gate', () => {
  const data = planted(), rows = { train: movementRows(data, plan.train, policy), stopping: movementRows(data, plan.stopping, policy), calibration: movementRows(data, plan.calibration, policy) };
  const model = fitAdvanceModel(rows, plan, policy, 'smooth', ['ta'], { epochs: 150, hidden: 12 });
  const p = (x: number, z: number) => {
    const e = observation(plan.audit.through + 3 * MIN, null, x, z), v = encodeAdvanceMovement(e.o, e.byAt, policy);
    return v;
  };
  const score = (x: number, z: number) => { const v = p(x, z); return binaryResponseProbability(model.head, model.featureNames.map((n) => v[n] ?? NaN)); };
  assert.ok(score(0.8, 0.8) > score(-0.8, 0.8) + 0.1);
  assert.ok(Math.abs(score(0.800001, 0.8) - score(0.8, 0.8)) < 0.0001);
  const s = studied(); assert.equal(s.objective, 'advance-price-movement'); assert.equal(s.status, 'research-fit');
  assert.ok(s.blockers.every((b) => !/settlement|quote|fee-net|pays/.test(b)));
  assert.deepEqual(s.selected!.included, []); assert.ok(s.retention.every((r) => r.decision === 'insufficient-evidence'));
  const crossing = structuredClone(data[0]); crossing.outcome.knownAt = plan.train.through + 1;
  assert.equal(movementRows([crossing], plan.train, policy).length, 0);
  assert.throws(() => movementRows([...data, example(FROZEN_FINAL_FROM, true)], plan.train, policy), /reserved-final/);
});
test('P/L urgency cannot change movement probabilities, and artifact publication/identity remain enforced', () => {
  const product = createAdvanceProduct(studied(), { source: sha }, { data: sha }, plan.audit.through), e = observation(plan.audit.through + 3 * MIN);
  const options = { maximumCalibrationAgeMs: 86400000, minimumMoveLowerBound: 0.8 };
  const q = queryAdvanceProduct(product, e.o, policy, options);
  assert.equal(q.status, 'unqualified'); assert.equal(q.forecast!.kind, 'movement'); assert.equal(q.forecast!.calibrationRef, null);
  assert.equal('sidePays' in q.forecast!, false);
  const urgency = structuredClone(policy); urgency.pacer.hourlyUsd = 100; urgency.finalProfitFraction = 0.2;
  assert.deepEqual(queryAdvanceProduct(product, e.o, urgency, options), q);
  const future = createAdvanceProduct(studied(), { source: sha }, { data: sha }, e.o.query.asOf + 1);
  assert.equal(queryAdvanceProduct(future, e.o, policy, options).forecast, null);
  const tampered = structuredClone(product); tampered.study.selected!.head.calibration.c += 1;
  assert.throws(() => validateAdvanceProduct(tampered), /ID/);
});
test('movement S5/S6 comparison aligns the same price-path cohort without fee or payout outcomes', (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-advance-snn-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'inputs.tape'), writer = new TapeWriter(file);
  for (const e of planted()) writer.step(e.observation.query.asOf, [{ key: 'BTC-15m', asset: 'BTC', price: 100, mid: undefined, values: {} }]); writer.close();
  const datasets: MovementExample[][] = [], studies = [];
  for (const variant of ['S5', 'S6'] as const) {
    const states = new Map<number, AtlasSnnState>();
    replayAtlasSnnTape(file, { variant, sourceSha256: sha, inputLagMs: 0, maximumInputPriceAgeMs: 3000, everyMs: 1000,
      params: { ...DEFAULT_SNN, nE: 8, nI: 2, nL1: 4 }, onState: (s) => states.set(s.asOf, s) });
    const data = planted().map((e) => {
      const { id, ...core } = e.observation, changed = { ...core, snn: states.get(core.query.asOf)! }, observation = { ...changed, id: digest(changed) };
      return { ...e, observation, outcome: { ...e.outcome, observationId: observation.id } };
    }); datasets.push(data); studies.push(runAdvanceStudy(data, plan, policy, { epochs: 10, hidden: 3, trees: 4 }));
  }
  const result = compareAdvanceSnn(studies[0], datasets[0], studies[1], datasets[1], policy);
  assert.equal(result.recommended, 'none'); assert.ok(result.rows > 0); assert.equal(result.tests.length, 3);
  assert.ok(result.tests.every((r) => !r.accepted && !('economic' in r)));
});

const fees = { knownAt: start, effectiveFrom: start, validUntil: null, sourceSha256: sha, verified: true,
  schedule: { takerMultiplier: 1, makerMultiplier: 0, takerRate: 0.07, makerRate: 0.0175, balancePrecision: 0.01 } };
function exitRequest(at = start, side: 'yes' | 'no' = 'yes', bid = 0.65, size = 40): ProfitExitRequest {
  return { asOf: at, contract: { ticker: 'FIXTURE-EXIT', asset: 'BTC', openTime: start, closeTime: start + 15 * MIN,
    termsKnownAt: start, terms: { kind: 'greater', strike: 100 }, settlementReference: 'fixture-index' },
    position: { ticker: 'FIXTURE-EXIT', side, quantity: 40, averageEntryCost: 0.5175 }, fees, credits: [], riskApprovedQuantity: 40,
    quote: { ticker: 'FIXTURE-EXIT', side, at, knownAt: at, bid, bidSize: size, tickSize: 0.01, slippagePerContract: 0, sourceSha256: sha } };
}
test('profit targets use whole-position P/L including the actual entry basis and nonlinear rounded exit fee', () => {
  // Bought 40 at $0.50 plus $0.70 entry fee. Selling at $0.65 receives $26 minus $0.64: $4.66 net.
  const r = exitRequest(), p = evaluateProfitExit(r, policy);
  assert.equal(p.clock.neededUsd, 4.5); assert.equal(p.targetSideBid, 0.65); assert.ok(Math.abs(p.positionNetAtTouch! - 4.66) < 1e-9);
  assert.equal(p.action, 'exit'); assert.equal(p.quantityToSell, 40);
  assert.ok(profitAtSideBid(r.position, 0.64, fees.schedule) < 4.5);
  const no = evaluateProfitExit(exitRequest(start, 'no'), policy); assert.ok(Math.abs(no.positionNetAtTouch! - 4.66) < 1e-9); assert.equal(no.action, 'exit');
  assert.equal(profitTargetPrice({ ...r.position, quantity: 1 }, 4.5, 0.01, fees.schedule), null, 'unreachable cash goal never requests a larger position');
});
test('thin-book profit recommendations credit no hypothetical fills and do not enlarge risk', () => {
  const r = exitRequest(start, 'yes', 0.65, 10), result = evaluateProfitExit(r, policy);
  assert.equal(result.action, 'reduce'); assert.equal(result.quantityToSell, 10); assert.ok(Math.abs(result.executableNetNow! - 1.165) < 1e-9);
  assert.equal(result.clock.status.realized24hUsd, 0);
  const capped = evaluateProfitExit({ ...r, riskApprovedQuantity: 0 }, policy); assert.equal(capped.quantityToSell, 10); assert.match(capped.reason, /risk/);
  const smaller = evaluateProfitExit({ ...exitRequest(), riskApprovedQuantity: 10 }, policy);
  assert.equal(smaller.availableDepthQuantity, 40); assert.equal(smaller.quantityToSell, 30);
  assert.ok(Math.abs(smaller.netForRecommendedSale! - 3.495) < 1e-9, 'fee and reported P/L use the recommended reduction quantity');
});
test('the existing New York hourly slices respond to time and fee-net realized P/L without stacking a huge deficit', () => {
  const late = start + 11 * 3600000 + 45 * MIN;
  const credits = [{ id: 'closed-fill', at: late - MIN, knownAt: late - MIN, netUsdDelta: 3 }];
  const c = profitClock(policy, credits, late);
  assert.equal(c.status.hourIndex, 12); assert.equal(c.status.remainingGoalUsd, 105); assert.equal(c.neededUsd, 1.5);
  assert.equal(profitClock(policy, [], late).neededUsd, 4.5);
  assert.throws(() => profitClock(policy, [{ ...credits[0], knownAt: late + 1 }], late), /future/);
  const r = exitRequest(late); r.contract.openTime = late; r.contract.closeTime = late + 15 * MIN; r.credits = credits;
  assert.equal(evaluateProfitExit(r, policy).targetSideBid, 0.58);
});
test('only profitable positions get the final-window settlement exception; risk and loss exits remain independent of forecasts', () => {
  assert.equal(profitExitBy(exitRequest().contract, policy), start + 870000);
  const r = exitRequest(start + 14 * MIN);
  assert.equal(evaluateProfitExit(r, policy).action, 'ride-profitable-final-window');
  assert.equal(evaluateProfitExit(exitRequest(start + 14 * MIN, 'yes', 0.50), policy).action, 'manage', 'ordinary stops/exits continue before the sale deadline');
  const loss = evaluateProfitExit(exitRequest(start + 14.5 * MIN, 'yes', 0.50), policy);
  assert.equal(evaluateProfitExit(exitRequest(start + 15 * MIN - 500, 'yes', 0.50), policy).action, 'exit');
  assert.equal(loss.action, 'exit'); assert.match(loss.reason, /without a net profit/);
  assert.equal(evaluateProfitExit({ ...r, riskApprovedQuantity: 20 }, policy).action, 'reduce');
  assert.equal(evaluateProfitExit({ ...r, fees: { ...fees, verified: false } }, policy).action, 'manage');
  const listed = exitRequest(start + 54 * MIN); listed.contract.openTime = start - 86400000; listed.contract.closeTime = start + 3600000;
  assert.equal(evaluateProfitExit(listed, policy).action, 'ride-profitable-final-window', 'the capped final share begins six minutes before close');
  listed.asOf -= 1000; listed.quote = { ...listed.quote!, at: listed.asOf, knownAt: listed.asOf };
  assert.notEqual(evaluateProfitExit(listed, policy).action, 'ride-profitable-final-window', 'listing duration does not extend the exception');
  assert.equal(evaluateProfitExit({ ...r, quote: { ...r.quote!, knownAt: r.asOf + 1 } }, policy).action, 'unavailable');
});
test('existing higher-target quota floors are preserved without using settlement value', () => {
  const p = structuredClone(policy); p.pacer.floorTicks = 0;
  const r = { ...exitRequest(), higherTarget: 'existing trailing target' }, armed = evaluateProfitExit(r, p);
  assert.equal(armed.action, 'hold-for-profit'); assert.equal(armed.armFloorUsd, 4.5);
  assert.equal(evaluateProfitExit({ ...r, quote: { ...r.quote!, bid: 0.64 }, floor: { usd: 4.5, knownAt: start } }, p).action, 'exit');
});
test('the adapter consumes the existing group verdict and rejects a future verdict', () => {
  const p = structuredClone(policy); p.pacer.group = true;
  const r = { ...exitRequest(start, 'yes', 0.59), group: { knownAt: start, sell: true, sumUsd: 4.8, members: 2 } };
  assert.equal(evaluateProfitExit(r, p).action, 'exit');
  assert.throws(() => evaluateProfitExit({ ...r, group: { ...r.group, knownAt: start + 1 } }, p), /invalid/);
});
test('shared predictive/economic week evidence preserves the older diagnostic scoring semantics', () => {
  const full: ContractScore[] = [];
  for (let week = 0; week < 8; week++) {
    const at = start + week * 7 * 86400000, { o, index } = observation(at);
    const complete = { ...index, prints: Array.from({ length: 131 }, (_, s) => ({ ts: at + s * 1000, knownAt: at + s * 1000, value: s >= 10 ? 100.3 : 100 })) };
    const outcome = labelContract(o, complete, at + 130000);
    full.push({ key: `k${week}`, at, week, eventKey: `e${week}`, weight: 1, loss: 0.1, brier: 0, p: { both: 1, neither: 0, moveOnly: 0, paysOnly: 0 },
      row: { observation: o, outcome, weight: 1, values: {}, eventKey: `e${week}`, quote: { ticker: o.query.contract.ticker, side: 'yes', at, knownAt: at,
        bid: 0.39, ask: 0.4, bidSize: 1, askSize: 1, entryFee: 0, exitFee: 0, settlementFee: 0, slippage: 0, sourceSha256: sha } } });
  }
  const base = full.map((r) => ({ ...r, loss: 0.2, p: { both: 0, neither: 1, moveOnly: 0, paysOnly: 0 } }));
  const predictive = pairedPredictiveEvidence(full, base);
  assert.equal(predictive.weeks, 8); assert.ok(Math.abs(predictive.gain!.mean - 0.1) < 1e-12);
  assert.deepEqual(pairedContractEvidence(full, base), predictive);
  const economic = pairedContractEvidence(full, base, { minimumMoveLowerBound: 0.8, minimumJointLowerBound: 0.7, minimumEntryEdge: 0.02, maximumQuoteAgeMs: 2000, maximumPosition: 1 });
  assert.equal(economic.rows, 8); assert.ok(Math.abs(economic.gain!.mean - 0.6) < 1e-12);
});
test('receipt-checked movement assembly, fitting, query and shadow run without loading settlement results', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-advance-product-')); t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const inputs = path.join(root, 'inputs');
  await writeProductDemoInputs(inputs);
  const specFile = path.join(inputs, 'spec.json'), spec = JSON.parse(fs.readFileSync(specFile, 'utf8'));
  const resultFile = path.join(inputs, spec.results.file); fs.unlinkSync(resultFile); // Should be irrelevant to a movement study.
  const policyFile = path.join(root, 'policy.json'); fs.writeFileSync(policyFile, JSON.stringify(policy));
  const dataset = path.join(root, 'dataset'), assembled = await assembleMovementDataset(specFile, policyFile, dataset);
  assert.ok(assembled.counts.complete > 0); assert.equal(assembled.inputs[resultFile], undefined);
  const data = await loadMovementDataset(dataset, policy); assert.ok(data.examples.every((e) => !('sidePays' in e.outcome)));
  const fitted = await exportAdvanceStudy(dataset, path.join(inputs, 'plan.json'), policyFile, path.join(root, 'study'), { epochs: 10, hidden: 3, trees: 4 });
  assert.equal(fitted.objective, 'advance-price-movement'); assert.notEqual(fitted.status, 'movement-validated');
  const shadow = await exportMovementShadow(path.join(root, 'study/product.json'), path.join(dataset, 'examples.jsonl'), policyFile,
    path.join(root, 'shadow'), { historicalAudit: true, maximumCalibrationAgeMs: 86400000, minimumMoveLowerBound: 0.8 });
  assert.ok(shadow.queries > 0); assert.equal(shadow.mode, 'historical-audit');
  await assert.rejects(exportMovementShadow(path.join(root, 'study/product.json'), path.join(dataset, 'examples.jsonl'), policyFile,
    path.join(root, 'fake-forward'), { historicalAudit: false, maximumCalibrationAgeMs: 86400000, minimumMoveLowerBound: 0.8 }), /forward/);
  const modified = JSON.parse(fs.readFileSync(specFile, 'utf8')); modified.decisions.sha256 = 'b'.repeat(64); fs.writeFileSync(specFile, JSON.stringify(modified));
  await assert.rejects(assembleMovementDataset(specFile, policyFile, path.join(root, 'bad')), /hash/);
});
test('forward lead starts at persisted publication and delayed publication cannot masquerade as an advance forecast', async (t) => {
  const now = Date.UTC(2026, 10, 8, 17), root = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-advance-publication-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const product = createAdvanceProduct(studied(), { source: sha }, { data: sha }, now - 1);
  const e = observation(now, 5), productFile = path.join(root, 'product.json'), observationsFile = path.join(root, 'observations.jsonl'), policyFile = path.join(root, 'policy.json');
  fs.writeFileSync(productFile, JSON.stringify(product)); fs.writeFileSync(observationsFile, JSON.stringify({ observation: e.o }) + '\n'); fs.writeFileSync(policyFile, JSON.stringify(policy));
  t.mock.timers.enable({ apis: ['Date'], now });
  const options = { historicalAudit: false, maximumCalibrationAgeMs: Number.MAX_SAFE_INTEGER, minimumMoveLowerBound: 0.8 };
  const result = await exportMovementShadow(productFile, observationsFile, policyFile, path.join(root, 'forward'), options);
  assert.equal(result.publication.publishedAt, now); assert.equal(result.publication.forwardTimingEligible, true);
  const y = labelTimelyMovement(e.o, e.index, now + 40000, e.byAt, 5000);
  assert.equal(movementLeadAfterPublication(y, result.publication).advanceMove, true);
  const { id, ...core } = result.publication, delayed = { ...core, publishedAt: now + 800, earliestEligibleMoveAt: now + 5800 };
  assert.equal(movementLeadAfterPublication(y, { ...delayed, id: digest(delayed) }).advanceMove, false, 'feature-time lead is insufficient when delivery used part of it');
  const rename = fs.renameSync;
  t.mock.method(fs, 'renameSync', (...args: Parameters<typeof fs.renameSync>) => { t.mock.timers.tick(26000); return rename(...args); });
  await assert.rejects(exportMovementShadow(productFile, observationsFile, policyFile, path.join(root, 'late'), options), /published too late/);
  const receipt = JSON.parse(fs.readFileSync(path.join(root, 'late/publication.json'), 'utf8'));
  assert.equal(receipt.forwardTimingEligible, false);
  assert.throws(() => movementLeadAfterPublication(y, receipt), /eligible/);
});
