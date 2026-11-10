import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { gzipSync } from 'node:zlib';
import { test } from 'node:test';
import { digest } from '../research/opportunity/contractDataset';
import { OracleMatrix, oracleCoordinates, ORACLE_AXES, ORACLE_SCHEMA, ORACLE_LAYOUT_ID } from '../research/opportunity/oracleMatrix';
import { IMPORTANCE_EXPERTS } from '../research/opportunity/oracleImportance';
import { loadEdgeOracle, scoreEdgeForecast, edgeEvidence, edgeDirection } from '../research/opportunity/oracleEdge';
import { sha256File } from '../research/opportunity/jointPathData';
import { edgeListedMarkets } from '../research/opportunity/oracleEdgeCli';

const T = Date.UTC(2026, 10, 10), MIN = 60000;
async function model(dir: string) {
  const m = new OracleMatrix(), raw = ORACLE_AXES.map(() => NaN); raw[0] = 100; raw[1] = -2;
  for (let i = 0; i < 500; i++) for (const a of [0, 100]) for (const b of [-2, 2]) {
    const x = [...raw]; x[0] = a; x[1] = b;
    m.add({ at: MIN, knownAt: 16 * MIN, horizon: 15, neutralBps: 1, category: (a === 100) !== (b === 2) ? 0 : 2, returnBps: 5, maxUpBps: 10, maxDownBps: -10 }, oracleCoordinates(x));
  }
  const file = path.join(dir, 'full-history-model.f64.gz'); fs.writeFileSync(file, gzipSync(Buffer.from(m.data.buffer)));
  const mc = { schema: ORACLE_SCHEMA, layoutId: ORACLE_LAYOUT_ID, asset: 'BTC', source: 'archive-binance-1m-quarantined-v1', trainedThrough: 16 * MIN, file: path.basename(file), sha256: await sha256File(file) };
  const mid = digest(mc); fs.writeFileSync(path.join(dir, 'model.json'), JSON.stringify({ ...mc, id: mid }));
  const wc = { schema: 'opportunity-oracle-importance-v1', layoutId: ORACLE_LAYOUT_ID, originalModelIdentity: mid, asset: 'BTC', finalWeights: [15, 60].map((horizon) => ({ horizon,
    importanceTrainedThrough: 16 * MIN, curves: IMPORTANCE_EXPERTS.map((name) => ({ name, logWeight: name === 'm1:rsi x m1:macd_hist_atr' ? 5 : 0 })) })) };
  fs.writeFileSync(path.join(dir, 'importance.json'), JSON.stringify({ ...wc, id: digest(wc) }));
  return { reader: await loadEdgeOracle(path.join(dir, 'model.json'), path.join(dir, 'importance.json')), raw };
}
test('frozen Oracle serves learned importance and explicitly identifies transferred source and delayed publication', async (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'oracle-edge-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const { reader, raw } = await model(dir), o = { raw, featureAt: T, knownAt: T + 2000, publishedAt: T + 5000, anchor: 100, atrBps: 20, horizon: 15 as const };
  const f = reader.forecast(o); assert.ok(f.p[0] > f.uniform[0] + 0.1); assert.equal(f.byAt, T + 15 * MIN);
  assert.equal(f.featuresKnownAt, o.knownAt); assert.equal(f.inputSource, 'tvdatafeed-binance'); assert.equal(f.providerTransfer, true); assert.equal(f.activeCurves, 3);
  assert.throws(() => reader.forecast({ ...o, knownAt: T + 6000 }), /future/);
  assert.throws(() => reader.forecast({ ...o, publishedAt: T + 3 * MIN }), /stale/);
  fs.appendFileSync(path.join(dir, 'full-history-model.f64.gz'), 'changed');
  await assert.rejects(loadEdgeOracle(path.join(dir, 'model.json'), path.join(dir, 'importance.json')), /hash/);
});
test('forward outcomes remain pending until their exact minute close; no missing prices become sideways labels', async (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'oracle-edge-label-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const { reader, raw } = await model(dir), f = reader.forecast({ raw, featureAt: T, knownAt: T + 1000, publishedAt: T + 2000, anchor: 100, atrBps: 20, horizon: 15 });
  const prices = new Map(Array.from({ length: 16 }, (_, i) => [T + i * MIN, 100 + i / 10]));
  assert.equal(scoreEdgeForecast(f, prices, f.byAt - 1).status, 'pending');
  const result = scoreEdgeForecast(f, prices, f.byAt); assert.equal(result.status, 'complete');
  if (result.status === 'complete') { assert.equal(result.category, 0); assert.equal(result.firstSustainedCloseAt, T + 2 * MIN); assert.ok(result.weightedLoss < result.uniformLoss); }
  prices.delete(f.byAt); assert.equal(scoreEdgeForecast(f, prices, f.byAt).status, 'missing-price');
  assert.equal(edgeDirection([0.3, 0.4, 0.3]), null);
});
test('overlapping minute predictions do not manufacture independent edge evidence', () => {
  const row = { id: 'x', status: 'complete' as const, asset: 'BTC', horizon: 60 as const, publishedAt: T, byAt: T + 60 * MIN,
    group: Math.floor(T / 3600000), returnBps: 10, signedReturnBps: 10, category: 0, weightedLoss: 0.2, uniformLoss: 0.4, priorLoss: 0.6,
    predictedClass: 0, probabilities: [0.8, 0.1, 0.1], firstSustainedCloseAt: null, missingPath: false };
  const result = edgeEvidence(Array.from({ length: 1000 }, (_, i) => ({ ...row, id: `${i}`, publishedAt: T + i * 1000 })))[1];
  assert.equal(result.rows, 1000); assert.equal(result.nonOverlappingUtcHourGroups, 1); assert.equal(result.status, 'insufficient-evidence'); assert.equal(result.groupedInterval, null);
});
test('contract selection consumes every close-filtered market page and rejects partial listings', async () => {
  const m = (ticker: string, floor: number, close = T + 3600000) => ({ ticker, series_ticker: 'KXBTCD', open_time: new Date(T - MIN).toISOString(), close_time: new Date(close).toISOString(), floor_strike: floor });
  const routes: string[] = [];
  const r = await edgeListedMarkets('KXBTCD', T, async (route) => { routes.push(route); return { knownAt: T + 1000, sourceSha256: 'a'.repeat(64),
    data: route.includes('cursor=next') ? { markets: [m('KXBTCD-H-T75000', 75000)], cursor: '' }
      : { markets: [m('KXBTCD-H-T83000', 83000), m('KXBTCD-FUTURE-T75000', 75000, T + 7200000)], cursor: 'next' } }; });
  assert.equal(routes.length, 2); assert.ok(routes.every((s) => s.includes('min_close_ts=') && s.includes('max_close_ts=')));
  assert.equal(r.markets.length, 2); assert.equal(r.markets.sort((a, b) => Math.abs(a.floorStrike! - 75000) - Math.abs(b.floorStrike! - 75000))[0].floorStrike, 75000);
  await assert.rejects(edgeListedMarkets('KXBTCD', T, async (route) => route.includes('cursor=next') ? null : { knownAt: T, sourceSha256: '', data: { markets: [m('KXBTCD-H-T83000', 83000)], cursor: 'next' } }), /incomplete/);
  await assert.rejects(edgeListedMarkets('KXBTCD', T, async () => ({ knownAt: T, sourceSha256: '', data: { markets: [], cursor: 'same' } })), /repeating/);
});
