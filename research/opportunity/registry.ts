/** Content-addressed offline/paper registry. Loading an artifact never promotes a bot model. */
import { digest, encodeContractObservation, type ContractObservation } from './contractDataset';
import { contractModelSupports, contractProbabilities, contractSupportKey, missingRequiredInputs, validateContractModel, validateStudyPlan } from './contractLearner';
import { CONTRACT_STUDY_SCHEMA, contractBounds, type ContractStudy } from './contractStudy';
import type { ContractPathForecast } from './contractTiming';
import { predictMovementMixture, validateMovementModel } from './movement';
import { studyPolicy } from './studyPolicy';

export const ATLAS_PRODUCT_SCHEMA = 'opportunity-paper-product-v1';
export interface AtlasProduct {
  schema: typeof ATLAS_PRODUCT_SCHEMA; id: string; createdAt: number;
  researchOnly: true; liveEntryAllowed: false; autoPromote: false;
  codeHashes: Record<string, string>; inputHashes: Record<string, string>; study: ContractStudy;
}
export function createAtlasProduct(study: ContractStudy, codeHashes: Record<string, string>, inputHashes: Record<string, string>, createdAt = Date.now()): AtlasProduct {
  const core: Omit<AtlasProduct, 'id'> = { schema: ATLAS_PRODUCT_SCHEMA, createdAt, researchOnly: true, liveEntryAllowed: false,
    autoPromote: false, study, codeHashes, inputHashes };
  const p = { ...core, id: digest(core) }; validateAtlasProduct(p); return p;
}
export function validateAtlasProduct(p: AtlasProduct) {
  const { id, ...core } = p, s = p.study, { id: studyId, ...studyCore } = s;
  if (p.schema !== ATLAS_PRODUCT_SCHEMA || digest(core) !== id || p.researchOnly !== true || p.liveEntryAllowed !== false || p.autoPromote !== false ||
      !Number.isSafeInteger(p.createdAt) || p.createdAt < 0 || s.schema !== CONTRACT_STUDY_SCHEMA || digest(studyCore) !== studyId ||
      s.researchOnly !== true || s.liveEntryAllowed !== false || s.autoPromote !== false ||
      Object.values({ ...p.codeHashes, ...p.inputHashes }).some((h) => !/^[a-f0-9]{64}$/.test(h))) throw new Error('invalid Atlas product or study content ID');
  validateStudyPlan(s.plan);
  if (!['blocked-insufficient-data', 'research-fit', 'paper-qualified'].includes(s.status) || (s.status !== 'blocked-insufficient-data' && (!s.selected || !s.calibration || !s.audit))) throw new Error('incomplete or invalid study status');
  for (const model of [...s.candidates.map((c) => c.model), ...[s.selected, s.baseline].filter((m) => m !== null)]) {
    validateContractModel(model);
    if (studyPolicy(model.studyPolicyId).id !== studyPolicy(s.plan.studyPolicyId).id ||
        model.trainedThrough !== s.plan.train.through || model.knownAt !== s.plan.calibration.through) throw new Error('model/study partition registration or fitting dates differ');
  }
  if (s.selected && s.selected.included.some((g) => !s.retention.some((r) => r.group === g && r.decision === 'retained'))) throw new Error('selected input lacks retention evidence');
  if (s.movement) { validateMovementModel(s.movement); if (s.movement.parentModelId !== s.selected?.id ||
    digest(s.movement.featureNames) !== digest(s.selected.featureNames)) throw new Error('movement parent or selected inputs differ'); }
  if (s.selected?.included.includes('snn') && s.status === 'paper-qualified') {
    if (!(s.selected.snnPriceAgeLimitMs! > 0 && s.selected.snnPriceAgeLimitMs! <= 3000)) throw new Error('SNN observed-price freshness qualification absent');
    const e = s.snnComparison, variant = e?.recommended;
    if (!e || !variant || variant === 'none' || e.modelIds[variant] !== s.selected.id || e.knownAt !== s.plan.audit.through) throw new Error('SNN same-period qualification absent');
    const { id: evidenceId, ...evidenceCore } = e;
    if (digest(evidenceCore) !== evidenceId) throw new Error('invalid SNN comparison content ID');
  }
  if (s.calibration) {
    const c = s.calibration;
    if (c.modelId !== s.selected?.id || c.knownAt !== s.plan.audit.through || c.alpha !== 0.05 || c.simultaneousVariants !== 2 ||
        c.method !== 'independent-audit-week-frequency-hoeffding' || c.minimumWeeks < 8 || c.minimumEvents < 50 ||
        c.bins.some((b) => ![b.frequency, b.meanForecast, b.radius].every(Number.isFinite) || b.frequency < 0 || b.frequency > 1 ||
          b.meanForecast < 0 || b.meanForecast > 1 || b.radius < 0 || b.radius > 1 || !Number.isInteger(b.bin) || b.bin < 0 || b.bin > 9 ||
          !Number.isInteger(b.weeks) || b.weeks < 1 || !Number.isInteger(b.events) || b.events < 1)) throw new Error('invalid independent calibration evidence');
  }
  if (s.status === 'paper-qualified' && (s.blockers.length || !s.selected || !s.baseline || !s.calibration || !s.audit ||
      s.selected.indexBasis !== 'observed-index' || s.selected.termsBases.some((b) => b !== 'recorded-contract') || Object.values(s.selected.heads).some((h) => !h.calibrationFitted) ||
      s.audit.rows < 100 || s.audit.confirmedResults < 50 || s.audit.quoteRows < 100 ||
      s.audit.predictive.weeks < 8 || s.audit.economic.weeks < 8 ||
      (s.audit.predictive.gain?.lo ?? -Infinity) <= 0 || (s.audit.economic.gain?.lo ?? -Infinity) <= 0 ||
      (s.audit.predictive.p ?? 1) > 0.025 || (s.audit.economic.p ?? 1) > 0.025)) throw new Error('unsubstantiated paper qualification');
}
export interface AtlasQueryResult {
  schema: typeof ATLAS_PRODUCT_SCHEMA; productId: string; researchOnly: true; liveEntryAllowed: false;
  status: 'unavailable' | 'unsupported' | 'unqualified' | 'expired' | 'paper-supported'; reason: string;
  forecast: ContractPathForecast | null; blockers: string[];
  movement: ReturnType<typeof predictMovementMixture>;
  uncertaintyBasis: string;
}
export class AtlasRegistry {
  private readonly products = new Map<string, AtlasProduct>();
  register(p: AtlasProduct) { validateAtlasProduct(p); this.products.set(p.id, structuredClone(p)); return p.id; }
  status() {
    return [...this.products.values()].map((p) => ({ productId: p.id, modelId: p.study.selected?.id ?? null, createdAt: p.createdAt,
      status: p.study.status, blockers: p.study.blockers, groups: p.study.selected?.included ?? [],
      liveEntryAllowed: false, autoPromote: false }));
  }
  /** The caller names ONE locked product; probability cannot choose the winning model. */
  query(productId: string, observation: ContractObservation, options: { maximumCalibrationAgeMs: number; mode?: 'forward-paper' | 'historical-audit' }): AtlasQueryResult {
    if (!Number.isSafeInteger(options.maximumCalibrationAgeMs) || options.maximumCalibrationAgeMs <= 0) throw new Error('explicit calibration freshness policy required');
    const out: AtlasQueryResult = { schema: ATLAS_PRODUCT_SCHEMA, productId, researchOnly: true, liveEntryAllowed: false, status: 'unavailable',
      reason: 'registered fitted product unavailable', forecast: null, movement: null, blockers: [],
      uncertaintyBasis: 'Independent audit calibration-group frequency bands under a stable, independent-week assumption; not individual conditional-probability confidence intervals.' };
    const p = this.products.get(productId), s = p?.study, model = s?.selected;
    if (!p || !s || !model) return out;
    out.blockers = [...s.blockers];
    const x = encodeContractObservation(observation), q = observation.query;
    const availableAt = options.mode === 'historical-audit' ? s.plan.audit.through : Math.max(p.createdAt, s.plan.audit.through);
    if (q.asOf < availableAt) return { ...out, reason: 'product was not available at this query time' };
    if (!contractModelSupports(model, observation)) return { ...out, status: 'unsupported', reason: 'asset, terms, index, timing, feature/SNN identity or training geometry coverage differs' };
    if (missingRequiredInputs(model, x).length) return { ...out, status: 'unsupported', reason: 'a selected input is missing in a pattern never observed in training; confidence cannot be inferred by mean imputation' };
    const joint = contractProbabilities(model, x), probs = { move: joint.moveOnly + joint.both, pays: joint.paysOnly + joint.both, both: joint.both };
    const supportKey = contractSupportKey(observation, model.included.includes('snn'));
    const cal = s.calibration, bounds = (k: 'move' | 'pays' | 'both') => cal ? contractBounds(cal, supportKey, k, probs[k]) :
      { supported: false, bounds: { probability: probs[k], lower: 0, upper: 1 } };
    const move = bounds('move'), pays = bounds('pays'), both = bounds('both');
    const expired = !cal || q.asOf - cal.knownAt > options.maximumCalibrationAgeMs;
    const qualified = s.status === 'paper-qualified' && !expired && move.supported && pays.supported && both.supported;
    let featuresKnownAt = Math.max(q.featuresKnownAt, observation.index.knownAt, q.contract.termsKnownAt);
    if (observation.snn) featuresKnownAt = Math.max(featuresKnownAt, observation.snn.provenance.inputKnownAt,
      observation.snn.provenance.checkpointKnownAt, observation.snn.provenance.trainedThrough);
    const forecast: ContractPathForecast = { kind: 'contract-path', id: digest([p.id, observation.id]), modelId: model.id,
      asset: q.asset, asOf: q.asOf, featuresKnownAt, direction: q.direction, eventDefinitionId: q.eventDefinitionId, byAt: q.effectBy,
      contract: structuredClone(q.contract), side: q.side, settlementBasis: 'official-index-average',
      calibrationRef: qualified ? digest(cal) : null, moveBy: move.bounds, sidePays: pays.bounds, timelyMoveAndSidePays: both.bounds };
    return { ...out, forecast, movement: s.movement ? predictMovementMixture(s.movement, x, supportKey) : null,
      status: expired ? 'expired' : qualified ? 'paper-supported' : 'unqualified',
      reason: expired ? 'independent calibration is missing or older than the caller policy' : qualified ? 'exact contract supported for paper evaluation' : 'research forecast only; qualification or this calibration group is incomplete' };
  }
}
