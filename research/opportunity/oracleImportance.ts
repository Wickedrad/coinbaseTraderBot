/** Learn predictive importance independently of each curve's evidence/support mass. */
import { ORACLE_EMBARGO_MS, ORACLE_HORIZONS, ORACLE_HORIZON_SIZE, ORACLE_KNOTS, ORACLE_STATS, ORACLE_SURFACES,
  type OracleCoordinates, type OracleMatrix } from './oracleMatrix';

export const IMPORTANCE_POLICY = Object.freeze({ shrinkage: 100, decay: 0.75, learningRate: 50, maximumLogWeight: 5, minimumEarlierPredictions: 100,
  meaning: 'Update from complete earlier-quarter predictions only; freeze all mixture weights before the next quarter' });
export const IMPORTANCE_EXPERTS = ['historical-class-prior', ...ORACLE_SURFACES.map((s) => s.name)];
/** Caller-owned scratch buffer; unavailable curves are NaN, not zero-probability experts. */
export function oracleComponents(m: OracleMatrix, horizon: 15 | 60, c: OracleCoordinates, asOf: number,
  out = new Float64Array(IMPORTANCE_EXPERTS.length * 3)) {
  if (out.length !== IMPORTANCE_EXPERTS.length * 3 || m.trainedThrough + ORACLE_EMBARGO_MS > asOf || !(ORACLE_HORIZONS as readonly number[]).includes(horizon)) throw new Error('importance component size or temporal boundary differs');
  const d = m.data, base = ORACLE_HORIZONS.indexOf(horizon) * ORACLE_HORIZON_SIZE, n = d[base];
  const prior = [(d[base + 1] + 0.5) / (n + 1.5), (d[base + 2] + 0.5) / (n + 1.5), (n - d[base + 1] - d[base + 2] + 0.5) / (n + 1.5)];
  out.fill(NaN); out.set(prior);
  const { lo, hi, fraction: t } = c, S = ORACLE_STATS.length, K = ORACLE_KNOTS;
  for (let j = 0; j < ORACLE_SURFACES.length; j++) {
    const s = ORACLE_SURFACES[j], a = s.a, b = s.b; if (lo[a] < 0 || (b !== null && lo[b] < 0)) continue;
    let mass = 0, up = 0, flat = 0;
    const read = (cell: number, weight: number) => { const off = base + s.offset + cell * S; mass += weight * d[off]; up += weight * d[off + 1]; flat += weight * d[off + 2]; };
    if (b === null) { read(lo[a], 1 - t[a]); read(hi[a], t[a]); }
    else { read(lo[a] * K + lo[b], (1 - t[a]) * (1 - t[b])); read(lo[a] * K + hi[b], (1 - t[a]) * t[b]);
      read(hi[a] * K + lo[b], t[a] * (1 - t[b])); read(hi[a] * K + hi[b], t[a] * t[b]); }
    const off = (j + 1) * 3, shrink = IMPORTANCE_POLICY.shrinkage, total = mass + shrink;
    out[off] = (up + shrink * prior[0]) / total; out[off + 1] = (flat + shrink * prior[1]) / total;
    out[off + 2] = (Math.max(0, mass - up - flat) + shrink * prior[2]) / total;
  }
  return out;
}
export function importanceMixture(components: Float64Array, logWeights: readonly number[]) {
  if (components.length !== IMPORTANCE_EXPERTS.length * 3 || logWeights.length !== IMPORTANCE_EXPERTS.length || logWeights.some((w) => !Number.isFinite(w) || Math.abs(w) > 5)) throw new Error('invalid importance vector');
  const p = [0, 0, 0]; let total = 0;
  for (let i = 0; i < logWeights.length; i++) {
    const off = i * 3; if (!Number.isFinite(components[off])) continue;
    const w = Math.exp(logWeights[i]); total += w;
    for (let k = 0; k < 3; k++) p[k] += w * components[off + k];
  }
  if (!(total > 0)) throw new Error('no finite importance experts'); return p.map((v) => v / total);
}
export class OracleImportance {
  readonly logWeights = IMPORTANCE_EXPERTS.map(() => 0);
  private counts = new Float64Array(IMPORTANCE_EXPERTS.length);
  private losses = new Float64Array(IMPORTANCE_EXPERTS.length);
  private priorLosses = new Float64Array(IMPORTANCE_EXPERTS.length);
  trainedThrough = 0;
  weightsTrainedThrough = 0;
  observe(components: Float64Array, category: number, knownAt: number) {
    if (components.length !== IMPORTANCE_EXPERTS.length * 3 || ![0, 1, 2].includes(category) || !Number.isSafeInteger(knownAt) || knownAt < this.trainedThrough) throw new Error('invalid importance label or order');
    const priorLoss = -Math.log(Math.max(1e-12, components[category]));
    for (let i = 1; i < this.counts.length; i++) if (Number.isFinite(components[i * 3 + category])) {
      this.counts[i]++; this.losses[i] -= Math.log(Math.max(1e-12, components[i * 3 + category])); this.priorLosses[i] += priorLoss;
    }
    this.trainedThrough = knownAt;
  }
  /** The quarter must be complete before it can alter a later quarter's weights. */
  closeQuarter(nextFrom: number) {
    if (this.trainedThrough + ORACLE_EMBARGO_MS > nextFrom) throw new Error('importance labels have not completed the embargo before next quarter');
    const evidence = IMPORTANCE_EXPERTS.map((name, i) => {
      const gain = this.counts[i] ? (this.priorLosses[i] - this.losses[i]) / this.counts[i] : null;
      if (i > 0 && this.counts[i] >= IMPORTANCE_POLICY.minimumEarlierPredictions) this.logWeights[i] = Math.max(-5, Math.min(5,
        IMPORTANCE_POLICY.decay * this.logWeights[i] + IMPORTANCE_POLICY.learningRate * gain!));
      return { name, predictions: this.counts[i], gain, logWeight: this.logWeights[i] };
    });
    this.weightsTrainedThrough = this.trainedThrough;
    this.counts.fill(0); this.losses.fill(0); this.priorLosses.fill(0); return evidence;
  }
}
