/** Read-only audit of the actual saved response surfaces, not a relationship-edge claim. */
import fs from 'node:fs';
import path from 'node:path';
import { gunzipSync } from 'node:zlib';
import { ORACLE_AXES, ORACLE_SURFACES, ORACLE_HORIZONS, ORACLE_LAYOUT_ID, ORACLE_SCHEMA, ORACLE_KNOTS,
  ORACLE_HORIZON_SIZE, ORACLE_STATS, OracleMatrix, oracleCoordinates, oracleRawCoordinate, type OracleSurface } from './oracleMatrix';
import { digest } from './contractDataset';
import { sha256File } from './jointPathData';
import { atomicDirectory } from './productCli';

const S = ORACLE_STATS.length, K = ORACLE_KNOTS;
const cyclic = (j: number) => ['day', 'week'].includes(ORACLE_AXES[j].transform);
function coordinate(j: number, x: number) {
  const z = (cyclic(j) ? ((x % 1) + 1) % 1 : Math.max(0, Math.min(1, x))) * (K - 1);
  const lo = Math.floor(z), hi = cyclic(j) ? (lo + 1) % (K - 1) : Math.min(K - 1, lo + 1);
  return { lo, hi, t: z - lo };
}
/** Independent reconstruction of one curve's current interpolated estimate. */
export function surfaceEstimate(m: OracleMatrix, h: 15 | 60, s: OracleSurface, x: number, y = 0.5, strength = 100) {
  const base = ORACLE_HORIZONS.indexOf(h) * ORACLE_HORIZON_SIZE, a = coordinate(s.a, x), b = s.b === null ? null : coordinate(s.b, y);
  const g = m.data, n = g[base], prior = [(g[base + 1] + 0.5) / (n + 1.5), (g[base + 2] + 0.5) / (n + 1.5), (n - g[base + 1] - g[base + 2] + 0.5) / (n + 1.5)];
  let mass = 0, up = 0, flat = 0;
  const add = (cell: number, w: number) => { const i = base + s.offset + cell * S; mass += g[i] * w; up += g[i + 1] * w; flat += g[i + 2] * w; };
  if (!b) { add(a.lo, 1 - a.t); add(a.hi, a.t); }
  else { add(a.lo * K + b.lo, (1 - a.t) * (1 - b.t)); add(a.lo * K + b.hi, (1 - a.t) * b.t); add(a.hi * K + b.lo, a.t * (1 - b.t)); add(a.hi * K + b.hi, a.t * b.t); }
  return { evidenceWeight: mass, probabilities: [(up + strength * prior[0]) / (mass + strength), (flat + strength * prior[1]) / (mass + strength),
    (Math.max(0, mass - up - flat) + strength * prior[2]) / (mass + strength)] };
}
export function auditSpectrumMatrix(m: OracleMatrix) {
  const curves = [];
  for (const h of ORACLE_HORIZONS) for (const s of ORACLE_SURFACES) {
    const base = ORACLE_HORIZONS.indexOf(h) * ORACLE_HORIZON_SIZE;
    let mass = 0, occupied = 0, supported = 0, directionalHighCells = 0, min = [1, 1, 1], max = [0, 0, 0], maxContinuityJump = 0;
    for (let cell = 0; cell < s.cells; cell++) {
      const i = base + s.offset + cell * S, n = m.data[i];
      if (n < -1e-7 || m.data[i + 1] < -1e-7 || m.data[i + 2] < -1e-7 || m.data[i + 1] + m.data[i + 2] > n + 1e-6) throw new Error('invalid weighted class evidence');
      mass += n; if (n <= 1e-9) continue; occupied++; if (n >= 100) supported++;
      const x = (s.b === null ? cell : Math.floor(cell / K)) / (K - 1), y = s.b === null ? 0.5 : (cell % K) / (K - 1);
      const p = surfaceEstimate(m, h, s, x, y).probabilities;
      p.forEach((v, j) => { if (!Number.isFinite(v) || v < -1e-9 || v > 1 + 1e-9) throw new Error('invalid spectrum probability'); min[j] = Math.min(min[j], v); max[j] = Math.max(max[j], v); });
      if (n >= 100 && Math.max(p[0], p[2]) >= 0.6) directionalHighCells++;
    }
    if (mass > m.rows(h) + Math.max(1e-5, m.rows(h) * 1e-10)) throw new Error('a relationship contains more evidence than all input answers');
    for (const axis of s.b === null ? [0] : [0, 1]) for (const other of [0.2, 0.5, 0.8]) {
      const j = axis === 0 ? s.a : s.b!;
      for (let knot = cyclic(j) ? 0 : 1; knot < K - 1; knot++) {
        const center = knot / (K - 1), diff = (eps: number) => {
          const a = surfaceEstimate(m, h, s, axis === 0 ? center - eps : other, axis === 0 ? other : center - eps).probabilities;
          const b = surfaceEstimate(m, h, s, axis === 0 ? center + eps : other, axis === 0 ? other : center + eps).probabilities;
          return Math.max(...a.map((v, k) => Math.abs(v - b[k])));
        };
        const coarse = diff(1e-6), fine = diff(1e-8); maxContinuityJump = Math.max(maxContinuityJump, fine);
        if (fine > coarse * 0.1 + 1e-9) throw new Error('spectrum fails the shrinking-distance continuity check');
      }
    }
    curves.push({ horizonMinutes: h, relationship: s.name, dimensions: s.b === null ? 1 : 2, cells: s.cells, occupiedCells: occupied,
      cellsWithAtLeast100EffectiveObservations: supported, evidenceWeight: mass, proportionOfAllAnswers: m.rows(h) ? mass / m.rows(h) : 0,
      probabilityRanges: occupied ? { up: [min[0], max[0]], sideways: [min[1], max[1]], down: [min[2], max[2]] } : null,
      supportedCellsWithDirectionalPointProbabilityAtLeastPointSix: directionalHighCells,
      maximumSmallDistanceProbabilityChange: maxContinuityJump, continuousInterpolationVerified: true, learnedImportanceWeight: null });
  }
  // Reconstruct the full ensemble independently at a mixed, non-knot point.
  const points = ORACLE_AXES.map((_, j) => 0.25 + (j % 7) * 0.07);
  const raw = points.map((x, j) => oracleRawCoordinate(x, ORACLE_AXES[j]));
  for (const h of ORACLE_HORIZONS) {
    const actual = m.predict(h, oracleCoordinates(raw), m.trainedThrough + 3600000);
    const p = [...actual.baseline];
    for (const s of ORACLE_SURFACES) surfaceEstimate(m, h, s, points[s.a], s.b === null ? 0.5 : points[s.b]).probabilities.forEach((v, j) => p[j] += v);
    const sum = p.reduce((a, b) => a + b, 0);
    if (p.some((v, j) => Math.abs(v / sum - actual.p[j]) > 1e-10)) throw new Error('stored ensemble differs from its weighted surfaces');
  }
  return { registeredRelationships: ORACLE_SURFACES.length, curves, totalCurves: curves.length,
    evidenceWeightedStorage: true, continuousInterpolation: true, learnedRelationshipImportance: false,
    currentImportance: 'Equal weight for each available curve plus one historical prior, after each curve is shrunk by 100 effective observations',
    nominalCurveWeightWithAllInputs: 1 / (ORACLE_SURFACES.length + 1), target: 'Terminal return up/sideways/down; not a sustained-movement or profit label',
    interpret: 'A stored varying curve demonstrates a descriptive spectrum. Predictive usefulness and learned importance require a separate past-only study; effective counts are correlated minute evidence, not independent samples.' };
}
export async function auditSavedSpectra(root: string, out: string) {
  return atomicDirectory(out, async (dir) => {
    const assets = [];
    for (const asset of ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE']) {
      const base = path.join(root, `atlas-oracle-result-${asset}`, 'walk'), modelFile = path.join(base, 'model.json');
      const model = JSON.parse(fs.readFileSync(modelFile, 'utf8')), { id, ...identity } = model;
      if (digest(identity) !== id || model.schema !== ORACLE_SCHEMA || model.layoutId !== ORACLE_LAYOUT_ID || model.asset !== asset || model.file !== 'full-history-model.f64.gz') throw new Error('spectrum model metadata differs');
      const file = path.join(base, model.file), data = new Float64Array(ORACLE_HORIZON_SIZE * 2);
      if (await sha256File(file) !== model.sha256) throw new Error('spectrum model bytes differ');
      const bytes = gunzipSync(fs.readFileSync(file), { maxOutputLength: data.byteLength });
      if (bytes.length !== data.byteLength) throw new Error('spectrum matrix layout differs'); Buffer.from(data.buffer).set(bytes);
      const m = new OracleMatrix(data); m.trainedThrough = model.trainedThrough;
      const audit = auditSpectrumMatrix(m), result = { asset, modelId: id, modelSha256: model.sha256, ...audit };
      fs.writeFileSync(path.join(dir, `${asset}-spectrum.json`), JSON.stringify(result, null, 2) + '\n');
      assets.push({ asset, modelId: id, curves: audit.totalCurves, populatedCurves: audit.curves.filter((c) => c.occupiedCells > 0).length,
        supportedDirectionalHighCells: audit.curves.reduce((sum, c) => sum + c.supportedCellsWithDirectionalPointProbabilityAtLeastPointSix, 0),
        continuous: true, importanceWeightsLearned: false });
    }
    fs.copyFileSync(new URL('./spectrumViewer.html', import.meta.url), path.join(dir, 'spectrum-viewer.html'));
    const report = { schema: 'opportunity-spectrum-audit-v1', assets, registeredRelationshipsPerAsset: ORACLE_SURFACES.length,
      curvesAudited: assets.reduce((n, a) => n + a.curves, 0), continuumVerified: true, learnedImportanceVerified: false,
      researchOnly: true, liveEntryAllowed: false, interpretation: 'Continuous evidence-weighted spectra exist. Their predictor still uses uniform curve importance; no predictive edge or profit is asserted by this audit.' };
    fs.writeFileSync(path.join(dir, 'report.json'), JSON.stringify(report, null, 2) + '\n'); return report;
  });
}
if (process.argv[1] && /(^|[/\\])spectrumAudit\.(ts|js)$/.test(process.argv[1])) {
  void auditSavedSpectra(process.argv[2], process.argv[3]).then((r) => console.log(JSON.stringify(r, null, 2))).catch((e) => { console.error(e); process.exitCode = 1; });
}
