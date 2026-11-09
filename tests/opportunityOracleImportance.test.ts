import assert from 'node:assert/strict';
import { test } from 'node:test';
import { OracleMatrix, ORACLE_AXES, oracleCoordinates, type OracleAnswer } from '../research/opportunity/oracleMatrix';
import { IMPORTANCE_EXPERTS, OracleImportance, importanceMixture, oracleComponents } from '../research/opportunity/oracleImportance';

const T = Date.UTC(2023, 0, 1), MIN = 60000;
test('independent expert components reconstruct the original uniform confidence with continuous interpolation', () => {
  const m = new OracleMatrix();
  for (let i = 0; i < 100; i++) {
    const y: OracleAnswer = { at: T + i * MIN, knownAt: T + (i + 15) * MIN, horizon: 15, neutralBps: 1,
      category: i < 65 ? 0 : 2, returnBps: i < 65 ? 5 : -5, maxUpBps: 10, maxDownBps: -10 };
    const raw = ORACLE_AXES.map((_, j) => j === 0 ? i : j % 5 === 0 ? NaN : 0.2); m.add(y, oracleCoordinates(raw));
  }
  const raw = ORACLE_AXES.map((_, j) => j === 0 ? 55 : j % 5 === 0 ? NaN : 0.2), at = T + 300 * MIN;
  const c = oracleCoordinates(raw), components = oracleComponents(m, 15, c, at), weights = IMPORTANCE_EXPERTS.map(() => 0);
  const p = importanceMixture(components, weights), original = m.predict(15, c, at).p;
  for (let k = 0; k < 3; k++) assert.ok(Math.abs(p[k] - original[k]) < 1e-12);
  const close = [...raw]; close[0] += 1e-6;
  const next = importanceMixture(oracleComponents(m, 15, oracleCoordinates(close), at), weights);
  assert.ok(Math.abs(p[0] - next[0]) < 1e-6);
  assert.throws(() => oracleComponents(m, 15, c, m.trainedThrough), /temporal/);
});
test('importance changes only at the next eligible quarter and favors predictive curves over harmful curves', () => {
  const importance = new OracleImportance(), c = new Float64Array(IMPORTANCE_EXPERTS.length * 3).fill(NaN);
  c.set([0.5, 0.25, 0.25]); c.set([0.8, 0.1, 0.1], 3); c.set([0.1, 0.45, 0.45], 6);
  for (let i = 0; i < 200; i++) importance.observe(c, 0, T + i * 1000);
  assert.ok(importance.logWeights.every((w) => w === 0));
  assert.throws(() => importance.closeQuarter(T + 200000), /embargo/);
  const evidence = importance.closeQuarter(T + 3600000 + 200000);
  assert.ok(importance.logWeights[1] > importance.logWeights[2]); assert.ok(evidence[1].gain! > 0); assert.ok(evidence[2].gain! < 0);
  assert.equal(importance.logWeights[0], 0); assert.equal(importance.logWeights[3], 0, 'missing evidence does not earn invented importance');
  const weighted = importanceMixture(c, importance.logWeights), uniform = importanceMixture(c, IMPORTANCE_EXPERTS.map(() => 0));
  assert.ok(weighted[0] > uniform[0]); assert.ok(Math.abs(weighted.reduce((n, p) => n + p, 0) - 1) < 1e-12);
});
