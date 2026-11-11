import assert from 'node:assert/strict';
import { test } from 'node:test';
import { OracleMatrix, ORACLE_AXES, ORACLE_SURFACES, oracleCoordinates } from '../research/opportunity/oracleMatrix';
import { auditSpectrumMatrix, surfaceEstimate } from '../research/opportunity/spectrumAudit';

function matrix() {
  const m = new OracleMatrix();
  for (let j = 0; j < 500; j++) {
    const raw = ORACLE_AXES.map((a, k) => a.transform === 'rsi' ? j % 101 : a.transform === 'log-atan' ? 1 + j % 20 : Math.sin(j / (k + 1)));
    for (const h of [15, 60] as const) m.add({ at: 60000, knownAt: (h + 1) * 60000, horizon: h, neutralBps: 1,
      category: j % 3 as 0 | 1 | 2, returnBps: j % 3 - 1, maxUpBps: 3, maxDownBps: 2 }, oracleCoordinates(raw));
  }
  return m;
}
test('actual weighted single/pair spectra are continuous and retain evidence without claiming learned importance', () => {
  const report = auditSpectrumMatrix(matrix());
  assert.equal(report.totalCurves, 812); assert.equal(report.learnedRelationshipImportance, false);
  assert.equal(report.nominalCurveWeightWithAllInputs, 1 / 407);
  assert.ok(report.curves.every((c) => c.evidenceWeight > 0 && c.continuousInterpolationVerified));
  assert.ok(report.curves.some((c) => c.probabilityRanges!.up[1] > c.probabilityRanges!.up[0]));
});
test('an unobserved spectrum is unknown evidence, rather than a verified predictive relationship', () => {
  const report = auditSpectrumMatrix(new OracleMatrix());
  assert.ok(report.curves.every((c) => c.occupiedCells === 0 && c.probabilityRanges === null && c.learnedImportanceWeight === null));
});
test('spectrum audit rejects inconsistent class mass and an ensemble that differs from the registered curves', (t) => {
  const invalid = matrix(); invalid.data[ORACLE_SURFACES[0].offset + 1] = 100000;
  assert.throws(() => auditSpectrumMatrix(invalid), /class evidence/);
  const m = matrix(), original = m.predict.bind(m);
  t.mock.method(m, 'predict', (...args: Parameters<OracleMatrix['predict']>) => ({ ...original(...args), p: [0.9, 0.05, 0.05] }));
  assert.throws(() => auditSpectrumMatrix(m), /differs/);
});
test('clock curves wrap continuously at midnight and week boundaries', () => {
  const m = matrix(), s = ORACLE_SURFACES.find((s) => s.name === 'clock:ny_hour')!;
  const a = surfaceEstimate(m, 15, s, -1e-9).probabilities, b = surfaceEstimate(m, 15, s, 1e-9).probabilities;
  assert.ok(a.every((p, i) => Math.abs(p - b[i]) < 1e-7));
});
