/** Named study registrations. The owner approved the prospective study on 2026-11-08.
 * Reused 2026 development data is never advertised as an unseen final benchmark. */
export const LEGACY_STUDY_ID = 'legacy-pre2025-frozen2026-v1';
export const PROSPECTIVE_STUDY_ID = 'prospective-2026-11-09-v1';
export const ORACLE_BLOCK_STUDY_ID = 'oracle-full-history-2026-11-09-v1';
export interface AtlasStudyPolicy {
  id: string; trainBefore: number; finalFrom: number; authorizedOn: string | null;
  interpretation: string;
}
const policies: Readonly<Record<string, Readonly<AtlasStudyPolicy>>> = Object.freeze({
  [LEGACY_STUDY_ID]: Object.freeze({ id: LEGACY_STUDY_ID, trainBefore: Date.parse('2025-01-01'), finalFrom: Date.parse('2026-01-01'),
    authorizedOn: null, interpretation: 'Original study: pre-2025 fit, 2025 development, frozen 2026 outcomes.' }),
  [PROSPECTIVE_STUDY_ID]: Object.freeze({ id: PROSPECTIVE_STUDY_ID, trainBefore: Date.parse('2026-10-29'), finalFrom: Date.parse('2026-11-09'),
    authorizedOn: '2026-11-08', interpretation: 'Owner-approved separate development study. Earlier 2026 is reused research data; 2026-11-09 onward is a fresh prospective holdout. No live or promotion approval.' }),
  [ORACLE_BLOCK_STUDY_ID]: Object.freeze({ id: ORACLE_BLOCK_STUDY_ID, trainBefore: Date.parse('2026-11-08T23:00:00Z'), finalFrom: Date.parse('2026-11-09'),
    authorizedOn: '2026-11-09', interpretation: 'Owner-requested all-minute Oracle-first block study. Earlier history is reused development; quarterly walk-forward predictions use only earlier resolved blocks. A one-hour embargo precedes the unchanged November 9 prospective holdout. No live or promotion approval.' }),
});
export function studyPolicy(id = LEGACY_STUDY_ID): Readonly<AtlasStudyPolicy> {
  const policy = policies[id]; if (!policy) throw new Error('unknown or unregistered Atlas study policy'); return policy;
}
