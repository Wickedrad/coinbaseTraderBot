/** Purged, weighted joint contract candidates. Reuses the repository's MLP, trees and beta calibration. */
import { train, predictLogits, type Normalization } from '../mlp';
import { DEFAULT_GBDT, trainGbdt } from '../gbdt';
import { gbdtLogit, validateGbdt, type GbdtModel } from '../../bot/model/trees';
import type { DenseLayer } from '../../bot/model/metaModel';
import { applyBeta, fitBeta, IDENTITY_BETA, weightedLogLoss, type BetaCal } from '../../bot/model/calibration';
import { sigmoid } from '../../bot/util/num';
import { digest, encodeContractObservation, moveThresholdBps, stamp, CONTRACT_LABEL_SCHEMA, type ContractObservation, type ContractOutcome } from './contractDataset';
import { FROZEN_TRAIN_BEFORE, FROZEN_FINAL_FROM, type TimeWindow } from './jointPathData';
import type { PaperQuote } from './paper';
import { studyPolicy } from './studyPolicy';

export const CONTRACT_MODEL_SCHEMA = 'opportunity-contract-model-v1';
export type FeatureFamily = 'ta' | 'snn' | 'dominance' | 'clock' | 'micro' | 'daily';
export const FEATURE_FAMILIES: FeatureFamily[] = ['ta', 'snn', 'dominance', 'clock', 'micro', 'daily'];
export type ModelFamily = 'smooth' | 'trees' | 'temporal-linear';
export interface ContractExample { observation: ContractObservation; outcome: ContractOutcome; quote?: PaperQuote }
export interface ContractStudyPlan {
  studyPolicyId?: string;
  train: TimeWindow; stopping: TimeWindow; calibration: TimeWindow; selection: TimeWindow; audit: TimeWindow; embargoMs: number;
}
export interface EncodedContractRow extends ContractExample { values: Record<string, number>; weight: number; eventKey: string }
type HeadModel = { kind: 'prior'; p: number } | { kind: 'smooth'; layers: DenseLayer[]; norm: Normalization } | { kind: 'trees'; model: GbdtModel };
export interface ContractHead { model: HeadModel; calibration: BetaCal; calibrationFitted: boolean; trainingEvents: number }
const HEADS = ['move', 'paysGivenMove', 'paysGivenNoMove'] as const;
type HeadName = typeof HEADS[number];
interface Support { key: string; minimumRemainingSec: number; maximumRemainingSec: number; minimumMoneyness: number; maximumMoneyness: number;
  minimumFrameAgeSec: number; maximumFrameAgeSec: number;
  minimumMoveBps: number; maximumMoveBps: number; minimumCapMoneyness: number | null; maximumCapMoneyness: number | null }
export interface ContractModel {
  studyPolicyId: string;
  schema: typeof CONTRACT_MODEL_SCHEMA; id: string; family: ModelFamily; researchOnly: true; liveEntryAllowed: false;
  featureSchema: string; taSchema: string; engine: string; knownAt: number; trainedThrough: number;
  featureSources: Record<string, string>;
  termsBases: ContractObservation['termsBasis'][];
  included: FeatureFamily[]; featureNames: string[]; heads: Record<HeadName, ContractHead>; support: Support[];
  requiredFiniteFeatures: string[];
  snnIdentity: string | null; indexBasis: 'observed-index' | 'synthetic-fixture';
  snnPriceAgeLimitMs?: number | null;
}
export interface JointContractProbabilities { neither: number; moveOnly: number; paysOnly: number; both: number }
export interface ContractFitOptions { epochs?: number; hidden?: number; trees?: number; seed?: number }
const WEEK = 7 * 86400000;
export function featureFamily(name: string): FeatureFamily | null {
  if (name.startsWith('snn:')) return 'snn';
  if (name.startsWith('movement:') || name.startsWith('contract:') || name.startsWith('missing:contract:') || name.startsWith('asset:')) return null;
  if (/btcd|usdtd|dominance/.test(name)) return 'dominance';
  if (name.includes('clock')) return 'clock';
  if (name.includes('micro') || name.includes('cross_asset') || name.includes('funding')) return 'micro';
  if (name.includes('yahoo') || name.includes('daily')) return 'daily';
  return 'ta';
}
export const snnIdentity = (o: ContractObservation) => o.snn ? digest([o.snn.version, o.snn.flagsSha256, o.snn.provenance.domain, o.snn.provenance.variant, o.snn.provenance.inputLagMs ?? 0,
  o.snn.provenance.checkpointSha256, o.snn.provenance.checkpointKnownAt,
  ...(o.snn.provenance.maximumInputGapMs !== undefined ? [o.snn.provenance.maximumInputGapMs] : []),
  ...(o.snn.provenance.maximumInputPriceAgeMs !== undefined ? ['observed-price-age', o.snn.provenance.maximumInputPriceAgeMs] : []),
  ...(o.snn.provenance.replayProfile ? ['replay-profile', o.snn.provenance.replayProfile] : [])]) : null;
export const contractSupportKey = (o: ContractObservation, withSnn = true) => digest([o.query.asset, o.query.side, o.query.contract.terms.kind,
  o.query.contract.settlementReference, o.query.contract.averagingSec, o.query.geometry.life_sec, o.query.executionBufferMs, o.event,
  o.event.thresholdAtr || o.event.priorDriftAtr ? o.anchor?.definition : null, o.termsBasis, withSnn ? snnIdentity(o) : null]);
const moneyness = (o: ContractObservation) => Math.log(o.index.value / (o.query.contract.terms.strike ?? o.query.contract.terms.cap!));
const capMoneyness = (o: ContractObservation) => o.query.contract.terms.cap ? Math.log(o.index.value / o.query.contract.terms.cap) : null;
export const frameSources = (o: ContractObservation) => Object.fromEntries(Object.entries(o.frame.groups).map(([k, g]) => [k, g.source]).sort(([a], [b]) => a.localeCompare(b)));
export function validateStudyPlan(p: ContractStudyPlan) {
  const policy = studyPolicy(p.studyPolicyId);
  const windows = [p.train, p.stopping, p.calibration, p.selection, p.audit];
  if (!Number.isSafeInteger(p.embargoMs) || p.embargoMs < 1000 || windows.some((w, i) =>
    ![w.from, w.through].every(stamp) || w.from >= w.through || (i && w.from < windows[i - 1].through + p.embargoMs)) ||
    p.train.through > policy.trainBefore || p.audit.through > policy.finalFrom) throw new Error('invalid, overlapping or frozen-period study plan');
}
/** Reserved final rows are never encoded. A final outcome in an input is rejected even when
 * the caller selected an earlier window. Full contract spans and label arrivals are purged. */
export function contractRows(examples: ContractExample[], w: TimeWindow, studyPolicyId?: string): EncodedContractRow[] {
  const policy = studyPolicy(studyPolicyId);
  if (examples.length > 100000 || ![w.from, w.through].every(stamp) || w.from >= w.through || w.through > policy.finalFrom) throw new Error('invalid contract dataset/window');
  const ids = new Set<string>(), decisions = new Set<string>(), selected: EncodedContractRow[] = [];
  for (const e of examples) {
    const o = e.observation, y = e.outcome, at = o.query.asOf;
    if (ids.has(o.id) || y.observationId !== o.id || y.schema !== CONTRACT_LABEL_SCHEMA || !stamp(y.knownAt) ||
        y.plannedThrough !== o.query.contract.closeTime || (y.status === 'complete' &&
        (at >= policy.finalFrom || y.knownAt >= policy.finalFrom || y.plannedThrough >= policy.finalFrom))) throw new Error('duplicate, incompatible or reserved-final outcome');
    ids.add(o.id);
    const decisionKey = digest([o.query.asset, o.query.contract.ticker, at, o.query.side, o.event]);
    if (decisions.has(decisionKey)) throw new Error('duplicate contract decision');
    decisions.add(decisionKey);
    if (y.status !== 'complete' || at < w.from || at >= w.through || y.plannedThrough > w.through || y.knownAt > w.through) continue;
    if (y.knownAt < y.plannedThrough || y.category === null || y.category !== Number(y.timelyMove) + 2 * Number(y.sidePays) ||
        typeof y.timelyMove !== 'boolean' || typeof y.sidePays !== 'boolean' ||
        y.basis !== 'reconstructed-official-index-rule' || !Number.isFinite(y.settlementAverage) || !(y.settlementAverage! > 0)) throw new Error('invalid joint contract label');
    selected.push({ ...e, values: encodeContractObservation(o), weight: 1,
      eventKey: digest([o.query.asset, o.query.contract.settlementReference, o.query.contract.closeTime]) });
  }
  const counts = new Map<string, number>();
  for (const r of selected) counts.set(r.eventKey, (counts.get(r.eventKey) ?? 0) + 1);
  for (const r of selected) r.weight = 1 / counts.get(r.eventKey)!;
  return selected;
}
const relevant = (r: EncodedContractRow, name: HeadName) => name === 'move' || r.outcome.timelyMove === (name === 'paysGivenMove');
const target = (r: EncodedContractRow, name: HeadName) => Number(name === 'move' ? r.outcome.timelyMove : r.outcome.sidePays);
function raw(h: HeadModel, x: number[]) {
  return h.kind === 'prior' ? h.p : sigmoid(h.kind === 'trees' ? gbdtLogit(h.model, x) : predictLogits(h.layers, h.norm, [x], -1)[0]);
}
export interface BinaryResponseRow { values: Record<string, number>; target: number; weight: number; eventKey: string }
export function fitBinaryResponse(family: ModelFamily, rows: BinaryResponseRow[][], names: string[], options: ContractFitOptions = {}): ContractHead {
  const [tr, st, ca] = rows;
  if (rows.length !== 3 || !names.length || rows.some((rs) => rs.some((r) => ![0, 1].includes(r.target) || !(r.weight > 0) || !Number.isFinite(r.weight)))) throw new Error('invalid binary response rows');
  const X = (rs: BinaryResponseRow[]) => rs.map((r) => names.map((n) => r.values[n] ?? NaN));
  const Y = (rs: BinaryResponseRow[]) => rs.map((r) => r.target);
  const W = (rs: BinaryResponseRow[]) => rs.map((r) => r.weight);
  const sw = tr.reduce((s, r) => s + r.weight, 0), sy = tr.reduce((s, r) => s + r.weight * r.target, 0);
  const prior = (sy + 0.5) / (sw + 1), events = new Set(tr.map((r) => r.eventKey)).size;
  let model: HeadModel = { kind: 'prior', p: prior };
  if (events >= 20 && st.length >= 10 && new Set(Y(tr)).size === 2) {
    if (family === 'trees') {
      const base = Math.log(prior / (1 - prior));
      const fit = trainGbdt(X(tr), Y(tr), W(tr), tr.map(() => base), X(st), Y(st), W(st), st.map(() => base),
        { ...DEFAULT_GBDT, nTrees: options.trees ?? 64, maxDepth: 3, learningRate: 0.05, minLeafWeight: 3, maxBins: 16,
          patience: 10, featureFraction: 1, baggingFraction: 1, seed: options.seed ?? 19 });
      model = { kind: 'trees', model: { ...fit.model, baseScore: base } };
    } else {
      const fit = train(X(tr), Y(tr), X(st), Y(st), { hidden: family === 'temporal-linear' ? 0 : options.hidden ?? 12,
        maxEpochs: options.epochs ?? 150, patience: 25, l2: 0.002, lr: 0.015, seed: options.seed ?? 19, residual: -1 }, W(tr), W(st));
      model = { kind: 'smooth', layers: fit.layers, norm: fit.norm };
    }
  }
  const h: ContractHead = { model, calibration: { ...IDENTITY_BETA }, calibrationFitted: false, trainingEvents: events };
  const cy = Y(ca), cw = W(ca), cp = X(ca).map((x) => raw(model, x));
  if (new Set(ca.map((r) => r.eventKey)).size >= 30 && cy.filter(Boolean).length >= 5 && cy.filter((v) => !v).length >= 5) {
    const beta = fitBeta(cp, cy, cw);
    if ([beta.a, beta.b, beta.c].every(Number.isFinite) && beta.a >= 0 && beta.b >= 0 &&
        weightedLogLoss(cp.map((p) => applyBeta(p, beta)), cy, cw) <= weightedLogLoss(cp, cy, cw) + 1e-9) {
      h.calibration = beta; h.calibrationFitted = true;
    }
  }
  return h;
}
export const binaryResponseProbability = (h: ContractHead, x: number[]) => applyBeta(raw(h.model, x), h.calibration);
function fitHead(name: HeadName, family: ModelFamily, rows: EncodedContractRow[][], names: string[], options: ContractFitOptions): ContractHead {
  return fitBinaryResponse(family, rows.map((rs) => rs.filter((r) => relevant(r, name)).map((r) => ({ values: r.values, target: target(r, name), weight: r.weight, eventKey: r.eventKey }))), names, options);
}

export function fitContractModel(rows: { train: EncodedContractRow[]; stopping: EncodedContractRow[]; calibration: EncodedContractRow[] },
  plan: ContractStudyPlan, family: ModelFamily, included: FeatureFamily[], options: ContractFitOptions = {}): ContractModel {
  validateStudyPlan(plan);
  if (!['smooth', 'trees', 'temporal-linear'].includes(family) || included.some((g) => !FEATURE_FAMILIES.includes(g)) || new Set(included).size !== included.length ||
      (options.epochs !== undefined && (!Number.isInteger(options.epochs) || options.epochs < 5 || options.epochs > 1000)) ||
      (options.hidden !== undefined && (!Number.isInteger(options.hidden) || options.hidden < 1 || options.hidden > 64)) ||
      (options.trees !== undefined && (!Number.isInteger(options.trees) || options.trees < 1 || options.trees > 512))) throw new Error('invalid contract candidate options');
  const all = [rows.train, rows.stopping, rows.calibration], first = rows.train[0]?.observation;
  if (!first || all.some((rs) => !rs.length) || all.flat().some((r) => r.observation.frame.schema !== first.frame.schema ||
      r.observation.frame.taSchema !== first.frame.taSchema || r.observation.frame.engine !== first.frame.engine ||
      digest(frameSources(r.observation)) !== digest(frameSources(first)) ||
      r.observation.index.basis !== first.index.basis || (included.includes('snn') && snnIdentity(r.observation) !== snnIdentity(first)))) throw new Error('insufficient or incompatible candidate rows');
  for (const [i, window] of [plan.train, plan.stopping, plan.calibration].entries()) if (all[i].some((r) =>
    r.observation.query.asOf < window.from || r.observation.query.asOf >= window.through || r.outcome.knownAt > window.through || r.outcome.plannedThrough > window.through)) throw new Error('candidate rows cross purged windows');
  const names = [...new Set(rows.train.flatMap((r) => Object.keys(r.values)))].filter((n) => {
    const f = featureFamily(n); if (f !== null && !included.includes(f)) return false;
    let firstValue: number | undefined, hasMissing = false;
    for (const r of rows.train) { const v = r.values[n]; if (!Number.isFinite(v)) { hasMissing = true; continue; }
      if (firstValue !== undefined && v !== firstValue) return true; firstValue = v; }
    return firstValue !== undefined && hasMissing;
  }).sort();
  if (!names.length) names.push('contract:remaining_sec');
  if (names.length > 10000 || names.length * all.reduce((s, rs) => s + rs.length, 0) > 20000000) throw new Error('contract learner matrix limit exceeded');
  const support = new Map<string, Support>();
  for (const r of rows.train) {
    const o = r.observation, key = contractSupportKey(o, included.includes('snn')), remaining = o.query.geometry.remaining_sec, m = moneyness(o), move = moveThresholdBps(o), cap = capMoneyness(o), frameAge = o.query.geometry.feature_snapshot_age_sec;
    const s = support.get(key) ?? { key, minimumRemainingSec: remaining, maximumRemainingSec: remaining, minimumMoneyness: m, maximumMoneyness: m,
      minimumMoveBps: move, maximumMoveBps: move, minimumCapMoneyness: cap, maximumCapMoneyness: cap, minimumFrameAgeSec: frameAge, maximumFrameAgeSec: frameAge };
    s.minimumRemainingSec = Math.min(s.minimumRemainingSec, remaining); s.maximumRemainingSec = Math.max(s.maximumRemainingSec, remaining);
    s.minimumMoneyness = Math.min(s.minimumMoneyness, m); s.maximumMoneyness = Math.max(s.maximumMoneyness, m);
    s.minimumMoveBps = Math.min(s.minimumMoveBps, move); s.maximumMoveBps = Math.max(s.maximumMoveBps, move);
    s.minimumFrameAgeSec = Math.min(s.minimumFrameAgeSec, frameAge); s.maximumFrameAgeSec = Math.max(s.maximumFrameAgeSec, frameAge);
    if (cap !== null) { s.minimumCapMoneyness = Math.min(s.minimumCapMoneyness!, cap); s.maximumCapMoneyness = Math.max(s.maximumCapMoneyness!, cap); } support.set(key, s);
  }
  const core: Omit<ContractModel, 'id'> = { schema: CONTRACT_MODEL_SCHEMA, studyPolicyId: studyPolicy(plan.studyPolicyId).id, family, researchOnly: true, liveEntryAllowed: false,
    featureSchema: first.frame.schema, taSchema: first.frame.taSchema, engine: first.frame.engine, featureSources: frameSources(first),
    termsBases: [...new Set(rows.train.map((r) => r.observation.termsBasis))].sort(),
    knownAt: plan.calibration.through, trainedThrough: plan.train.through, included: [...included], featureNames: names,
    requiredFiniteFeatures: names.filter((name) => rows.train.every((r) => Number.isFinite(r.values[name]))),
    heads: Object.fromEntries(HEADS.map((name) => [name, fitHead(name, family, all, names, options)])) as ContractModel['heads'],
    support: [...support.values()].sort((a, b) => a.key.localeCompare(b.key)),
    snnIdentity: included.includes('snn') ? snnIdentity(first) : null, indexBasis: first.index.basis,
    snnPriceAgeLimitMs: included.includes('snn') ? first.snn?.provenance.maximumInputPriceAgeMs ?? null : null };
  const model = { ...core, id: digest(core) }; validateContractModel(model); return model;
}
export function contractProbabilities(model: ContractModel, values: Record<string, number>): JointContractProbabilities {
  const x = model.featureNames.map((n) => values[n] ?? NaN);
  const [move, paysMove, paysNoMove] = HEADS.map((n) => applyBeta(raw(model.heads[n].model, x), model.heads[n].calibration));
  return { neither: (1 - move) * (1 - paysNoMove), moveOnly: move * (1 - paysMove), paysOnly: (1 - move) * paysNoMove, both: move * paysMove };
}
/** An unseen missingness pattern must not receive confidence by mean imputation. */
export function missingRequiredInputs(model: Pick<ContractModel, 'requiredFiniteFeatures'>, values: Record<string, number>) {
  return model.requiredFiniteFeatures.filter((name) => !Number.isFinite(values[name]));
}
export function contractModelSupports(model: ContractModel, o: ContractObservation) {
  const s = model.support.find((s) => s.key === contractSupportKey(o, model.included.includes('snn')));
  return !!s && o.query.asOf >= model.knownAt && o.frame.schema === model.featureSchema && o.frame.taSchema === model.taSchema && o.frame.engine === model.engine &&
    o.query.geometry.feature_snapshot_age_sec >= s.minimumFrameAgeSec && o.query.geometry.feature_snapshot_age_sec <= s.maximumFrameAgeSec &&
    digest(frameSources(o)) === digest(model.featureSources) && moveThresholdBps(o) >= s.minimumMoveBps && moveThresholdBps(o) <= s.maximumMoveBps &&
    (capMoneyness(o) === null ? s.minimumCapMoneyness === null : capMoneyness(o)! >= s.minimumCapMoneyness! - 1e-12 && capMoneyness(o)! <= s.maximumCapMoneyness! + 1e-12) &&
    o.index.basis === model.indexBasis && (model.snnIdentity === null || snnIdentity(o) === model.snnIdentity) &&
    o.query.geometry.remaining_sec >= s.minimumRemainingSec && o.query.geometry.remaining_sec <= s.maximumRemainingSec &&
    moneyness(o) >= s.minimumMoneyness - 1e-12 && moneyness(o) <= s.maximumMoneyness + 1e-12;
}
export function validateContractModel(m: ContractModel) {
  const { id, ...core } = m;
  const policy = studyPolicy(m.studyPolicyId);
  if (m.schema !== CONTRACT_MODEL_SCHEMA || m.researchOnly !== true || m.liveEntryAllowed !== false || digest(core) !== id ||
      !['smooth', 'trees', 'temporal-linear'].includes(m.family) || !stamp(m.knownAt) || !stamp(m.trainedThrough) || m.trainedThrough > policy.trainBefore || m.knownAt >= policy.finalFrom ||
      m.knownAt < m.trainedThrough || !['observed-index', 'synthetic-fixture'].includes(m.indexBasis) ||
      (m.snnIdentity !== null && !/^[a-f0-9]{64}$/.test(m.snnIdentity)) || m.included.some((f) => !FEATURE_FAMILIES.includes(f)) ||
      (m.snnPriceAgeLimitMs != null && (!Number.isSafeInteger(m.snnPriceAgeLimitMs) || m.snnPriceAgeLimitMs < 1 || m.snnPriceAgeLimitMs > 60000)) ||
      !m.featureNames.length || m.featureNames.length > 10000 || new Set(m.featureNames).size !== m.featureNames.length || !m.support.length ||
      !Array.isArray(m.requiredFiniteFeatures) || new Set(m.requiredFiniteFeatures).size !== m.requiredFiniteFeatures.length || m.requiredFiniteFeatures.some((n) => !m.featureNames.includes(n)) ||
      m.featureNames.some((n) => { const f = featureFamily(n); return !/^[a-zA-Z0-9_:-]+$/.test(n) || (f !== null && !m.included.includes(f)); }) ||
      Object.values(m.featureSources).some((s) => typeof s !== 'string' || !s) || m.support.some((s) => !/^[a-f0-9]{64}$/.test(s.key) ||
        ![s.minimumRemainingSec, s.maximumRemainingSec, s.minimumMoneyness, s.maximumMoneyness, s.minimumMoveBps, s.maximumMoveBps, s.minimumFrameAgeSec, s.maximumFrameAgeSec].every(Number.isFinite) ||
        s.minimumFrameAgeSec < 0 || s.minimumFrameAgeSec > s.maximumFrameAgeSec ||
        s.minimumRemainingSec <= 0 || s.maximumRemainingSec > 86400 || s.minimumRemainingSec > s.maximumRemainingSec ||
        s.minimumMoneyness > s.maximumMoneyness || s.minimumMoveBps <= 0 || s.minimumMoveBps > s.maximumMoveBps)) throw new Error('invalid contract model/ID');
  for (const n of HEADS) validateBinaryResponse(m.heads[n], m.featureNames.length);
}
export interface ContractScore { key: string; at: number; week: number; eventKey: string; weight: number; loss: number; brier: number; p: JointContractProbabilities; row: EncodedContractRow }
export function scoreContractModel(m: ContractModel, rows: EncodedContractRow[]): ContractScore[] {
  const keys = ['neither', 'moveOnly', 'paysOnly', 'both'] as const;
  return rows.filter((r) => contractModelSupports(m, r.observation)).map((r) => {
    const p = contractProbabilities(m, r.values), actual = keys[r.outcome.category!];
    return { key: r.observation.id, at: r.observation.query.asOf, week: Math.floor(r.observation.query.asOf / WEEK), eventKey: r.eventKey, weight: r.weight,
      loss: -Math.log(Math.max(1e-9, p[actual])), brier: keys.reduce((s, k) => s + (p[k] - Number(k === actual)) ** 2, 0), p, row: r };
  });
}

/** Shared validation for the existing contract heads and independent movement head. */
export function validateBinaryResponse(h: ContractHead, inputCount: number) {
  const a = h.model;
  if (typeof h.calibrationFitted !== 'boolean' || !Number.isSafeInteger(h.trainingEvents) || h.trainingEvents < 0) throw new Error('invalid binary response evidence');
    if (![h.calibration.a, h.calibration.b, h.calibration.c].every(Number.isFinite) || h.calibration.a < 0 || h.calibration.b < 0) throw new Error('invalid contract calibration');
    if (a.kind === 'prior') { if (!(a.p > 0 && a.p < 1)) throw new Error('invalid contract prior'); }
    else if (a.kind === 'trees') {
      validateGbdt(a.model, inputCount);
      for (const tree of a.model.trees) {
        const visit = (i: number, seen: Set<number>) => {
          if (!Number.isInteger(i) || seen.has(i) || seen.size > 32 || !tree[i]) throw new Error('invalid or cyclic contract tree');
          const node = tree[i]; if (node.f < 0) return;
          const next = new Set(seen).add(i); visit(node.l, next); visit(node.r, next);
        }; visit(0, new Set());
      }
    } else if (a.kind === 'smooth') {
      if (a.norm.mean.length !== inputCount || a.norm.std.length !== inputCount || a.norm.mean.some((v) => !Number.isFinite(v)) || a.norm.std.some((v) => !Number.isFinite(v) || v <= 0) || !a.layers.length || a.layers.length > 2) throw new Error('invalid contract normalization');
      let inputs = inputCount;
      for (const l of a.layers) {
        if (!['linear', 'tanh'].includes(l.activation ?? '') || !l.weights.length || l.weights.length !== l.bias.length || l.weights.some((r) => r.length !== inputs || r.some((v) => !Number.isFinite(v))) || l.bias.some((v) => !Number.isFinite(v))) throw new Error('invalid contract dense layer');
        inputs = l.bias.length;
      }
      if (inputs !== 1) throw new Error('invalid contract output');
    } else throw new Error('unknown contract head');
}
