/** Same-period S5/S6 comparison. Audit labels never select a new feature/model fit. */
import { digest } from './contractDataset';
import { contractRows, scoreContractModel, type ContractExample, type ContractScore } from './contractLearner';
import { holmRetained, pairedContractEvidence, type ContractStudy, type PairedEvidence } from './contractStudy';

export interface SnnComparison {
  schema: 'opportunity-snn-comparison-v1'; id: string; studyIds: { S5: string; S6: string };
  modelIds: { S5: string; S6: string }; inputIds: { S5: string; S6: string };
  recommended: 'S5' | 'S6' | 'none'; rows: number;
  tests: Array<{ contrast: 'S5-vs-simple' | 'S6-vs-simple' | 'S6-vs-S5'; predictive: PairedEvidence; economic: PairedEvidence; accepted: boolean }>;
  knownAt: number; researchOnly: true; liveEntryAllowed: false;
}
/** Identity excludes the SNN state, while requiring the very same query, base frame,
 * official index source, costs/quotes and resulting observed path. */
function align(scores: ContractScore[]) {
  return scores.map((s) => ({ ...s, key: digest([s.row.observation.query, s.row.observation.frame, s.row.observation.event, s.row.observation.index,
    s.row.quote ?? null, { ...s.row.outcome, observationId: '' }]) }));
}
export function compareSnnStudies(s5: ContractStudy, data5: ContractExample[], s6: ContractStudy, data6: ContractExample[]): SnnComparison {
  if (digest(s5.plan) !== digest(s6.plan) || digest(s5.policy) !== digest(s6.policy) || !s5.selected || !s6.selected || !s5.baseline || !s6.baseline ||
      s5.inputId !== digest(data5) || s6.inputId !== digest(data6) ||
      data5.some((r) => r.observation.snn?.provenance.variant !== 'S5') || data6.some((r) => r.observation.snn?.provenance.variant !== 'S6')) throw new Error('SNN comparison requires two locked same-period variant studies and matching datasets');
  const rows5 = contractRows(data5, s5.plan.audit, s5.plan.studyPolicyId), rows6 = contractRows(data6, s6.plan.audit, s6.plan.studyPolicyId);
  const a = align(scoreContractModel(s5.selected, rows5)), b = align(scoreContractModel(s6.selected, rows6));
  const simple5 = align(scoreContractModel(s5.baseline, rows5)), simple6 = align(scoreContractModel(s6.baseline, rows6));
  const sets = [a, b, simple5, simple6].map((rs) => new Set(rs.map((s) => s.key))), common = new Set(a.map((s) => s.key).filter((key) => sets.every((set) => set.has(key))));
  const commonRows = (rs: ContractScore[]) => rs.filter((s) => common.has(s.key));
  const tests = ([['S5-vs-simple', a, simple5], ['S6-vs-simple', b, simple6], ['S6-vs-S5', b, a]] as const).map(([contrast, full, parent]) => ({
    contrast, predictive: pairedContractEvidence(commonRows(full), commonRows(parent)),
    economic: pairedContractEvidence(commonRows(full), commonRows(parent), s5.policy), accepted: false }));
  const keep = holmRetained(tests.flatMap((t) => [t.predictive.p, t.economic.p]));
  tests.forEach((t, i) => { t.accepted = keep.has(2 * i) && keep.has(2 * i + 1) && (t.predictive.gain?.lo ?? -Infinity) > 0 && (t.economic.gain?.lo ?? -Infinity) > 0; });
  const recommended = s6.selected.included.includes('snn') && tests[1].accepted && tests[2].accepted ? 'S6'
    : s5.selected.included.includes('snn') && tests[0].accepted ? 'S5' : 'none';
  const core: Omit<SnnComparison, 'id'> = { schema: 'opportunity-snn-comparison-v1', studyIds: { S5: s5.id, S6: s6.id },
    modelIds: { S5: s5.selected.id, S6: s6.selected.id }, inputIds: { S5: s5.inputId, S6: s6.inputId }, recommended, rows: common.size,
    tests, knownAt: s5.plan.audit.through, researchOnly: true, liveEntryAllowed: false };
  return { ...core, id: digest(core) };
}
export const SNN_COMPARISON_BLOCKER = 'Retained SNN state requires a same-period S5/S6 versus simpler-baseline comparison';
export function qualifySnnStudy(study: ContractStudy, evidence: SnnComparison): ContractStudy {
  const { id, ...core } = evidence;
  const variant = evidence.recommended;
  if (digest(core) !== id || evidence.schema !== 'opportunity-snn-comparison-v1' || variant === 'none' ||
      evidence.modelIds[variant] !== study.selected?.id || evidence.studyIds[variant] !== study.id ||
      evidence.knownAt !== study.plan.audit.through || !study.selected.included.includes('snn')) throw new Error('SNN evidence does not qualify this locked study');
  const { id: oldId, ...updated } = structuredClone(study);
  updated.snnComparison = evidence;
  updated.blockers = updated.blockers.filter((b) => b !== SNN_COMPARISON_BLOCKER);
  updated.status = updated.blockers.length ? 'research-fit' : 'paper-qualified';
  return { ...updated, id: digest(updated) };
}
