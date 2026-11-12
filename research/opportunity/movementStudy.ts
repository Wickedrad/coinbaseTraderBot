/** Independent advance-movement learning. No contract payout labels or profit quotas are targets. */
import { digest, encodeContractObservation, moveThresholdBps, priorThresholdBps, stamp, type ContractObservation, type TimelyMovementOutcome } from './contractDataset';
import { encodePathFrame } from './jointPathData';
import { encodeSnnState } from './snnState';
import { binaryResponseProbability, featureFamily, FEATURE_FAMILIES, fitBinaryResponse, frameSources, missingRequiredInputs, snnIdentity,
  validateBinaryResponse, validateStudyPlan, type ContractFitOptions, type ContractHead, type ContractStudyPlan, type FeatureFamily, type ModelFamily } from './contractLearner';
import { holmRetained, pairedPredictiveEvidence, type PairedEvidence } from './contractStudy';
import { movementTargetPolicy, profitExitBy, validateProfitPolicy, type ProfitPolicy } from './profitExit';
import { studyPolicy } from './studyPolicy';
import type { MovementTimingForecast } from './contractTiming';

export const MOVEMENT_SCHEMA = 'opportunity-advance-movement-v1';
const WEEK = 7 * 86400000;
export interface MovementExample { observation: ContractObservation; byAt: number; outcome: TimelyMovementOutcome }
interface Row extends MovementExample { values: Record<string, number>; weight: number; eventKey: string; key: string }
interface Support { key: string; minSec: number; maxSec: number; minBps: number; maxBps: number; minAge: number; maxAge: number }
export interface AdvanceModel {
  schema: typeof MOVEMENT_SCHEMA; id: string; family: ModelFamily; studyPolicyId: string;
  researchOnly: true; liveEntryAllowed: false; objective: 'advance-price-movement';
  knownAt: number; trainedThrough: number; featureSchema: string; taSchema: string; engine: string;
  featureSources: Record<string, string>; indexReferences: Record<string, string>; indexBasis: string;
  targetPolicySha256: string; minimumLeadMs: number; included: FeatureFamily[]; featureNames: string[];
  requiredFiniteFeatures: string[]; snnIdentity: string | null; snnPriceAgeLimitMs: number | null;
  head: ContractHead; support: Support[];
}
export interface MovementScore { key: string; comparisonKey: string; week: number; weight: number; eventKey: string; loss: number; p: number; y: number; supportKey: string }
interface Band { supportKey: string; bin: number; weeks: number; events: number; frequency: number; radius: number }
export interface AdvanceStudy {
  schema: typeof MOVEMENT_SCHEMA; id: string; objective: 'advance-price-movement'; researchOnly: true; liveEntryAllowed: false; autoPromote: false;
  status: 'blocked-insufficient-data' | 'research-fit' | 'movement-validated'; blockers: string[];
  plan: ContractStudyPlan; targetPolicySha256: string; inputId: string;
  candidates: Array<{ model: AdvanceModel; selectionLoss: number | null; rows: number }>;
  retention: Array<{ group: FeatureFamily; parentId: string; ablatedId: string; predictive: PairedEvidence; decision: 'retained' | 'suppressed' | 'insufficient-evidence' }>;
  selected: AdvanceModel | null; baseline: AdvanceModel | null; snnComparison: AdvanceComparison | null;
  audit: PairedEvidence | null; calibration: { modelId: string; knownAt: number; minimumWeeks: 8; minimumEvents: 50; simultaneousVariants: 3; bins: Band[] } | null;
}
/** Same physical forecast across YES/NO sides and ladder strikes is one observation. */
export function movementObservationKey(o: ContractObservation, byAt: number, withSnn = true) {
  const i = o.index;
  return digest([o.query.asset, o.query.asOf, byAt, o.frame, o.event, o.anchor,
    [i.reference, i.sourceSha256, i.basis, i.at, i.knownAt, i.value, i.priorReturnBps], withSnn ? o.snn : null]);
}
export function movementDeadline(o: ContractObservation, policy: ProfitPolicy) {
  return Math.min(o.query.effectBy, profitExitBy(o.query.contract, policy));
}
function supportKey(o: ContractObservation, withSnn: boolean) {
  return digest([o.query.asset, o.event, o.event.thresholdAtr || o.event.priorDriftAtr ? o.anchor?.definition : null, withSnn ? snnIdentity(o) : null]);
}
export function encodeAdvanceMovement(o: ContractObservation, byAt: number, policy: ProfitPolicy) {
  encodeContractObservation(o); validateProfitPolicy(policy);
  if (!stamp(byAt) || byAt !== movementDeadline(o, policy) || byAt - o.query.asOf < Math.max(1000, policy.minimumLeadMs) + o.event.sustainSec * 1000) throw new Error('movement deadline leaves insufficient advance/sustain time');
  const x = { ...encodePathFrame(o.frame, true), ...encodeSnnState(o.snn, o.query.asOf) };
  Object.assign(x, { [`asset:${o.query.asset}`]: 1, 'movement:horizon_sec': (byAt - o.query.asOf) / 1000,
    'movement:direction_up': Number(o.event.direction === 'up'), 'movement:threshold_bps': moveThresholdBps(o),
    'movement:prior_return_bps': o.index.priorReturnBps ?? NaN, 'movement:prior_sec': o.event.priorWindowSec,
    'movement:prior_drift_bps': priorThresholdBps(o), 'movement:sustain_sec': o.event.sustainSec,
    'movement:sustain_fraction': o.event.sustainFraction, 'movement:minimum_lead_sec': policy.minimumLeadMs / 1000,
    'movement:index_age_sec': (o.query.asOf - o.index.at) / 1000, 'movement:atr_bps': o.anchor?.atrBps ?? NaN,
    'movement:frame_age_sec': (o.query.asOf - o.frame.decisionAt) / 1000 });
  for (const k of ['move', 'reversal', 'continuation']) x[`movement:event_${k}`] = Number(o.event.kind === k);
  for (const [k, v] of Object.entries(x)) if (k.startsWith('movement:')) x[`movement:missing_${k.slice(9)}`] = Number(!Number.isFinite(v));
  return x;
}
export function movementRows(data: MovementExample[], window: { from: number; through: number }, policy: ProfitPolicy, policyId?: string): Row[] {
  const registered = studyPolicy(policyId), keys = new Set<string>(), out: Row[] = [];
  if (data.length > 100000 || !stamp(window.from) || !stamp(window.through) || window.from >= window.through || window.through > registered.finalFrom) throw new Error('invalid movement dataset/window');
  for (const e of data) {
    const o = e.observation, y = e.outcome, key = movementObservationKey(o, e.byAt);
    if (keys.has(key) || y.schema !== 'opportunity-timely-movement-v1' || y.observationId !== o.id || y.plannedThrough !== e.byAt ||
        !stamp(y.knownAt) || y.minimumLeadMs !== policy.minimumLeadMs) throw new Error('duplicate or incompatible movement example');
    keys.add(key);
    if (y.status === 'complete' && Math.max(o.query.asOf, e.byAt, y.knownAt) >= registered.finalFrom) throw new Error('reserved-final movement outcome');
    if (y.status !== 'complete' || o.query.asOf < window.from || o.query.asOf >= window.through || Math.max(y.knownAt, e.byAt) > window.through) continue;
    if (y.knownAt < e.byAt || typeof y.timelyMove !== 'boolean' || typeof y.advanceMove !== 'boolean' ||
        y.timelyMove !== (y.firstMoveAt !== null) || (y.firstMoveAt !== null && (!stamp(y.firstMoveAt) || y.firstMoveAt <= o.query.asOf || y.firstMoveAt + o.event.sustainSec * 1000 > e.byAt)) ||
        y.leadMs !== (y.firstMoveAt === null ? null : y.firstMoveAt - o.query.asOf) ||
        y.advanceMove !== (y.leadMs !== null && y.leadMs >= policy.minimumLeadMs) ||
        !Number.isFinite(y.mfeBps) || y.mfeBps! < 0 || !Number.isFinite(y.maeBps) || y.maeBps! > 0) throw new Error('invalid advance-movement label');
    out.push({ ...e, values: encodeAdvanceMovement(o, e.byAt, policy), weight: 1, key,
      eventKey: digest([o.query.asset, o.index.reference, e.byAt]) });
  }
  const counts = new Map<string, number>(); for (const r of out) counts.set(r.eventKey, (counts.get(r.eventKey) ?? 0) + 1);
  for (const r of out) r.weight = 1 / counts.get(r.eventKey)!;
  return out;
}
export function fitAdvanceModel(rows: { train: Row[]; stopping: Row[]; calibration: Row[] }, plan: ContractStudyPlan,
  policy: ProfitPolicy, family: ModelFamily, included: FeatureFamily[], options: ContractFitOptions = {}): AdvanceModel {
  validateStudyPlan(plan); validateProfitPolicy(policy);
  const all = [rows.train, rows.stopping, rows.calibration], first = rows.train[0]?.observation;
  if (!first || all.some((r) => !r.length) || !['smooth', 'trees', 'temporal-linear'].includes(family) || new Set(included).size !== included.length ||
      included.some((g) => !FEATURE_FAMILIES.includes(g)) ||
      (options.epochs !== undefined && (!Number.isInteger(options.epochs) || options.epochs < 5 || options.epochs > 1000)) ||
      (options.hidden !== undefined && (!Number.isInteger(options.hidden) || options.hidden < 1 || options.hidden > 64)) ||
      (options.trees !== undefined && (!Number.isInteger(options.trees) || options.trees < 1 || options.trees > 512))) throw new Error('insufficient rows or invalid movement fit');
  const sources = frameSources(first), references: Record<string, string> = {};
  for (const [i, role] of [plan.train, plan.stopping, plan.calibration].entries()) for (const r of all[i]) {
    const o = r.observation;
    if (o.query.asOf < role.from || Math.max(r.byAt, r.outcome.knownAt) > role.through || o.frame.schema !== first.frame.schema || o.frame.taSchema !== first.frame.taSchema ||
        o.frame.engine !== first.frame.engine || digest(frameSources(o)) !== digest(sources) || o.index.basis !== first.index.basis ||
        (included.includes('snn') && snnIdentity(o) !== snnIdentity(first)) || (references[o.query.asset] && references[o.query.asset] !== o.index.reference)) throw new Error('movement fit crosses a role or mixes feature/SNN/index identity');
    references[o.query.asset] = o.index.reference;
  }
  const names = [...new Set(rows.train.flatMap((r) => Object.keys(r.values)))].filter((n) => {
    const f = featureFamily(n); if (f !== null && !included.includes(f)) return false;
    let firstValue: number | undefined, missing = false;
    for (const r of rows.train) { const v = r.values[n]; if (!Number.isFinite(v)) { missing = true; continue; }
      if (firstValue !== undefined && v !== firstValue) return true; firstValue = v; }
    return firstValue !== undefined && missing;
  }).sort();
  if (!names.length) names.push('movement:horizon_sec');
  if (names.length > 10000 || names.length * all.reduce((s, r) => s + r.length, 0) > 20000000) throw new Error('movement learner matrix limit exceeded');
  const support = new Map<string, Support>();
  for (const r of rows.train) {
    const o = r.observation, key = supportKey(o, included.includes('snn')), sec = (r.byAt - o.query.asOf) / 1000, bps = moveThresholdBps(o), age = (o.query.asOf - o.frame.decisionAt) / 1000;
    const s = support.get(key) ?? { key, minSec: sec, maxSec: sec, minBps: bps, maxBps: bps, minAge: age, maxAge: age };
    s.minSec = Math.min(s.minSec, sec); s.maxSec = Math.max(s.maxSec, sec); s.minBps = Math.min(s.minBps, bps); s.maxBps = Math.max(s.maxBps, bps);
    s.minAge = Math.min(s.minAge, age); s.maxAge = Math.max(s.maxAge, age); support.set(key, s);
  }
  const core: Omit<AdvanceModel, 'id'> = { schema: MOVEMENT_SCHEMA, objective: 'advance-price-movement', family, studyPolicyId: studyPolicy(plan.studyPolicyId).id,
    researchOnly: true, liveEntryAllowed: false, knownAt: plan.calibration.through, trainedThrough: plan.train.through,
    featureSchema: first.frame.schema, taSchema: first.frame.taSchema, engine: first.frame.engine, featureSources: sources, indexReferences: references,
    indexBasis: first.index.basis, targetPolicySha256: digest(movementTargetPolicy(policy)), minimumLeadMs: policy.minimumLeadMs,
    included: [...included], featureNames: names, requiredFiniteFeatures: names.filter((n) => rows.train.every((r) => Number.isFinite(r.values[n]))),
    snnIdentity: included.includes('snn') ? snnIdentity(first) : null, snnPriceAgeLimitMs: included.includes('snn') ? first.snn?.provenance.maximumInputPriceAgeMs ?? null : null,
    head: fitBinaryResponse(family, all.map((rs) => rs.map((r) => ({ values: r.values, target: Number(r.outcome.advanceMove), weight: r.weight, eventKey: r.eventKey }))), names, options),
    support: [...support.values()].sort((a, b) => a.key.localeCompare(b.key)) };
  const model = { ...core, id: digest(core) }; validateAdvanceModel(model); return model;
}
export function validateAdvanceModel(m: AdvanceModel) {
  const { id, ...core } = m, policy = studyPolicy(m.studyPolicyId);
  if (m.schema !== MOVEMENT_SCHEMA || m.objective !== 'advance-price-movement' || m.researchOnly !== true || m.liveEntryAllowed !== false || digest(core) !== id ||
      !['smooth', 'trees', 'temporal-linear'].includes(m.family) || !stamp(m.trainedThrough) || !stamp(m.knownAt) || m.trainedThrough > policy.trainBefore || m.knownAt < m.trainedThrough || m.knownAt >= policy.finalFrom ||
      !stamp(m.minimumLeadMs) || m.minimumLeadMs < 1000 || m.minimumLeadMs > 3600000 || !/^[a-f0-9]{64}$/.test(m.targetPolicySha256) || !['observed-index', 'synthetic-fixture'].includes(m.indexBasis) ||
      m.included.some((g) => !FEATURE_FAMILIES.includes(g)) || new Set(m.included).size !== m.included.length || !m.featureNames.length || m.featureNames.length > 10000 || new Set(m.featureNames).size !== m.featureNames.length ||
      m.featureNames.some((n) => { const f = featureFamily(n); return !/^[a-zA-Z0-9_:-]+$/.test(n) || n.startsWith('contract:') || n.startsWith('missing:contract:') || (f !== null && !m.included.includes(f)); }) ||
      m.requiredFiniteFeatures.some((n) => !m.featureNames.includes(n)) || !m.support.length || m.support.some((s) => !/^[a-f0-9]{64}$/.test(s.key) ||
        ![s.minSec, s.maxSec, s.minBps, s.maxBps, s.minAge, s.maxAge].every(Number.isFinite) || s.minSec <= 0 || s.maxSec > 86400 || s.minSec > s.maxSec || s.minBps <= 0 || s.minBps > s.maxBps || s.minAge < 0 || s.minAge > s.maxAge)) throw new Error('invalid movement model/ID');
  if (m.included.includes('snn') !== (m.snnIdentity !== null) || (m.snnIdentity !== null && !/^[a-f0-9]{64}$/.test(m.snnIdentity))) throw new Error('invalid movement SNN identity');
  validateBinaryResponse(m.head, m.featureNames.length);
}
export function advanceModelSupports(m: AdvanceModel, o: ContractObservation, byAt: number, p: ProfitPolicy) {
  const s = m.support.find((s) => s.key === supportKey(o, m.included.includes('snn'))), sec = (byAt - o.query.asOf) / 1000, bps = moveThresholdBps(o), age = (o.query.asOf - o.frame.decisionAt) / 1000;
  return !!s && m.targetPolicySha256 === digest(movementTargetPolicy(p)) && m.minimumLeadMs === p.minimumLeadMs && o.query.asOf >= m.knownAt &&
    o.frame.schema === m.featureSchema && o.frame.taSchema === m.taSchema && o.frame.engine === m.engine && digest(frameSources(o)) === digest(m.featureSources) &&
    m.indexReferences[o.query.asset] === o.index.reference && o.index.basis === m.indexBasis && (m.snnIdentity === null || snnIdentity(o) === m.snnIdentity) &&
    sec >= s.minSec && sec <= s.maxSec && bps >= s.minBps && bps <= s.maxBps && age >= s.minAge && age <= s.maxAge;
}
export function scoreAdvanceModel(m: AdvanceModel, rows: Row[], policy: ProfitPolicy): MovementScore[] {
  return rows.flatMap((r) => {
    if (!advanceModelSupports(m, r.observation, r.byAt, policy) || missingRequiredInputs(m, r.values).length) return [];
    const p = Math.max(1e-12, Math.min(1 - 1e-12, binaryResponseProbability(m.head, m.featureNames.map((n) => r.values[n] ?? NaN)))), y = Number(r.outcome.advanceMove);
    return [{ key: r.key, comparisonKey: movementObservationKey(r.observation, r.byAt, false), week: Math.floor(r.observation.query.asOf / WEEK), weight: r.weight, eventKey: r.eventKey,
      loss: -(y * Math.log(p) + (1 - y) * Math.log(1 - p)), p, y, supportKey: supportKey(r.observation, m.included.includes('snn')) }];
  });
}
const meanLoss = (rows: MovementScore[]) => rows.length ? rows.reduce((s, r) => s + r.weight * r.loss, 0) / rows.reduce((s, r) => s + r.weight, 0) : null;
export function runAdvanceStudy(data: MovementExample[], plan: ContractStudyPlan, p: ProfitPolicy, options: ContractFitOptions = {}): AdvanceStudy {
  validateStudyPlan(plan); validateProfitPolicy(p);
  const rows = { train: movementRows(data, plan.train, p, plan.studyPolicyId), stopping: movementRows(data, plan.stopping, p, plan.studyPolicyId),
    calibration: movementRows(data, plan.calibration, p, plan.studyPolicyId), selection: movementRows(data, plan.selection, p, plan.studyPolicyId), audit: movementRows(data, plan.audit, p, plan.studyPolicyId) };
  const s: Omit<AdvanceStudy, 'id'> = { schema: MOVEMENT_SCHEMA, objective: 'advance-price-movement', researchOnly: true, liveEntryAllowed: false, autoPromote: false,
    status: 'blocked-insufficient-data', blockers: [], plan, targetPolicySha256: digest(movementTargetPolicy(p)), inputId: digest(data),
    candidates: [], retention: [], selected: null, baseline: null, snnComparison: null, audit: null, calibration: null };
  const finish = () => ({ ...s, id: digest(s) });
  if (Object.values(rows).some((r) => !r.length)) { s.blockers.push('One or more purged roles lack complete movement paths'); return finish(); }
  const full = FEATURE_FAMILIES.filter((g) => g !== 'snn' || rows.train[0].observation.snn !== null);
  const fit = (family: ModelFamily, groups: FeatureFamily[]) => fitAdvanceModel(rows, plan, p, family, groups, options);
  for (const family of ['smooth', 'trees', 'temporal-linear'] as ModelFamily[]) {
    const model = fit(family, full), score = scoreAdvanceModel(model, rows.selection, p);
    s.candidates.push({ model, selectionLoss: meanLoss(score), rows: score.length });
  }
  const scores = s.candidates.map((c) => scoreAdvanceModel(c.model, rows.selection, p)), sets = scores.map((rs) => new Set(rs.map((r) => r.key)));
  const common = new Set(scores[0].map((r) => r.key).filter((k) => sets.every((set) => set.has(k))));
  s.candidates.forEach((c, i) => { c.selectionLoss = meanLoss(scores[i].filter((r) => common.has(r.key))); c.rows = common.size; });
  const winner = [...s.candidates].sort((a, b) => (a.selectionLoss ?? Infinity) - (b.selectionLoss ?? Infinity))[0];
  if (!common.size || winner.selectionLoss === null) { s.blockers.push('No common supported movement selection cohort'); return finish(); }
  const parent = scoreAdvanceModel(winner.model, rows.selection, p);
  for (const group of full) {
    const model = fit(winner.model.family, full.filter((g) => g !== group)), scored = scoreAdvanceModel(model, rows.selection, p);
    s.candidates.push({ model, selectionLoss: meanLoss(scored), rows: scored.length });
    s.retention.push({ group, parentId: winner.model.id, ablatedId: model.id, predictive: pairedPredictiveEvidence(parent, scored), decision: 'insufficient-evidence' });
  }
  const keep = holmRetained(s.retention.map((r) => r.predictive.p), 0.05 / 3, 3);
  s.retention.forEach((r, i) => { r.decision = keep.has(i) && (r.predictive.gain?.lo ?? -Infinity) > 0 ? 'retained' : r.predictive.p === null ? 'insufficient-evidence' : 'suppressed'; });
  s.selected = fit(winner.model.family, s.retention.filter((r) => r.decision === 'retained').map((r) => r.group));
  s.baseline = fit('temporal-linear', []);
  const audit = scoreAdvanceModel(s.selected, rows.audit, p), baseline = scoreAdvanceModel(s.baseline, rows.audit, p);
  const baselineKeys = new Set(baseline.map((b) => b.key)), paired = audit.filter((r) => baselineKeys.has(r.key));
  s.audit = pairedPredictiveEvidence(paired, baseline);
  const buckets = new Map<string, MovementScore[]>();
  for (const r of paired) { const k = `${r.supportKey}:${Math.min(9, Math.floor(r.p * 10))}`; const b = buckets.get(k) ?? []; b.push(r); buckets.set(k, b); }
  const tests = Math.max(1, s.selected.support.length * 10 * 3);
  const bins = [...buckets.values()].map((rs) => {
    const weeks = new Map<number, { y: number; weight: number }>();
    for (const r of rs) { const w = weeks.get(r.week) ?? { y: 0, weight: 0 }; w.y += r.y * r.weight; w.weight += r.weight; weeks.set(r.week, w); }
    return { supportKey: rs[0].supportKey, bin: Math.min(9, Math.floor(rs[0].p * 10)), weeks: weeks.size, events: new Set(rs.map((r) => r.eventKey)).size,
      frequency: [...weeks.values()].reduce((sum, w) => sum + w.y / w.weight, 0) / weeks.size,
      radius: Math.min(1, Math.sqrt(Math.log(2 * tests / 0.05) / (2 * weeks.size))) };
  });
  s.calibration = { modelId: s.selected.id, knownAt: plan.audit.through, minimumWeeks: 8, minimumEvents: 50, simultaneousVariants: 3, bins };
  s.status = 'research-fit';
  if (s.selected.indexBasis !== 'observed-index') s.blockers.push('Synthetic movement fixtures are software checks');
  if (s.selected.head.model.kind === 'prior' || !s.selected.head.calibrationFitted) s.blockers.push('Independent movement head fitting/calibration is insufficient');
  if (s.audit.weeks < 8 || (s.audit.gain?.lo ?? -Infinity) <= 0 || (s.audit.p ?? 1) > 0.05 / 3) s.blockers.push('Locked movement forecast lacks independent weekly predictive gain');
  if (!bins.some((b) => b.weeks >= 8 && b.events >= 50)) s.blockers.push('Movement calibration groups lack independent coverage');
  if (s.selected.included.includes('snn')) s.blockers.push(MOVEMENT_SNN_BLOCKER);
  if (s.selected.included.includes('snn') && !(s.selected.snnPriceAgeLimitMs! > 0 && s.selected.snnPriceAgeLimitMs! <= 3000)) s.blockers.push('Retained SNN needs an explicit observed-price age limit of at most three seconds');
  if (!s.blockers.length) s.status = 'movement-validated';
  return finish();
}
export interface AdvanceProduct {
  schema: typeof MOVEMENT_SCHEMA; id: string; createdAt: number; researchOnly: true; liveEntryAllowed: false; autoPromote: false;
  study: AdvanceStudy; codeHashes: Record<string, string>; inputHashes: Record<string, string>;
}
export function createAdvanceProduct(study: AdvanceStudy, codeHashes: Record<string, string>, inputHashes: Record<string, string>, createdAt = Date.now()): AdvanceProduct {
  const core: Omit<AdvanceProduct, 'id'> = { schema: MOVEMENT_SCHEMA, createdAt, researchOnly: true, liveEntryAllowed: false, autoPromote: false, study, codeHashes, inputHashes };
  const p = { ...core, id: digest(core) }; validateAdvanceProduct(p); return p;
}
export function validateAdvanceProduct(p: AdvanceProduct) {
  const { id, ...core } = p, { id: studyId, ...s } = p.study;
  if (p.schema !== MOVEMENT_SCHEMA || digest(core) !== id || !stamp(p.createdAt) || p.researchOnly !== true || p.liveEntryAllowed !== false || p.autoPromote !== false ||
      s.schema !== MOVEMENT_SCHEMA || s.objective !== 'advance-price-movement' || s.researchOnly !== true || s.liveEntryAllowed !== false || s.autoPromote !== false || digest(s) !== studyId ||
      !['blocked-insufficient-data', 'research-fit', 'movement-validated'].includes(s.status) || Object.values({ ...p.codeHashes, ...p.inputHashes }).some((h) => !/^[a-f0-9]{64}$/.test(h))) throw new Error('invalid advance product/study ID');
  validateStudyPlan(s.plan);
  for (const m of [...s.candidates.map((c) => c.model), ...[s.selected, s.baseline].filter((m) => m !== null)]) {
    validateAdvanceModel(m);
    if (m.studyPolicyId !== studyPolicy(s.plan.studyPolicyId).id || m.knownAt !== s.plan.calibration.through || m.trainedThrough !== s.plan.train.through || m.targetPolicySha256 !== s.targetPolicySha256) throw new Error('movement fitting/target registration differs');
  }
  if (s.selected?.included.some((g) => !s.retention.some((r) => r.group === g && r.decision === 'retained'))) throw new Error('movement group lacks retention evidence');
  if (s.status === 'movement-validated' && s.selected?.included.includes('snn')) {
    const e = s.snnComparison, variant = e?.recommended;
    if (!e || !variant || variant === 'none' || !(s.selected.snnPriceAgeLimitMs! > 0 && s.selected.snnPriceAgeLimitMs! <= 3000) ||
        e.modelIds[variant] !== s.selected.id || e.inputIds[variant] !== s.inputId || e.knownAt !== s.plan.audit.through || e.targetPolicySha256 !== s.targetPolicySha256) throw new Error('movement SNN comparison/freshness qualification absent');
    const { id, ...core } = e; if (digest(core) !== id) throw new Error('invalid movement SNN comparison ID');
  }
  const c = s.calibration;
  if (c && (c.modelId !== s.selected?.id || c.knownAt !== s.plan.audit.through || c.minimumWeeks !== 8 || c.minimumEvents !== 50 || c.simultaneousVariants !== 3 ||
      c.bins.some((b) => !Number.isInteger(b.bin) || b.bin < 0 || b.bin > 9 || !Number.isInteger(b.weeks) || b.weeks < 1 || !Number.isInteger(b.events) || b.events < 1 ||
        !Number.isFinite(b.frequency) || b.frequency < 0 || b.frequency > 1 || !Number.isFinite(b.radius) || b.radius < 0 || b.radius > 1))) throw new Error('invalid movement audit calibration');
  if (s.status !== 'blocked-insufficient-data' && (!s.selected || !s.baseline || !s.audit || !c)) throw new Error('incomplete movement study');
  if (s.status === 'movement-validated' && (s.blockers.length || s.selected?.indexBasis !== 'observed-index' || !s.selected.head.calibrationFitted || s.selected.head.model.kind === 'prior' ||
      !s.audit || s.audit.weeks < 8 || (s.audit.gain?.lo ?? -Infinity) <= 0 || (s.audit.p ?? 1) > 0.05 / 3 || !c?.bins.some((b) => b.weeks >= 8 && b.events >= 50))) throw new Error('unsubstantiated movement validation');
}
export const MOVEMENT_SNN_BLOCKER = 'Retained SNN needs a same-period movement-only S5/S6 baseline comparison';
export interface AdvanceComparison {
  schema: 'opportunity-movement-snn-comparison-v1'; id: string; recommended: 'S5' | 'S6' | 'none';
  studyIds: Record<'S5' | 'S6', string>; modelIds: Record<'S5' | 'S6', string>; inputIds: Record<'S5' | 'S6', string>;
  targetPolicySha256: string; knownAt: number; rows: number;
  tests: Array<{ contrast: string; predictive: PairedEvidence; accepted: boolean }>;
  researchOnly: true; liveEntryAllowed: false;
}
/** Same physical queries, observed movement labels and audit period; no settlement/economic contrast. */
export function compareAdvanceSnn(s5: AdvanceStudy, data5: MovementExample[], s6: AdvanceStudy, data6: MovementExample[], p: ProfitPolicy): AdvanceComparison {
  if (digest(s5.plan) !== digest(s6.plan) || s5.targetPolicySha256 !== s6.targetPolicySha256 || s5.targetPolicySha256 !== digest(movementTargetPolicy(p)) ||
      !s5.selected || !s6.selected || !s5.baseline || !s6.baseline || s5.inputId !== digest(data5) || s6.inputId !== digest(data6) ||
      data5.some((e) => e.observation.snn?.provenance.variant !== 'S5') || data6.some((e) => e.observation.snn?.provenance.variant !== 'S6')) throw new Error('movement SNN comparison requires matching locked variants and datasets');
  const rows5 = movementRows(data5, s5.plan.audit, p, s5.plan.studyPolicyId), rows6 = movementRows(data6, s6.plan.audit, p, s6.plan.studyPolicyId);
  const align = (rs: MovementScore[]) => rs.map((r) => ({ ...r, key: r.comparisonKey }));
  const a = align(scoreAdvanceModel(s5.selected, rows5, p)), b = align(scoreAdvanceModel(s6.selected, rows6, p));
  const simple5 = align(scoreAdvanceModel(s5.baseline, rows5, p)), simple6 = align(scoreAdvanceModel(s6.baseline, rows6, p));
  const sets = [a, b, simple5, simple6].map((rs) => new Set(rs.map((r) => r.key))), common = new Set(a.map((r) => r.key).filter((k) => sets.every((s) => s.has(k))));
  const same = (rs: MovementScore[]) => rs.filter((r) => common.has(r.key));
  const tests = ([['S5-vs-simple', a, simple5], ['S6-vs-simple', b, simple6], ['S6-vs-S5', b, a]] as const)
    .map(([contrast, full, base]) => ({ contrast, predictive: pairedPredictiveEvidence(same(full), same(base)), accepted: false }));
  const keep = holmRetained(tests.map((t) => t.predictive.p));
  tests.forEach((t, i) => { t.accepted = keep.has(i) && (t.predictive.gain?.lo ?? -Infinity) > 0; });
  const recommended = s6.selected.included.includes('snn') && tests[1].accepted && tests[2].accepted ? 'S6'
    : s5.selected.included.includes('snn') && tests[0].accepted ? 'S5' : 'none';
  const core: Omit<AdvanceComparison, 'id'> = { schema: 'opportunity-movement-snn-comparison-v1', recommended,
    studyIds: { S5: s5.id, S6: s6.id }, modelIds: { S5: s5.selected.id, S6: s6.selected.id }, inputIds: { S5: s5.inputId, S6: s6.inputId },
    targetPolicySha256: s5.targetPolicySha256, knownAt: s5.plan.audit.through, rows: common.size, tests, researchOnly: true, liveEntryAllowed: false };
  return { ...core, id: digest(core) };
}
export function qualifyAdvanceSnn(s: AdvanceStudy, e: AdvanceComparison): AdvanceStudy {
  const { id, ...core } = e, v = e.recommended;
  if (digest(core) !== id || v === 'none' || e.studyIds[v] !== s.id || e.modelIds[v] !== s.selected?.id || e.inputIds[v] !== s.inputId ||
      e.targetPolicySha256 !== s.targetPolicySha256 || e.knownAt !== s.plan.audit.through || !s.selected.included.includes('snn')) throw new Error('movement SNN evidence does not qualify this study');
  const { id: oldId, ...updated } = structuredClone(s);
  updated.snnComparison = e; updated.blockers = updated.blockers.filter((b) => b !== MOVEMENT_SNN_BLOCKER);
  updated.status = updated.blockers.length ? 'research-fit' : 'movement-validated';
  return { ...updated, id: digest(updated) };
}
export interface CalibratedMovementForecast extends MovementTimingForecast { calibrationRef: string | null; minimumLeadMs: number; targetPolicySha256: string }
/** Named locked artifact; no payout probabilities and no urgency-based model selection. */
export function queryAdvanceProduct(product: AdvanceProduct, o: ContractObservation, policy: ProfitPolicy,
  options: { maximumCalibrationAgeMs: number; minimumMoveLowerBound: number; historicalAudit?: boolean }) {
  validateAdvanceProduct(product); validateProfitPolicy(policy);
  if (!stamp(options.maximumCalibrationAgeMs) || options.maximumCalibrationAgeMs === 0 || !Number.isFinite(options.minimumMoveLowerBound) || options.minimumMoveLowerBound <= 0.5 || options.minimumMoveLowerBound > 1) throw new Error('explicit movement confidence/freshness policy required');
  const s = product.study, m = s.selected, byAt = movementDeadline(o, policy);
  const out = { productId: product.id, researchOnly: true as const, liveEntryAllowed: false as const,
    status: 'unavailable' as 'unavailable' | 'unsupported' | 'unqualified' | 'expired' | 'insufficient-confidence' | 'movement-supported',
    reason: 'locked movement model unavailable', uncertaintyBasis: 'Independent audit-group average movement frequencies under stable, independent-week assumptions; not individual-probability confidence intervals', forecast: null as CalibratedMovementForecast | null,
    execution: 'Movement timing only; the existing fee, entry, risk and profit-exit controls still decide execution', blockers: s.blockers };
  if (!m || o.query.asOf < (options.historicalAudit ? s.plan.audit.through : Math.max(product.createdAt, s.plan.audit.through))) return out;
  if (byAt - o.query.asOf < Math.max(1000, policy.minimumLeadMs) + o.event.sustainSec * 1000) return { ...out, status: 'unsupported' as const, reason: 'too little time for an advance move before the normal exit deadline' };
  const values = encodeAdvanceMovement(o, byAt, policy);
  if (!advanceModelSupports(m, o, byAt, policy) || missingRequiredInputs(m, values).length) return { ...out, status: 'unsupported' as const, reason: 'movement horizon, source, feature/SNN identity or observed missingness differs' };
  const probability = binaryResponseProbability(m.head, m.featureNames.map((n) => values[n] ?? NaN));
  const cal = s.calibration, bin = cal?.bins.find((b) => b.supportKey === supportKey(o, m.included.includes('snn')) && b.bin === Math.min(9, Math.floor(probability * 10)));
  const supported = !!bin && bin.weeks >= 8 && bin.events >= 50;
  const expired = !cal || o.query.asOf - cal.knownAt > options.maximumCalibrationAgeMs;
  const qualified = s.status === 'movement-validated' && supported && !expired;
  const lower = supported ? Math.min(probability, Math.max(0, bin!.frequency - bin!.radius)) : 0, upper = supported ? Math.max(probability, Math.min(1, bin!.frequency + bin!.radius)) : 1;
  const forecast: CalibratedMovementForecast = { kind: 'movement', id: digest([product.id, movementObservationKey(o, byAt)]), modelId: m.id,
    asset: o.query.asset, asOf: o.query.asOf, featuresKnownAt: Math.max(o.query.featuresKnownAt, o.index.knownAt, o.snn?.provenance.inputKnownAt ?? 0),
    direction: o.event.direction, eventDefinitionId: o.event.id, byAt, moveBy: { probability, lower, upper },
    calibrationRef: qualified ? digest(cal) : null, minimumLeadMs: policy.minimumLeadMs, targetPolicySha256: m.targetPolicySha256 };
  return { ...out, forecast, status: expired ? 'expired' as const : !qualified ? 'unqualified' as const : lower < options.minimumMoveLowerBound ? 'insufficient-confidence' as const : 'movement-supported' as const,
    reason: expired ? 'movement calibration missing or expired' : !qualified ? 'movement reliability or this audit group is incomplete' : lower < options.minimumMoveLowerBound ? 'advance-movement confidence is below the caller threshold' : 'advance movement supported before the normal sale deadline' };
}
