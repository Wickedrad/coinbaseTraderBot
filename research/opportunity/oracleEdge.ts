/** Frozen Oracle forecasting and forward scoring. No fitting or exchange client. */
import fs from 'node:fs';
import path from 'node:path';
import { gunzipSync } from 'node:zlib';
import { digest, stamp } from './contractDataset';
import { sha256File } from './jointPathData';
import { ORACLE_AXES, ORACLE_SCHEMA, ORACLE_LAYOUT_ID, ORACLE_HORIZON_SIZE, ORACLE_HORIZONS, OracleMatrix, oracleCoordinates } from './oracleMatrix';
import { IMPORTANCE_EXPERTS, importanceMixture, oracleComponents } from './oracleImportance';
import { bootstrapMeanCi } from '../stats';

export const EDGE_POLICY = Object.freeze({ id: 'frozen-oracle-forward-tv-binance-v1', assets: ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE'],
  maximumBarAgeMs: 120000, minimumOutcomeGroups: 20, saleBufferMs: 30000, positionCostUsd: 20, poolUsd: 200,
  minimumNetTakeUsd: 0.01, forecasts: [15, 60], paperHorizon: 15, quotePollMs: 5000,
  selection: 'Predeclared directional ranking; sideways probability is reported, no claimed calibrated confidence cutoff',
  providerTransfer: 'Original archived Binance minute curves evaluated on explicit tvdatafeed BINANCE USDT candles; no provider relabeling',
  fittingAllowed: false, liveEntryAllowed: false, autoPromote: false });
export interface EdgeForecast {
  id: string; modelId: string; asset: string; publishedAt: number; featureAt: number; featuresKnownAt: number; byAt: number; horizon: 15 | 60;
  anchor: number; atrBps: number; p: number[]; uniform: number[]; prior: number[]; availableAxes: string[]; activeCurves: number;
  trainingSource: string; inputSource: 'tvdatafeed-binance'; providerTransfer: true;
}
export async function loadEdgeOracle(modelFile: string, importanceFile: string) {
  const m = JSON.parse(fs.readFileSync(modelFile, 'utf8')), w = JSON.parse(fs.readFileSync(importanceFile, 'utf8'));
  const { id: mid, ...mc } = m, { id: wid, ...wc } = w;
  if (digest(mc) !== mid || digest(wc) !== wid || m.schema !== ORACLE_SCHEMA || w.schema !== 'opportunity-oracle-importance-v1' || m.layoutId !== ORACLE_LAYOUT_ID || w.layoutId !== ORACLE_LAYOUT_ID ||
      w.originalModelIdentity !== mid || w.asset !== m.asset || !stamp(m.trainedThrough) || m.trainedThrough >= Date.UTC(2026, 10, 9) ||
      m.source !== 'archive-binance-1m-quarantined-v1' || m.file !== 'full-history-model.f64.gz') throw new Error('Oracle model/importance identity differs');
  const weights = new Map<15 | 60, number[]>(); let learnedThrough = m.trainedThrough;
  for (const h of ORACLE_HORIZONS) {
    const row = w.finalWeights.find((r: { horizon: number }) => r.horizon === h);
    if (!row || row.curves.length !== IMPORTANCE_EXPERTS.length || row.curves.some((r: { name: string; logWeight: number }, i: number) =>
      r.name !== IMPORTANCE_EXPERTS[i] || !Number.isFinite(r.logWeight) || Math.abs(r.logWeight) > 5) || !stamp(row.importanceTrainedThrough)) throw new Error('Oracle importance vocabulary differs');
    weights.set(h, row.curves.map((r: { logWeight: number }) => r.logWeight)); learnedThrough = Math.max(learnedThrough, row.importanceTrainedThrough);
  }
  const file = path.join(path.dirname(modelFile), m.file), data = new Float64Array(ORACLE_HORIZON_SIZE * 2);
  if (await sha256File(file) !== m.sha256) throw new Error('Oracle matrix hash differs');
  const bytes = gunzipSync(fs.readFileSync(file), { maxOutputLength: data.byteLength });
  if (bytes.length !== data.byteLength) throw new Error('Oracle matrix size differs'); Buffer.from(data.buffer).set(bytes);
  const matrix = new OracleMatrix(data); matrix.trainedThrough = learnedThrough;
  const modelId = digest([mid, wid, EDGE_POLICY.id]);
  return { asset: m.asset as string, modelId, learnedThrough, modelHash: mid as string, importanceHash: wid as string,
    forecast(o: { raw: number[]; featureAt: number; knownAt: number; publishedAt: number; anchor: number; atrBps: number; horizon: 15 | 60 }): EdgeForecast {
      if (![o.featureAt, o.knownAt, o.publishedAt].every(stamp) || o.featureAt % 60000 || o.featureAt > o.knownAt || o.knownAt > o.publishedAt ||
          o.publishedAt - o.featureAt > EDGE_POLICY.maximumBarAgeMs || !(o.anchor > 0) || !(o.atrBps > 0)) throw new Error('future, stale or invalid Oracle feature publication');
      const c = oracleComponents(matrix, o.horizon, oracleCoordinates(o.raw), o.featureAt), p = importanceMixture(c, weights.get(o.horizon)!);
      const core = { modelId, asset: m.asset, publishedAt: o.publishedAt, featureAt: o.featureAt, featuresKnownAt: o.knownAt, byAt: o.featureAt + o.horizon * 60000,
        horizon: o.horizon, anchor: o.anchor, atrBps: o.atrBps, p, uniform: importanceMixture(c, IMPORTANCE_EXPERTS.map(() => 0)), prior: Array.from(c.slice(0, 3)),
        availableAxes: ORACLE_AXES.filter((_, i) => Number.isFinite(o.raw[i])).map((a) => a.name),
        activeCurves: Array.from({ length: IMPORTANCE_EXPERTS.length - 1 }, (_, i) => Number(Number.isFinite(c[(i + 1) * 3]))).reduce((a, b) => a + b, 0),
        trainingSource: m.source, inputSource: 'tvdatafeed-binance' as const, providerTransfer: true as const };
      return { ...core, id: digest(core) };
    } };
}
export function edgeDirection(p: number[]): 'up' | 'down' | null {
  if (p.length !== 3 || p.some((x) => !Number.isFinite(x) || x < 0 || x > 1) || Math.abs(p.reduce((a, b) => a + b, 0) - 1) > 1e-8) throw new Error('invalid Oracle probabilities');
  return Math.abs(p[0] - p[2]) < 1e-10 ? null : p[0] > p[2] ? 'up' : 'down';
}
/** Prices are actual closed minute bars. Intraminute order and fills are never inferred. */
export function scoreEdgeForecast(f: EdgeForecast, closes: ReadonlyMap<number, number>, knownAt: number) {
  if (knownAt < f.byAt) return { id: f.id, status: 'pending' as const };
  const target = closes.get(f.byAt); if (!(target! > 0)) return { id: f.id, status: 'missing-price' as const };
  const ret = Math.log(target! / f.anchor) * 10000, neutral = Math.max(1, 0.25 * f.atrBps * Math.sqrt(f.horizon / 15));
  const y = ret > neutral ? 0 : ret < -neutral ? 2 : 1, loss = (p: number[]) => -Math.log(Math.max(1e-12, p[y]));
  const sign = edgeDirection(f.p) === 'up' ? 1 : edgeDirection(f.p) === 'down' ? -1 : 0;
  let firstSustainedCloseAt: number | null = null, previous = false, missingPath = false;
  for (let at = f.featureAt + 60000; at <= f.byAt; at += 60000) {
    const price = closes.get(at); if (!(price! > 0)) { missingPath = true; previous = false; continue; }
    const move = sign * Math.log(price! / f.anchor) * 10000;
    if (at > f.publishedAt && previous && move >= neutral * 0.75 && firstSustainedCloseAt === null) firstSustainedCloseAt = at;
    previous = at > f.publishedAt && move >= neutral;
  }
  return { id: f.id, status: 'complete' as const, asset: f.asset, horizon: f.horizon, publishedAt: f.publishedAt, byAt: f.byAt,
    group: Math.floor(f.publishedAt / 3600000), returnBps: ret, signedReturnBps: sign * ret, category: y,
    weightedLoss: loss(f.p), uniformLoss: loss(f.uniform), priorLoss: loss(f.prior),
    predictedClass: f.p.indexOf(Math.max(...f.p)), probabilities: f.p, firstSustainedCloseAt: missingPath ? null : firstSustainedCloseAt, missingPath };
}
export function edgeEvidence(scores: ReturnType<typeof scoreEdgeForecast>[]) {
  return ORACLE_HORIZONS.map((horizon) => {
    const rs = scores.filter((r): r is Extract<typeof r, { status: 'complete' }> => r.status === 'complete' && r.horizon === horizon);
    const candidates = new Map<number, typeof rs>(); for (const r of rs) candidates.set(r.group, [...(candidates.get(r.group) ?? []), r]);
    const groups = new Map<number, number[]>(); let lastEnd = 0;
    for (const [group, rows] of [...candidates].sort(([a], [b]) => a - b)) {
      const first = new Map<string, typeof rows[number]>();
      for (const r of [...rows].sort((a, b) => a.publishedAt - b.publishedAt)) if (!first.has(r.asset)) first.set(r.asset, r);
      const selected = [...first.values()];
      if (Math.min(...selected.map((r) => r.publishedAt)) < lastEnd) continue;
      groups.set(group, selected.map((r) => r.priorLoss - r.weightedLoss)); lastEnd = Math.max(...selected.map((r) => r.byAt));
    }
    const gains = [...groups.values()].map((xs) => xs.reduce((a, b) => a + b, 0) / xs.length), ci = gains.length >= EDGE_POLICY.minimumOutcomeGroups ? bootstrapMeanCi(gains, 0.05, 5000, 1729) : null;
    return { horizon, rows: rs.length, observedUtcHourGroups: candidates.size, nonOverlappingUtcHourGroups: groups.size, meanGainOverPrior: gains.length ? gains.reduce((a, b) => a + b, 0) / gains.length : null,
      groupedInterval: ci, status: !ci ? 'insufficient-evidence' : ci.lo > 0 ? 'positive-direction-evidence' : 'no-positive-edge-established',
      calibration: Array.from({ length: 10 }, (_, bin) => { const selected = rs.filter((r) => Math.min(9, Math.floor(Math.max(...r.probabilities) * 10)) === bin);
        return { from: bin / 10, rows: selected.length, predicted: selected.length ? selected.reduce((s, r) => s + Math.max(...r.probabilities), 0) / selected.length : null,
          observed: selected.length ? selected.filter((r) => r.category === r.predictedClass).length / selected.length : null }; }) };
  });
}
