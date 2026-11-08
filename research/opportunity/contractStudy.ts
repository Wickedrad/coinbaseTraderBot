/** Independent selection/audit windows and a reversible relationship-retention ledger. */
import { bootstrapMeanCi, rng } from '../stats';
import { digest } from './contractDataset';
import { contractRows, contractProbabilities, contractSupportKey, FEATURE_FAMILIES, fitContractModel, scoreContractModel, validateStudyPlan,
  type ContractExample, type ContractFitOptions, type ContractModel, type ContractScore, type ContractStudyPlan, type FeatureFamily, type ModelFamily } from './contractLearner';
import { quoteAvailable, validatePaperPolicy, type PaperPolicy } from './paper';
import type { ProbabilityBounds } from './contractTiming';
import { fitMovementMixture, type MovementModel } from './movement';
import type { SnnComparison } from './snnComparison';

export const CONTRACT_STUDY_SCHEMA = 'opportunity-contract-study-v1';
type Component = 'move' | 'pays' | 'both';
const components: Component[] = ['move', 'pays', 'both'];
const probability = (s: ContractScore, k: Component) => k === 'both' ? s.p.both : k === 'move' ? s.p.both + s.p.moveOnly : s.p.both + s.p.paysOnly;
const outcome = (s: ContractScore, k: Component) => k === 'both' ? Number(s.row.outcome.timelyMove && s.row.outcome.sidePays) : Number(k === 'move' ? s.row.outcome.timelyMove : s.row.outcome.sidePays);
const meanLoss = (scores: ContractScore[]) => scores.length ? scores.reduce((s, r) => s + r.weight * r.loss, 0) / scores.reduce((s, r) => s + r.weight, 0) : null;
export interface PairedEvidence { rows: number; weeks: number; gain: ReturnType<typeof bootstrapMeanCi> | null; p: number | null }
function signFlip(gains: number[]): number {
  const random = rng(91), observed = gains.reduce((a, b) => a + b, 0);
  let exceed = 1;
  for (let j = 0; j < 8191; j++) {
    const draw = gains.reduce((a, b) => a + (random() < 0.5 ? b : -b), 0);
    if (draw >= observed - 1e-12) exceed++;
  }
  return exceed / 8192;
}
function realized(s: ContractScore, policy: PaperPolicy): number | null {
  const q = s.row.quote, o = s.row.observation;
  if (!q || !quoteAvailable(q, o, policy.maximumQuoteAgeMs) || q.ask === null || q.askSize < 1) return null;
  const cost = q.ask + q.entryFee + q.slippage + q.settlementFee;
  const enter = probability(s, 'move') >= policy.minimumMoveLowerBound && s.p.both >= policy.minimumJointLowerBound &&
    probability(s, 'pays') - cost >= policy.minimumEntryEdge;
  return enter ? Number(s.row.outcome.sidePays) - cost : 0;
}
/** Paired UTC-week blocks; the same row/event weights and the same fixed execution policy.
 * Bootstrap and sign flips assume reasonably independent/exchangeable week blocks. */
export function pairedContractEvidence(full: ContractScore[], parent: ContractScore[], economicPolicy?: PaperPolicy): PairedEvidence {
  const lookup = new Map(parent.map((s) => [s.key, s])), blocks = new Map<number, { sum: number; weight: number }>();
  let rows = 0;
  for (const s of full) {
    const b = lookup.get(s.key); if (!b) continue;
    const a = economicPolicy ? realized(s, economicPolicy) : s.loss, p = economicPolicy ? realized(b, economicPolicy) : b.loss;
    if (a === null || p === null) continue;
    const gain = economicPolicy ? a - p : p - a, v = blocks.get(s.week) ?? { sum: 0, weight: 0 };
    v.sum += gain * s.weight; v.weight += s.weight; blocks.set(s.week, v); rows++;
  }
  const gains = [...blocks.values()].map((b) => b.sum / b.weight);
  return { rows, weeks: gains.length, gain: gains.length >= 8 ? bootstrapMeanCi(gains, 0.05, 2000, 91) : null,
    p: gains.length >= 8 ? signFlip(gains) : null };
}
export function holmRetained(p: Array<number | null>, alpha = 0.05, registeredParentFamilies = 1) {
  if (!Number.isInteger(registeredParentFamilies) || registeredParentFamilies < 1 || registeredParentFamilies > 64) throw new Error('invalid parent-family trial count');
  const all = [...p, ...new Array(p.length * (registeredParentFamilies - 1)).fill(null)];
  const sorted = all.map((p, index) => ({ p: p ?? 1, index })).sort((a, b) => a.p - b.p), keep = new Set<number>();
  for (let i = 0; i < sorted.length; i++) { if (sorted[i].p > alpha / (sorted.length - i)) break; keep.add(sorted[i].index); }
  return keep;
}
export interface CalibrationBand {
  supportKey: string; component: Component; bin: number; weeks: number; events: number; frequency: number;
  meanForecast: number; radius: number;
}
export interface ContractCalibration {
  modelId: string; knownAt: number; alpha: number; minimumWeeks: number; minimumEvents: number;
  method: 'independent-audit-week-frequency-hoeffding'; bins: CalibrationBand[];
  simultaneousVariants: 2;
  assumption: string;
}
/** These are bands for an audit calibration group's average event frequency, not a
 * guarantee about an individual conditional probability. Beta fits never use this audit. */
export function contractCalibration(model: ContractModel, scores: ContractScore[], knownAt: number): ContractCalibration {
  const buckets = new Map<string, { supportKey: string; component: Component; bin: number; rows: ContractScore[] }>();
  for (const s of scores) for (const k of components) {
    const supportKey = contractSupportKey(s.row.observation, model.included.includes('snn')), bin = Math.min(9, Math.floor(probability(s, k) * 10)), id = `${supportKey}:${k}:${bin}`;
    const b = buckets.get(id) ?? { supportKey, component: k, bin, rows: [] }; b.rows.push(s); buckets.set(id, b);
  }
  const tests = Math.max(1, model.support.length * 30);
  const bins = [...buckets.values()].map((b) => {
    const weeks = new Map<number, { y: number; p: number; weight: number }>();
    for (const s of b.rows) { const w = weeks.get(s.week) ?? { y: 0, p: 0, weight: 0 };
      w.y += s.weight * outcome(s, b.component); w.p += s.weight * probability(s, b.component); w.weight += s.weight; weeks.set(s.week, w); }
    const values = [...weeks.values()];
    return { supportKey: b.supportKey, component: b.component, bin: b.bin, weeks: weeks.size,
      events: new Set(b.rows.map((s) => s.eventKey)).size,
      frequency: values.reduce((s, w) => s + w.y / w.weight, 0) / values.length,
      meanForecast: values.reduce((s, w) => s + w.p / w.weight, 0) / values.length,
      radius: Math.min(1, Math.sqrt(Math.log(2 * tests * 2 / 0.05) / (2 * weeks.size))) };
  });
  return { modelId: model.id, knownAt, alpha: 0.05, minimumWeeks: 8, minimumEvents: 50,
    method: 'independent-audit-week-frequency-hoeffding', simultaneousVariants: 2, bins,
    assumption: 'Independent bounded weekly group frequencies with stable future calibration groups; market drift can invalidate this assumption. Not individual-probability confidence intervals.' };
}
export function contractBounds(cal: ContractCalibration, supportKey: string, component: Component, p: number): { bounds: ProbabilityBounds; supported: boolean } {
  const b = cal.bins.find((b) => b.supportKey === supportKey && b.component === component && b.bin === Math.min(9, Math.floor(p * 10)));
  const supported = !!b && b.weeks >= cal.minimumWeeks && b.events >= cal.minimumEvents;
  return { bounds: { probability: p, lower: supported ? Math.min(p, Math.max(0, b!.frequency - b!.radius)) : 0,
    upper: supported ? Math.max(p, Math.min(1, b!.frequency + b!.radius)) : 1 }, supported };
}
export interface RetentionRecord {
  group: FeatureFamily; fullParentModelId: string; ablatedModelId: string; predictive: PairedEvidence; economic: PairedEvidence;
  decision: 'retained' | 'suppressed' | 'insufficient-evidence'; reason: string;
}
export interface ContractStudy {
  schema: typeof CONTRACT_STUDY_SCHEMA; id: string; researchOnly: true; liveEntryAllowed: false; autoPromote: false;
  status: 'blocked-insufficient-data' | 'research-fit' | 'paper-qualified'; blockers: string[]; plan: ContractStudyPlan; policy: PaperPolicy;
  candidates: Array<{ model: ContractModel; selectionLogLoss: number | null; selectionRows: number }>;
  selected: ContractModel | null; baseline: ContractModel | null; calibration: ContractCalibration | null;
  movement: MovementModel | null;
  snnComparison: SnnComparison | null;
  retention: RetentionRecord[]; audit: { predictive: PairedEvidence; economic: PairedEvidence; rows: number; confirmedResults: number; quoteRows: number } | null;
  selectionRule: string; inputId: string;
}
export function runContractStudy(examples: ContractExample[], plan: ContractStudyPlan, policy: PaperPolicy,
  options: ContractFitOptions & { onProgress?: (message: string) => void } = {}): ContractStudy {
  validateStudyPlan(plan); validatePaperPolicy(policy);
  // Every role is collected separately. No evaluation columns participate in vocabulary or normalization.
  const rows = { train: contractRows(examples, plan.train), stopping: contractRows(examples, plan.stopping),
    calibration: contractRows(examples, plan.calibration), selection: contractRows(examples, plan.selection), audit: contractRows(examples, plan.audit) };
  const core: Omit<ContractStudy, 'id'> = { schema: CONTRACT_STUDY_SCHEMA, researchOnly: true, liveEntryAllowed: false, autoPromote: false,
    status: 'blocked-insufficient-data', blockers: [], plan, policy, candidates: [], selected: null, baseline: null,
    calibration: null, movement: null, snnComparison: null, retention: [], audit: null, inputId: digest(examples),
    selectionRule: 'Selection-window family choice, full-parent leave-one-family-out Holm tests for predictive and fee-net value, then a locked reduced fit and independent audit. Suppressed evidence remains in this ledger.' };
  const finish = () => ({ ...core, id: digest(core) });
  if (Object.values(rows).some((r) => !r.length)) { core.blockers.push('One or more purged roles have no complete official-index examples'); return finish(); }
  const fit = (family: ModelFamily, included: FeatureFamily[]) => fitContractModel(rows, plan, family, included, options);
  const full: FeatureFamily[] = FEATURE_FAMILIES.filter((g) => g !== 'snn' || rows.train[0].observation.snn !== null);
  for (const family of ['smooth', 'trees', 'temporal-linear'] as ModelFamily[]) {
    options.onProgress?.(`Fitting ${family} joint contract candidate`);
    const model = fit(family, full), scores = scoreContractModel(model, rows.selection);
    core.candidates.push({ model, selectionLogLoss: meanLoss(scores), selectionRows: scores.length });
  }
  // Compare on the intersection, never reward a model that refuses harder rows.
  const scored = core.candidates.map((c) => scoreContractModel(c.model, rows.selection));
  const keySets = scored.map((rs) => new Set(rs.map((r) => r.key)));
  const common = new Set(scored[0].map((s) => s.key).filter((key) => keySets.every((set) => set.has(key))));
  for (let i = 0; i < core.candidates.length; i++) {
    core.candidates[i].selectionLogLoss = meanLoss(scored[i].filter((s) => common.has(s.key)));
    core.candidates[i].selectionRows = common.size;
  }
  const winner = [...core.candidates].sort((a, b) => (a.selectionLogLoss ?? Infinity) - (b.selectionLogLoss ?? Infinity))[0];
  if (!common.size || winner.selectionLogLoss === null) { core.blockers.push('No common supported selection examples'); return finish(); }
  const fullScore = scoreContractModel(winner.model, rows.selection);
  for (const group of full) {
    options.onProgress?.(`Ablating ${group} against full ${winner.model.family} parent`);
    const ablated = fit(winner.model.family, full.filter((g) => g !== group)), score = scoreContractModel(ablated, rows.selection);
    core.retention.push({ group, fullParentModelId: winner.model.id, ablatedModelId: ablated.id,
      predictive: pairedContractEvidence(fullScore, score), economic: pairedContractEvidence(fullScore, score, policy),
      decision: 'insufficient-evidence', reason: 'Independent paired blocks and fee-net evidence required; memory retained with zero influence if unsupported' });
    core.candidates.push({ model: ablated, selectionLogLoss: meanLoss(score), selectionRows: score.length });
  }
  // Parent family selection used the same selection window. Count all three possible
  // parents, assigning p=1 to unselected parent tests, rather than treating the winner
  // as if it had been fixed independently. Predictive/economic tests share one family.
  const tests = core.retention.flatMap((r) => [r.predictive.p, r.economic.p]);
  const retained = holmRetained(tests, 0.05, 3);
  core.retention.forEach((r, i) => {
    const supported = retained.has(2 * i) && retained.has(2 * i + 1) && (r.predictive.gain?.lo ?? -Infinity) > 0 && (r.economic.gain?.lo ?? -Infinity) > 0;
    r.decision = supported ? 'retained' : r.predictive.p === null || r.economic.p === null ? 'insufficient-evidence' : 'suppressed';
    if (supported) r.reason = 'Full-parent conditional predictive and fee-net gains survive the joint Holm correction';
  });
  const selectedGroups = core.retention.filter((r) => r.decision === 'retained').map((r) => r.group);
  core.selected = fit(winner.model.family, selectedGroups);
  core.baseline = fit('temporal-linear', []);
  core.movement = fitMovementMixture(rows.train, core.selected.featureNames, core.selected.id, core.selected.included.includes('snn'));
  // Nothing below changes the selected family, features, hyperparameters or beta calibrators.
  const audit = scoreContractModel(core.selected, rows.audit), baseline = scoreContractModel(core.baseline, rows.audit);
  const baselineKeys = new Set(baseline.map((s) => s.key)), paired = audit.filter((s) => baselineKeys.has(s.key));
  core.audit = { predictive: pairedContractEvidence(paired, baseline), economic: pairedContractEvidence(paired, baseline, policy), rows: paired.length,
    confirmedResults: new Set(paired.filter((s) => s.row.outcome.officialResultConfirmed).map((s) => s.eventKey)).size,
    quoteRows: paired.filter((s) => realized(s, policy) !== null).length };
  core.calibration = contractCalibration(core.selected, paired, plan.audit.through);
  core.status = 'research-fit';
  if (core.selected.indexBasis !== 'observed-index') core.blockers.push('Synthetic fixtures are software checks, not observed-market evidence');
  if (core.selected.termsBases.some((b) => b !== 'recorded-contract')) core.blockers.push('Contract terms require recorded venue evidence; declared/computed strikes remain research-only');
  if (Object.values(core.selected.heads).some((h) => !h.calibrationFitted)) core.blockers.push('One or more conditional heads lack independent beta calibration evidence');
  if (core.audit.predictive.weeks < 8 || (core.audit.predictive.gain?.lo ?? -Infinity) <= 0 || (core.audit.predictive.p ?? 1) > 0.025) core.blockers.push('Locked model lacks independent weekly predictive gain');
  if (core.audit.economic.weeks < 8 || (core.audit.economic.gain?.lo ?? -Infinity) <= 0 || (core.audit.economic.p ?? 1) > 0.025) core.blockers.push('Locked model lacks independent weekly fee-net gain under the fixed quote policy');
  if (core.audit.confirmedResults < 50 || core.audit.quoteRows < 100) core.blockers.push('Insufficient confirmed settlement events or executable quote examples');
  if (!core.calibration.bins.some((b) => b.weeks >= 8 && b.events >= 50)) core.blockers.push('No independently audited calibration group has sufficient coverage');
  if (core.selected.included.includes('snn')) core.blockers.push('Retained SNN state requires a same-period S5/S6 versus simpler-baseline comparison');
  if (!core.blockers.length) core.status = 'paper-qualified';
  return finish();
}
