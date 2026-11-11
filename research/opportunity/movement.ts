/** Continuous conditional empirical price-path distribution from training observations only. */
import { fitNormalization, type Normalization } from '../mlp';
import { rng } from '../stats';
import { digest } from './contractDataset';
import { contractSupportKey, type EncodedContractRow } from './contractLearner';

export interface MovementModel {
  schema: 'opportunity-movement-mixture-v1'; id: string; parentModelId: string; featureNames: string[];
  norm: Normalization; bandwidth: 1;
  prototypes: Array<{ supportKey: string; x: number[]; weight: number; terminalBps: number; mfeBps: number; maeBps: number }>;
  interpretation: string;
}
export function fitMovementMixture(rows: EncodedContractRow[], names: string[], parentModelId: string, withSnn = false): MovementModel | null {
  const eligible = rows.filter((r) => [r.outcome.terminalMoveBps, r.outcome.mfeBps, r.outcome.maeBps].every((v) => v !== null && Number.isFinite(v)));
  if (eligible.length < 20) return null;
  // Deterministic uniform reservoir, with original event weights. No stopping/audit outcomes.
  const cap = Math.min(2048, Math.max(1, Math.floor(2000000 / names.length))), random = rng(113), sample = eligible.slice(0, cap);
  for (let i = cap; i < eligible.length; i++) { const j = Math.floor(random() * (i + 1)); if (j < cap) sample[j] = eligible[i]; }
  const X = eligible.map((r) => names.map((n) => r.values[n] ?? NaN)), norm = fitNormalization(X);
  const z = (x: number[]) => x.map((v, i) => Number.isFinite(v) ? Math.max(-5, Math.min(5, (v - norm.mean[i]) / norm.std[i])) : 0);
  const core: Omit<MovementModel, 'id'> = { schema: 'opportunity-movement-mixture-v1', parentModelId, featureNames: [...names], norm, bandwidth: 1,
    prototypes: sample.map((r) => ({ supportKey: contractSupportKey(r.observation, withSnn), x: z(names.map((n) => r.values[n] ?? NaN)), weight: r.weight,
      terminalBps: r.outcome.terminalMoveBps!, mfeBps: r.outcome.mfeBps!, maeBps: r.outcome.maeBps! })),
    interpretation: 'Gaussian similarity weights over training-only standardized state and exact contract support. Empirical conditional mixture; quantiles describe path dispersion, not probability confidence or an independently calibrated movement model.' };
  return { ...core, id: digest(core) };
}
export function predictMovementMixture(m: MovementModel, values: Record<string, number>, supportKey: string) {
  const x = m.featureNames.map((n, i) => Number.isFinite(values[n]) ? Math.max(-5, Math.min(5, (values[n] - m.norm.mean[i]) / m.norm.std[i])) : 0);
  const matching = m.prototypes.filter((p) => p.supportKey === supportKey).map((p) => ({ ...p,
    w: p.weight * Math.exp(-p.x.reduce((s, v, i) => s + (v - x[i]) ** 2, 0) / Math.max(1, 2 * x.length)) }));
  const weight = matching.reduce((s, p) => s + p.w, 0);
  if (matching.length < 10 || weight < 1e-12) return null;
  const mean = (key: 'terminalBps' | 'mfeBps' | 'maeBps') => matching.reduce((s, p) => s + p.w * p[key], 0) / weight;
  const quantile = (q: number) => {
    const sorted = [...matching].sort((a, b) => a.terminalBps - b.terminalBps); let cumulative = 0;
    for (const p of sorted) { cumulative += p.w; if (cumulative >= q * weight) return p.terminalBps; } return sorted.at(-1)!.terminalBps;
  };
  return { modelId: m.id, basis: 'conditional-training-mixture' as const, calibrationRef: null,
    expectedTerminalBps: mean('terminalBps'), expectedFavorableBps: mean('mfeBps'), expectedAdverseBps: mean('maeBps'),
    terminalQuantilesBps: { p10: quantile(0.1), p50: quantile(0.5), p90: quantile(0.9) },
    prototypes: matching.length, effectivePrototypeCount: weight ** 2 / matching.reduce((s, p) => s + p.w ** 2, 0),
    interpretation: m.interpretation };
}
export function validateMovementModel(m: MovementModel) {
  const { id, ...core } = m;
  if (m.schema !== 'opportunity-movement-mixture-v1' || id !== digest(core) || m.bandwidth !== 1 ||
      !m.featureNames.length || m.norm.mean.length !== m.featureNames.length || m.norm.std.length !== m.featureNames.length ||
      m.norm.mean.some((v) => !Number.isFinite(v)) || m.norm.std.some((v) => !Number.isFinite(v) || v <= 0) || m.prototypes.length > 2048 ||
      m.prototypes.some((p) => p.x.length !== m.featureNames.length || p.x.some((v) => !Number.isFinite(v)) ||
        ![p.weight, p.terminalBps, p.mfeBps, p.maeBps].every(Number.isFinite) || p.weight <= 0 || p.mfeBps < 0 || p.maeBps > 0)) throw new Error('invalid conditional movement mixture');
}
