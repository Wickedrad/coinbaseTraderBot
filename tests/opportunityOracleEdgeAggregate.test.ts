import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { aggregateOracleEdge, firstSustainedRank, qualifyEdgeTrials, type EdgeTrialResult } from '../research/opportunity/oracleEdgeAggregate';
import type { EdgeForecast } from '../research/opportunity/oracleEdge';
import type { edgeEvidence } from '../research/opportunity/oracleEdge';

const positiveDirection = [{ horizon: 15, status: 'positive-direction-evidence' }] as ReturnType<typeof edgeEvidence>;
const start = Date.UTC(2026, 10, 10);
function trials(n = 20): EdgeTrialResult[] { return Array.from({ length: n }, (_, i) => ({ startedAt: start + i * 7200000, endedAt: start + i * 7200000 + 4320000, failure: null,
  arms: [{ arm: 'weighted', net: 5, stressedNet: 4 + i / 100, fills: 4, unresolved: 0, verifiedFees: true },
    ...['uniform', 'prior', 'reversed', 'always-up', 'always-down', 'random'].map((arm) => ({ arm, net: 1, stressedNet: 0, fills: 4, unresolved: 0, verifiedFees: true }))] })); }
test('registered edge criteria require incremental stressed profit and adequate direction evidence', () => {
  const r = qualifyEdgeTrials(trials(), positiveDirection);
  assert.equal(r.status, 'paper-edge-supported'); assert.equal(r.comparisons.length, 6); assert.equal(r.edgeVerified, true);
  assert.equal(r.automaticPromotion, false); assert.equal(r.actualVenueProfitVerified, false);
  const weak = trials(); for (const t of weak) t.arms[1].stressedNet = 8;
  assert.equal(qualifyEdgeTrials(weak, positiveDirection).edgeVerified, false, 'a profitable bot must still outperform its registered controls');
  assert.equal(qualifyEdgeTrials(trials(), []).edgeVerified, false, 'profit alone does not verify relationship-based direction prediction');
});
test('thin cohorts, missing fees, unresolved costs and failed runs cannot be hidden by large winning sales', () => {
  assert.equal(qualifyEdgeTrials(trials(1), positiveDirection).edgeVerified, false);
  for (const bad of ['fee', 'open', 'failed'] as const) {
    const ts = trials(); ts[0].arms[0].stressedNet = 300;
    if (bad === 'fee') ts[0].arms[1].verifiedFees = false;
    if (bad === 'open') ts[0].arms[0].unresolved = 1;
    if (bad === 'failed') ts[0].failure = 'missing source';
    assert.equal(qualifyEdgeTrials(ts, positiveDirection).edgeVerified, false);
  }
  const overlap = trials(); overlap[1].startedAt = overlap[0].startedAt + 1;
  assert.throws(() => qualifyEdgeTrials(overlap, positiveDirection), /overlapping/);
});
test('engineering probes cannot be recycled as locked edge trials', async (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'oracle-edge-probe-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  fs.writeFileSync(path.join(dir, 'report.json'), JSON.stringify({ schema: 'atlas-oracle-forward-edge-v1', mode: 'engineering-short-trial' }));
  await assert.rejects(aggregateOracleEdge([dir]), /locked forward/);
});
test('early sustained-direction credit survives a later terminal reversal and never fills missing price paths', () => {
  const f = { featureAt: start, publishedAt: start + 5000, byAt: start + 15 * 60000, horizon: 15, anchor: 100, atrBps: 20,
    p: [0.5, 0.3, 0.2], prior: [0.2, 0.3, 0.5], uniform: [0.3, 0.4, 0.3] } as EdgeForecast;
  const prices = new Map(Array.from({ length: 15 }, (_, i) => [start + (i + 1) * 60000, i < 3 ? 100.1 : 99.5]));
  const r = firstSustainedRank(f, prices); assert.equal(r.available, true);
  if (r.available) { assert.equal(r.first, 'up'); assert.equal(r.weightedHit, 1); assert.equal(r.priorHit, 0); }
  prices.delete(start + 4 * 60000); assert.equal(firstSustainedRank(f, prices).available, false);
});
