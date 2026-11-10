import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { aggregateOracleEdge, firstSustainedRank, qualifyEdgeTrials, type EdgeTrialResult } from '../research/opportunity/oracleEdgeAggregate';
import { EDGE_POLICY, scoreEdgeForecast, type EdgeForecast } from '../research/opportunity/oracleEdge';
import { auditEdgeLedger, type SavedEdgeBook, type SavedEdgeFill } from '../research/opportunity/oracleEdgeLedger';
import { DirectionPaperAccount } from '../research/opportunity/directionPaper';
import { digest } from '../research/opportunity/contractDataset';
import { sha256File } from '../research/opportunity/jointPathData';
import { codeHashes } from '../research/opportunity/productCli';
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
test('independent fill audit recomputes net cash and stressed fees from the observed book', () => {
  const books: SavedEdgeBook[] = [0, 1000].map((ms) => ({ contract: { ticker: 'T' }, quote: { knownAt: start + ms,
    bids: [{ price: ms ? 0.45 : 0.39, size: 20 }], asks: [{ price: ms ? 0.46 : 0.40, size: 20 }] }, fees: { schedule: { takerMultiplier: 1, makerMultiplier: 0, balancePrecision: 0.01 } } }));
  const fills: SavedEdgeFill[] = [{ ticker: 'T', at: start, side: 'yes', action: 'entry', sidePrice: 0.4, quantity: 20, fee: 0.34 },
    { ticker: 'T', at: start + 1000, side: 'yes', action: 'exit', sidePrice: 0.45, quantity: 20, fee: 0.35 }];
  const r = auditEdgeLedger(fills, books); assert.ok(Math.abs(r.endingCash - 200.31) < 1e-8); assert.equal(r.unresolved, 0);
  assert.ok(r.stressCost > 0.39); assert.ok(r.endingCash - 200 - r.stressCost < 0, 'a tiny fee-net gain is not robust to one cent adverse at both fills');
  assert.throws(() => auditEdgeLedger([{ ...fills[0], quantity: 21 }], books), /depth/);
  assert.throws(() => auditEdgeLedger([{ ...fills[0], fee: 0 }], books), /fee/);
});
test('artifact assessment runs from sealed forecasts through raw prices and native paper fills, then rejects changed books', async (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'oracle-edge-artifacts-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const save = (name: string, x: unknown) => fs.writeFileSync(path.join(dir, name), JSON.stringify(x) + '\n');
  const core = { modelId: 'a'.repeat(64), asset: 'BTC', publishedAt: start + 2000, featureAt: start, featuresKnownAt: start + 1000, byAt: start + 900000,
    horizon: 15 as const, anchor: 100, atrBps: 20, p: [0.6, 0.2, 0.2], uniform: [0.4, 0.3, 0.3], prior: [0.2, 0.3, 0.5],
    availableAxes: ['m1:rsi'], activeCurves: 1, trainingSource: 'archive-binance-1m-quarantined-v1', inputSource: 'tvdatafeed-binance' as const, providerTransfer: true as const };
  const f = { ...core, id: digest(core) }, prices = new Map(Array.from({ length: 16 }, (_, i) => [start + i * 60000, i === 15 ? 100 : 100 + i / 100]));
  const downCore = { ...core, p: [0.2, 0.2, 0.6] }, down = { ...downCore, id: digest(downCore) };
  assert.ok(Object.is(scoreEdgeForecast(down, prices, start + 72 * 60000).signedReturnBps, -0));
  fs.writeFileSync(path.join(dir, 'forecasts.jsonl'), [f, down].map((x) => JSON.stringify(x)).join('\n') + '\n');
  fs.writeFileSync(path.join(dir, 'outcomes.jsonl'), [f, down].map((x) => JSON.stringify(scoreEdgeForecast(x, prices, start + 72 * 60000))).join('\n') + '\n');
  const policy = { startingCash: 200, maximumPositionCost: 20, maximumContracts: 20, maximumOpenPositions: 5, minimumNetTakeUsd: 0.01,
    targetContractRoi: 0, minimumSignalProbability: 0, maximumQuoteAgeMs: 2000, maximumSignalAgeMs: 90000, saleBufferMs: 30000 };
  const profit = JSON.parse(fs.readFileSync('research/opportunity/examples/profit-policy.json', 'utf8'));
  const c = { ticker: 'T', asset: 'BTC', openTime: start - 3600000, closeTime: start + 3600000, termsKnownAt: start, terms: { kind: 'greater' as const, strike: 100 }, settlementReference: 'fixture' };
  const fees = { schedule: { takerMultiplier: 1, makerMultiplier: 0, balancePrecision: 0.01 }, knownAt: start, effectiveFrom: start, sourceSha256: 'b'.repeat(64), basis: 'observed-as-of' as const };
  const books = [3000, 5000].map((ms) => ({ contract: c, fees, quote: { ticker: 'T', at: start + ms, knownAt: start + ms, sourceSha256: 'b'.repeat(64),
    bids: [{ price: ms === 3000 ? 0.39 : 0.45, size: 20 }], asks: [{ price: ms === 3000 ? 0.40 : 0.46, size: 20 }] } }));
  fs.writeFileSync(path.join(dir, 'books.jsonl'), books.map((b) => JSON.stringify(b)).join('\n') + '\n');
  const paper = [];
  for (const arm of ['weighted', 'uniform', 'prior', 'reversed', 'always-up', 'always-down', 'random']) {
    const account = new DirectionPaperAccount(policy, profit, start - 10000);
    if (arm === 'weighted') for (const b of books) await account.observe(c, b.quote, fees, { id: f.id, modelId: f.modelId, asOf: f.publishedAt,
      producedAt: f.publishedAt, featuresKnownAt: f.featuresKnownAt, byAt: f.byAt, direction: 'up', probability: f.p[0] });
    paper.push({ arm, ...account.report() }); fs.writeFileSync(path.join(dir, `${arm}-fills.jsonl`), account.fills.map((r) => JSON.stringify(r)).join('\n') + '\n');
  }
  fs.mkdirSync(path.join(dir, 'tv-history/tvdatafeed-receipts'), { recursive: true });
  const rawFile = path.join(dir, 'tv-history/tvdatafeed-receipts/fixture.json');
  fs.writeFileSync(rawFile, JSON.stringify({ payload: { series: [{ id: 'BTC:1m', error: null, rows: [...prices].map(([at, value]) => [at - 60000, value, value, value, value, 1]) }] } }));
  save('acquisitions.jsonl', { knownAt: start + 72 * 60000 - 1, report: { rawFile: '/old/fixture.json', acquiredAt: new Date(start + 72 * 60000 - 2).toISOString(), rawSha256: await sha256File(rawFile) } });
  save('report.json', { schema: 'atlas-oracle-forward-edge-v1', mode: 'locked-forward-trial', policy: EDGE_POLICY, primary: 'weighted', noFit: true,
    models: [{ id: f.modelId, asset: 'BTC', learnedThrough: start - 86400000 }], assets: ['BTC'], cycles: 72, codeHashes: await codeHashes(),
    startedAt: start - 10000, endedAt: start + 72 * 60000, failure: null, rejectedAssets: [], paper,
    forecastsSha256: await sha256File(path.join(dir, 'forecasts.jsonl')), outcomesSha256: await sha256File(path.join(dir, 'outcomes.jsonl')), booksSha256: await sha256File(path.join(dir, 'books.jsonl')) });
  const assessed = await aggregateOracleEdge([dir]); assert.equal(assessed.assessment.edgeVerified, false); assert.equal(assessed.trials.length, 1);
  const result = assessed.trials[0].arms.find((a) => a.arm === 'weighted')!; assert.ok(Math.abs(result.net - 0.31) < 1e-8); assert.ok(result.stressedNet < 0);
  assert.equal(assessed.direction[0].nonOverlappingUtcHourGroups, 1);
  assert.equal(assessed.direction[0].pathCounts.up, 2); assert.equal(assessed.direction[0].descriptiveHitRate.weighted, 0.5);
  assert.equal(assessed.direction[0].descriptiveHitRate.prior, 0);
  fs.appendFileSync(path.join(dir, 'books.jsonl'), ' '); await assert.rejects(aggregateOracleEdge([dir]), /changed forward evidence/);
  const report = JSON.parse(fs.readFileSync(path.join(dir, 'report.json'), 'utf8'));
  report.booksSha256 = await sha256File(path.join(dir, 'books.jsonl'));
  const outcome = JSON.parse(fs.readFileSync(path.join(dir, 'outcomes.jsonl'), 'utf8').trim().split('\n')[0]);
  save('outcomes.jsonl', { ...outcome, weightedLoss: 0 }); report.outcomesSha256 = await sha256File(path.join(dir, 'outcomes.jsonl')); save('report.json', report);
  await assert.rejects(aggregateOracleEdge([dir]), /raw first-observed prices/, 'a new manifest hash cannot replace independent outcome reconstruction');
});
