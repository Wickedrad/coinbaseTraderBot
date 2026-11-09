/** Offline competing-risk learner. Its outputs are spot-barrier forecasts, never contract prices. */
import { createHash } from 'node:crypto';
import { DEFAULT_GBDT, trainGbdt, type GbdtParams } from '../gbdt';
import { applyBeta, fitBeta, IDENTITY_BETA, weightedLogLoss, type BetaCal } from '../../bot/model/calibration';
import { gbdtLogit, validateGbdt, type GbdtModel } from '../../bot/model/trees';
import { sigmoid } from '../../bot/util/num';
import { bootstrapMeanCi } from '../stats';
import { FROZEN_FINAL_FROM, FROZEN_TRAIN_BEFORE, encodePathFrame, pathQueryValues, riskRows, riskValue, selectPathEpisodes,
  type FirstCause, type JointPathDataset, type PathDecision, type PathObservation, type RiskRow, type TimeWindow } from './jointPathData';
import { ATLAS_FEATURE_SCHEMA, type AtlasFeatureFrame, type MinuteEntryAnchor } from './features';
import { TANET_SCHEMA } from '../../bot/ta/taNet';
import { studyPolicy } from './studyPolicy';
import { predictLogits, type Normalization, type TrainOptions } from '../mlp';
import { MlpTorch, trainMlp } from '../mlpTorch';
import type { DenseLayer } from '../../bot/model/metaModel';

export const JOINT_PATH_SCHEMA = 'opportunity-competing-risk-v1';
const MIN = 60000, DAY = 86400000, WEEK = 7 * DAY;
const HEADS = ['event', 'ambiguous', 'targetGivenClear'] as const;
type HeadName = typeof HEADS[number];
interface Head {
  model: GbdtModel; calibration: BetaCal; mode: 'trees' | 'smooth' | 'prior'; trainingRows: number;
  smooth?: { layers: DenseLayer[]; norm: Normalization };
  trainingEngine?: 'typescript' | 'pytorch';
  calibrationStatus: 'fitted' | 'insufficient'; calibrationDecisions: number;
}
export interface RiskModel {
  studyPolicyId?: string;
  family?: 'trees' | 'smooth';
  schema: typeof JOINT_PATH_SCHEMA; researchOnly: true; liveEntryAllowed: false; calibrationRef: null;
  id: string; featureSchema: string; taSchema: string; engine: string; anchorDefinition: string;
  availabilityBasis: 'simulated-replay-cutoff';
  knownAt: number; featureNames: string[]; maxHorizonMin: number; support: string[]; heads: Record<HeadName, Head>;
}
export interface RiskFold { train: TimeWindow; stopping: TimeWindow; calibration: TimeWindow; evaluation: TimeWindow }
export interface FoldPlan { expanding?: boolean; trainMs: number; stoppingMs: number; calibrationMs: number; evaluationMs: number; stepMs: number; embargoMs: number; maxFolds: number }
export const DEFAULT_FOLD_PLAN: FoldPlan = { trainMs: 3 * DAY, stoppingMs: DAY, calibrationMs: DAY,
  evaluationMs: DAY, stepMs: DAY, embargoMs: 60 * MIN, maxFolds: 8 };
export const SMOKE_FOLD_PLAN: FoldPlan = { trainMs: 6 * 60 * MIN, stoppingMs: 2 * 60 * MIN, calibrationMs: 2 * 60 * MIN,
  evaluationMs: 2 * 60 * MIN, stepMs: 2 * 60 * MIN, embargoMs: 60 * MIN, maxFolds: 1 };
export function planRiskFolds(data: JointPathDataset, p: FoldPlan): RiskFold[] {
  if (![p.trainMs, p.stoppingMs, p.calibrationMs, p.evaluationMs, p.stepMs].every((n) => Number.isSafeInteger(n) && n > 0) ||
      !Number.isSafeInteger(p.embargoMs) || p.embargoMs < 0 || p.stepMs < p.evaluationMs || !Number.isInteger(p.maxFolds) || p.maxFolds < 1 || p.maxFolds > 32) throw new Error('invalid purged fold plan');
  const times = [...data.decisions.values()].filter((d) => d.at < data.trainBefore).map((d) => d.at);
  if (!times.length) return [];
  const from = times.reduce((a, b) => Math.min(a, b), Infinity), last = Math.min(data.trainBefore, times.reduce((a, b) => Math.max(a, b), -Infinity) + MIN), folds: RiskFold[] = [];
  for (let end = from + p.trainMs; folds.length < p.maxFolds; end += p.stepMs) {
    const stopping = { from: end + p.embargoMs, through: end + p.embargoMs + p.stoppingMs };
    const calibration = { from: stopping.through + p.embargoMs, through: stopping.through + p.embargoMs + p.calibrationMs };
    const evaluation = { from: calibration.through + p.embargoMs, through: calibration.through + p.embargoMs + p.evaluationMs };
    if (evaluation.through > last) break;
    folds.push({ train: { from: p.expanding === false ? end - p.trainMs : from, through: end }, stopping, calibration, evaluation });
  }
  return folds;
}
const supportKey = (asset: string, p: Pick<PathObservation, 'side' | 'targetAtr' | 'stopAtr'>) => JSON.stringify([asset, p.side, p.targetAtr, p.stopAtr]);
function headRows(rows: RiskRow[], name: HeadName) {
  return rows.filter((r) => name === 'event' || (name === 'ambiguous' ? r.cause !== 'none' : r.cause === 'target' || r.cause === 'stop'));
}
const outcome = (r: RiskRow, name: HeadName) => Number(name === 'event' ? r.cause !== 'none' : name === 'ambiguous' ? r.cause === 'ambiguous' : r.cause === 'target');
function selectFeatures(rows: RiskRow[], geometryOnly: boolean): string[] {
  const names = new Set<string>();
  const contexts = [...new Map(rows.map((r) => [r.decisionId, r])).values()];
  for (const row of contexts) for (const key of [...Object.keys(row.values), ...Object.keys(row.query)]) if (!geometryOnly || key.startsWith('query:') || key.startsWith('asset:')) names.add(key);
  if (names.size > 10000) throw new Error('too many learner features');
  return [...names].sort().filter((name) => {
    let first = NaN, found = false, missing = false;
    for (const row of name.startsWith('query:') ? rows : contexts) {
      const v = riskValue(row, name);
      if (!Number.isFinite(v)) { missing = true; continue; }
      if (found && v !== first) return true;
      first = v; found = true;
    }
    return found && missing;
  }); // No marginal predictive culling; interaction-only inputs survive if they vary.
}
function headLogit(head: Pick<Head, 'model' | 'smooth'>, x: number[]) {
  return head.smooth ? predictLogits(head.smooth.layers, head.smooth.norm, [x], -1)[0] : gbdtLogit(head.model, x);
}
function predictHead(head: Head, x: number[]) { return applyBeta(sigmoid(headLogit(head, x)), head.calibration); }
async function fitHead(train: RiskRow[], stop: RiskRow[], calibration: RiskRow[], names: string[], name: HeadName,
  params: Partial<GbdtParams>, family: 'trees' | 'smooth', smoothParams: TrainOptions, torch?: MlpTorch, log?: (message: string) => void): Promise<Head> {
  const tr = headRows(train, name), va = headRows(stop, name), ca = headRows(calibration, name);
  if ((tr.length + va.length + ca.length) * names.length > 20000000) throw new Error('learner matrix exceeds 20 million cells; reduce dataset or fold duration');
  const w = tr.map((r) => r.weight), y = tr.map((r) => outcome(r, name));
  const total = w.reduce((s, x) => s + x, 0), positives = tr.reduce((s, r) => s + r.weight * outcome(r, name), 0);
  const prior = (positives + 0.5) / (total + 1), base = Math.log(prior / (1 - prior));
  const vector = (r: RiskRow) => names.map((n) => riskValue(r, n));
  let model: GbdtModel = { trees: [], baseScore: base }, mode: Head['mode'] = 'prior';
  let smooth: Head['smooth'], trainingEngine: Head['trainingEngine'] = 'typescript';
  if (tr.length >= 20 && va.length && new Set(y).size > 1) {
    if (family === 'smooth') {
      trainingEngine = torch ? 'pytorch' : 'typescript';
      const fit = await trainMlp(torch, tr.map(vector), y, va.map(vector), va.map((r) => outcome(r, name)), smoothParams,
        w, va.map((r) => r.weight), (message) => { trainingEngine = 'typescript'; log?.(message); });
      smooth = { layers: fit.layers, norm: fit.norm }; mode = 'smooth';
    } else {
    const fit = trainGbdt(tr.map(vector), y, w, tr.map(() => base), va.map(vector), va.map((r) => outcome(r, name)), va.map((r) => r.weight), va.map(() => base),
      params);
    model = { ...fit.model, baseScore: base }; mode = model.trees.length ? 'trees' : 'prior';
    }
  }
  const head: Head = { model, mode, ...(smooth ? { smooth } : {}), trainingEngine, trainingRows: tr.length, calibration: { ...IDENTITY_BETA }, calibrationStatus: 'insufficient', calibrationDecisions: new Set(ca.map((r) => r.decisionId)).size };
  const cy = ca.map((r) => outcome(r, name)), cw = ca.map((r) => r.weight);
  if (tr.length && head.calibrationDecisions >= 30 && cy.filter((v) => v === 1).length >= 5 && cy.filter((v) => v === 0).length >= 5) {
    const cp = ca.map((r) => sigmoid(headLogit(head, vector(r)))), beta = fitBeta(cp, cy, cw);
    if ([beta.a, beta.b, beta.c].every(Number.isFinite) && beta.a >= 0 && beta.b >= 0 &&
        weightedLogLoss(cp.map((p) => applyBeta(p, beta)), cy, cw) <= weightedLogLoss(cp, cy, cw) + 1e-9) {
      head.calibration = beta; head.calibrationStatus = 'fitted';
    }
  }
  return head;
}
async function fitRiskModel(data: JointPathDataset, episodes: PathObservation[], train: RiskRow[], stopping: RiskRow[], calibration: RiskRow[], fold: RiskFold, geometryOnly: boolean,
  params: Partial<GbdtParams>, family: 'trees' | 'smooth', smoothParams: TrainOptions, torch?: MlpTorch, log?: (message: string) => void): Promise<RiskModel> {
  const names = selectFeatures(train, geometryOnly); if (!names.length) names.push('query:minute');
  const first = data.decisions.get(episodes[0].decisionId)!;
  const heads = {} as Record<HeadName, Head>;
  for (const name of HEADS) heads[name] = await fitHead(train, stopping, calibration, names, name, params, family, smoothParams, torch, log);
  const core: Omit<RiskModel, 'id'> = { schema: JOINT_PATH_SCHEMA, family, studyPolicyId: studyPolicy(data.studyPolicyId).id, researchOnly: true as const, liveEntryAllowed: false as const, calibrationRef: null,
    featureSchema: ATLAS_FEATURE_SCHEMA, taSchema: TANET_SCHEMA, engine: first.engine, anchorDefinition: first.anchorDefinition,
    availabilityBasis: 'simulated-replay-cutoff' as const,
    knownAt: fold.calibration.through, featureNames: names, maxHorizonMin: Math.min(data.maxHorizonMin, train.reduce((m, r) => Math.max(m, r.minute), 0)),
    support: [...new Set(episodes.map((p) => supportKey(p.asset, p)))].sort(), heads };
  return { ...core, id: createHash('sha256').update(JSON.stringify(core)).digest('hex') };
}
export interface CauseProbabilities { none: number; target: number; stop: number; ambiguous: number }
function curveForValues(model: RiskModel, values: Record<string, number>, query: Pick<PathObservation, 'side' | 'targetAtr' | 'stopAtr'>, horizonMin: number): CauseProbabilities[] {
  let none = 1, target = 0, stop = 0, ambiguous = 0;
  const curve: CauseProbabilities[] = [];
  for (let minute = 1; minute <= horizonMin; minute++) {
    const q = pathQueryValues(query, minute), x = model.featureNames.map((n) => q[n as keyof typeof q] ?? values[n] ?? NaN);
    const hit = predictHead(model.heads.event, x), amb = predictHead(model.heads.ambiguous, x), clearTarget = predictHead(model.heads.targetGivenClear, x);
    const mass = none * hit;
    target += mass * (1 - amb) * clearTarget; stop += mass * (1 - amb) * (1 - clearTarget); ambiguous += mass * amb; none *= 1 - hit;
    curve.push({ none, target, stop, ambiguous });
  }
  return curve;
}
export function predictJointPath(model: RiskModel, frame: AtlasFeatureFrame, anchor: MinuteEntryAnchor,
  query: { side: 'long' | 'short'; targetAtr: number; stopAtr: number; horizonMin: number }) {
  if (model.schema !== JOINT_PATH_SCHEMA || model.researchOnly !== true || model.liveEntryAllowed !== false || model.calibrationRef !== null || model.availabilityBasis !== 'simulated-replay-cutoff' ||
      model.featureSchema !== frame.schema || model.taSchema !== frame.taSchema || model.engine !== frame.engine || model.anchorDefinition !== anchor.definition ||
      frame.decisionAt < model.knownAt || anchor.knownAt !== frame.decisionAt || !(anchor.price > 0) || !Number.isFinite(anchor.price) || !(anchor.atrBps! > 0) || !Number.isFinite(anchor.atrBps) ||
      Math.max(query.targetAtr, query.stopAtr) * anchor.atrBps! >= 10000 ||
      !Number.isInteger(query.horizonMin) || query.horizonMin < 1 || query.horizonMin > model.maxHorizonMin || !model.support.includes(supportKey(frame.asset, query))) return null;
  const curve = curveForValues(model, encodePathFrame(frame), query, query.horizonMin);
  return { schema: JOINT_PATH_SCHEMA, kind: 'spot-barrier-first-hit' as const, researchOnly: true, liveEntryAllowed: false, calibrationRef: null,
    modelId: model.id, asOf: frame.decisionAt, asset: frame.asset, query: { ...query }, timeResolutionMinutes: 1,
    targetPrice: anchor.price * (1 + (query.side === 'long' ? 1 : -1) * query.targetAtr * anchor.atrBps! / 10000),
    stopPrice: anchor.price * (1 - (query.side === 'long' ? 1 : -1) * query.stopAtr * anchor.atrBps! / 10000),
    probabilities: curve.at(-1)!, curve,
    targetFirstOrderRange: { identified: curve.at(-1)!.target, includingAmbiguous: curve.at(-1)!.target + curve.at(-1)!.ambiguous },
    caution: 'Order ambiguity range is not a statistical confidence interval; spot-barrier forecasts are not contract settlement probabilities.' };
}
export function validateRiskModel(model: RiskModel) {
  const policy = studyPolicy(model.studyPolicyId);
  if (model.schema !== JOINT_PATH_SCHEMA || model.researchOnly !== true || model.liveEntryAllowed !== false || model.calibrationRef !== null || model.availabilityBasis !== 'simulated-replay-cutoff' || !model.featureNames.length || model.featureNames.length > 10000 || new Set(model.featureNames).size !== model.featureNames.length ||
      (model.family !== undefined && !['trees', 'smooth'].includes(model.family)) ||
      !Number.isSafeInteger(model.knownAt) || model.knownAt > policy.trainBefore || !Number.isInteger(model.maxHorizonMin) || model.maxHorizonMin < 1 || model.maxHorizonMin > 1440) throw new Error('invalid risk model');
  for (const name of HEADS) {
    const h = model.heads[name]; validateGbdt(h.model, model.featureNames.length);
    if (!['trees', 'smooth', 'prior'].includes(h.mode) || (h.mode === 'smooth') !== Boolean(h.smooth) ||
        (h.mode === 'smooth' && model.family !== 'smooth') || (h.mode === 'trees' && model.family === 'smooth')) throw new Error('invalid risk head family');
    if (h.smooth) {
      const { layers, norm } = h.smooth;
      if (norm.mean.length !== model.featureNames.length || norm.std.length !== model.featureNames.length ||
          norm.mean.some((v) => !Number.isFinite(v)) || norm.std.some((v) => !Number.isFinite(v) || v <= 0) || layers.length !== 2) throw new Error('invalid risk normalization');
      let inputs = model.featureNames.length;
      for (const [index, l] of layers.entries()) {
        if (l.activation !== (index === 0 ? 'tanh' : 'linear') || !l.weights.length || l.weights.length > 64 || l.weights.length !== l.bias.length ||
            l.weights.some((r) => r.length !== inputs || r.some((v) => !Number.isFinite(v))) || l.bias.some((v) => !Number.isFinite(v))) throw new Error('invalid risk dense layer');
        inputs = l.bias.length;
      }
      if (inputs !== 1) throw new Error('invalid risk dense output');
    }
    for (const tree of h.model.trees) {
      const walk = (index: number, ancestors: Set<number>) => {
        if (ancestors.has(index) || ancestors.size >= 64) throw new Error('cyclic or excessive risk tree');
        const n = tree[index];
        if (!Number.isInteger(n.f) || n.f < -1) throw new Error('invalid risk tree feature');
        if (n.f < 0) return;
        if (!Number.isInteger(n.l) || !Number.isInteger(n.r)) throw new Error('invalid risk tree index');
        const next = new Set(ancestors).add(index); walk(n.l, next); walk(n.r, next);
      };
      walk(0, new Set());
    }
    if (![h.calibration.a, h.calibration.b, h.calibration.c].every(Number.isFinite) || h.calibration.a < 0 || h.calibration.b < 0) throw new Error('invalid risk calibration');
  }
  const { id, ...core } = model;
  if (createHash('sha256').update(JSON.stringify(core)).digest('hex') !== id) throw new Error('risk model content ID mismatch');
}
interface ScoreRow { at: number; weight: number; modelLoss: number; baselineLoss: number; brier: number }
export async function trainJointPaths(data: JointPathDataset, options: { plan?: FoldPlan; smokeTest?: boolean; params?: Partial<GbdtParams>; maxRiskRows?: number;
  family?: 'trees' | 'smooth'; mlpEngine?: 'ts' | 'torch' | 'auto'; smoothParams?: Partial<TrainOptions>; onProgress?: (message: string) => void } = {}) {
  const policy = studyPolicy(data.studyPolicyId);
  if (data.trainBefore > policy.trainBefore || data.finalFrom > policy.finalFrom ||
      (options.maxRiskRows !== undefined && (!Number.isSafeInteger(options.maxRiskRows) || options.maxRiskRows < 1))) throw new Error('frozen study dates or risk limits violated');
  const params: GbdtParams = { ...DEFAULT_GBDT, nTrees: 48, learningRate: 0.06, maxDepth: 3, minLeafWeight: 5,
    lambda: 2, maxBins: 16, patience: 10, featureFraction: 0.5, baggingFraction: 1, seed: 17, ...options.params };
  if (params.loss !== 'logistic' || !Number.isInteger(params.nTrees) || params.nTrees < 1 || params.nTrees > 512 || !Number.isInteger(params.maxDepth) || params.maxDepth < 1 || params.maxDepth > 8 ||
      !Number.isInteger(params.maxBins) || params.maxBins < 2 || params.maxBins > 64 || !Number.isInteger(params.patience) || params.patience < 0 || !Number.isSafeInteger(params.seed) ||
      ![params.learningRate, params.minLeafWeight, params.lambda, params.featureFraction, params.baggingFraction].every(Number.isFinite) || params.learningRate <= 0 || params.learningRate > 1 || params.minLeafWeight <= 0 || params.lambda < 0 ||
      params.featureFraction <= 0 || params.featureFraction > 1 || params.baggingFraction <= 0 || params.baggingFraction > 1) throw new Error('invalid joint learner parameters');
  const family = options.family ?? 'trees', mlpEngine = options.mlpEngine ?? 'ts';
  const smoothParams: TrainOptions = { hidden: 8, l2: 0.002, lr: 0.015, maxEpochs: 100, patience: 20, seed: 17, residual: -1, ...options.smoothParams };
  if (!['trees', 'smooth'].includes(family) || !['ts', 'torch', 'auto'].includes(mlpEngine) ||
      !Number.isInteger(smoothParams.hidden) || smoothParams.hidden < 1 || smoothParams.hidden > 64 ||
      !Number.isInteger(smoothParams.maxEpochs) || smoothParams.maxEpochs < 1 || smoothParams.maxEpochs > 500 ||
      !Number.isInteger(smoothParams.patience) || smoothParams.patience < 0 || !Number.isSafeInteger(smoothParams.seed) || smoothParams.residual !== -1 ||
      !Number.isFinite(smoothParams.lr) || smoothParams.lr <= 0 || smoothParams.lr > 1 || !Number.isFinite(smoothParams.l2) || smoothParams.l2 < 0) throw new Error('invalid smooth learner parameters');
  const plan = options.plan ?? (options.smokeTest ? SMOKE_FOLD_PLAN : DEFAULT_FOLD_PLAN), folds = planRiskFolds(data, plan);
  const results: Array<{ fold: RiskFold; trainingEpisodes: number; riskRows: number; evaluationEpisodes: number; modelLoss: number; baselineLoss: number; brier: number; model: RiskModel; baseline: RiskModel }> = [];
  const scores: ScoreRow[] = [];
  const torch = family === 'smooth' && folds.length ? await MlpTorch.start({ engine: mlpEngine, log: options.onProgress }) : undefined;
  const backend = { requested: mlpEngine, available: torch ? torch.device : 'typescript', notes: [] as string[] };
  const log = (message: string) => { backend.notes.push(message); options.onProgress?.(message); };
  try {
  for (const [index, fold] of folds.entries()) {
    const training = selectPathEpisodes(data, fold.train), support = new Set(training.map((p) => supportKey(p.asset, p)));
    const stopping = selectPathEpisodes(data, fold.stopping).filter((p) => support.has(supportKey(p.asset, p)));
    const calibration = selectPathEpisodes(data, fold.calibration).filter((p) => support.has(supportKey(p.asset, p)));
    const evaluation = selectPathEpisodes(data, fold.evaluation, true).filter((p) => support.has(supportKey(p.asset, p)));
    if (![training, stopping, calibration, evaluation].every((rows) => rows.length > 0)) continue;
    const tr = riskRows(data, training, options.maxRiskRows), lastRisk = tr.reduce((m, r) => Math.max(m, r.minute), 0);
    const va = riskRows(data, stopping, options.maxRiskRows).filter((r) => r.minute <= lastRisk), ca = riskRows(data, calibration, options.maxRiskRows).filter((r) => r.minute <= lastRisk);
    if (![tr, va, ca].every((rows) => rows.length > 0)) continue;
    options.onProgress?.(`Fold ${index + 1}: ${training.length} training episodes, ${tr.length} at-risk minutes; fitting joint and geometry baseline`);
    const model = await fitRiskModel(data, training, tr, va, ca, fold, false, params, family, smoothParams, torch, log);
    const baseline = await fitRiskModel(data, training, tr, va, ca, fold, true, params, family, smoothParams, torch, log);
    validateRiskModel(model); validateRiskModel(baseline);
    const multiplicity = new Map<string, number>();
    for (const e of evaluation) multiplicity.set(e.decisionId, (multiplicity.get(e.decisionId) ?? 0) + 1);
    const current: ScoreRow[] = [];
    for (const e of evaluation) {
      if (e.horizonMin > Math.min(model.maxHorizonMin, baseline.maxHorizonMin) || !model.support.includes(supportKey(e.asset, e))) continue;
      const d = data.decisions.get(e.decisionId)!, p = curveForValues(model, d.values, e, e.horizonMin).at(-1)!, b = curveForValues(baseline, d.values, e, e.horizonMin).at(-1)!;
      const row = { at: e.at, weight: 1 / multiplicity.get(e.decisionId)!, modelLoss: -Math.log(Math.max(1e-9, p[e.cause])), baselineLoss: -Math.log(Math.max(1e-9, b[e.cause])),
        brier: Object.entries(p).reduce((s, [key, value]) => s + (value - Number(key === e.cause)) ** 2, 0) };
      current.push(row); scores.push(row);
    }
    if (!current.length) continue;
    const mean = (key: 'modelLoss' | 'baselineLoss' | 'brier') => current.reduce((s, r) => s + r.weight * r[key], 0) / current.reduce((s, r) => s + r.weight, 0);
    results.push({ fold, trainingEpisodes: training.length, riskRows: tr.length, evaluationEpisodes: current.length,
      modelLoss: mean('modelLoss'), baselineLoss: mean('baselineLoss'), brier: mean('brier'), model, baseline });
  }
  } finally { await torch?.close(); }
  const blocks = new Map<number, { gain: number; weight: number }>();
  for (const s of scores) { const key = Math.floor(s.at / WEEK), b = blocks.get(key) ?? { gain: 0, weight: 0 }; b.gain += s.weight * (s.baselineLoss - s.modelLoss); b.weight += s.weight; blocks.set(key, b); }
  const gains = [...blocks.values()].map((b) => b.gain / b.weight);
  const evidence = gains.length >= 8 ? bootstrapMeanCi(gains, 0.05, 2000, 17) : null;
  return { schema: JOINT_PATH_SCHEMA, researchOnly: true, liveEntryAllowed: false, autoPromote: false, calibrationRef: null,
    status: results.length ? options.smokeTest ? 'smoke-test-only' : 'research-fit' : 'blocked-insufficient-history-or-rows',
    dataset: { studyPolicyId: policy.id, manifestSha256: data.manifestSha256, inputHashes: data.inputHashes, runId: data.runId, counts: data.counts, trainBefore: data.trainBefore, finalFrom: data.finalFrom },
    plan, family, params, ...(family === 'smooth' ? { smoothParams, backend } : {}), folds: results, weeklyEvidence: { blocks: gains.length, pairedLogLossGain: evidence,
      interpretation: 'Exploratory weekly-block diagnostics against the geometry baseline; not full-parent ablation or a multiple-testing-controlled promotion gate.' },
    limitations: ['No SNN state integration', 'No official contract settlement probabilities', 'No feature/memory retention selection',
      family === 'trees' ? 'Tree responses are piecewise constant; smooth-family comparison remains separate' : 'Smooth tanh responses; no independent sequence-family or family-selection qualification', 'No live or economic validation'] };
}
