/** Audit locked forward trials; never fit, select a model, or promote one. */
import fs from 'node:fs';
import path from 'node:path';
import { orderFee } from '../../bot/fees';
import { bootstrapMeanCi } from '../stats';
import { digest } from './contractDataset';
import { readJsonLines } from './productCli';
import { sha256File } from './jointPathData';
import { EDGE_POLICY, edgeDirection, edgeEvidence, scoreEdgeForecast, type EdgeForecast } from './oracleEdge';

export const EDGE_ACCEPTANCE = Object.freeze({ minimumTrials: 20, adversePricePerFill: 0.01, confidence: 0.95, minimumOutcomeGroups: 20,
  controls: ['uniform', 'prior', 'reversed', 'always-up', 'always-down', 'random'],
  requirements: ['Positive first-sustained-direction ranking gain over the frozen historical prior on non-overlapping time groups; terminal-close accuracy is a separate diagnostic',
    'Positive paper return after fees and one-cent adverse-price stress at each fill', 'Positive paired stressed return against every predeclared control',
    'All observations retained, no overlapping trials, no cash refills, no unresolved positions, current verified fee terms'],
  automaticPromotion: false, actualVenueProfitVerified: false });

export interface EdgeTrialResult {
  startedAt: number; endedAt: number; failure: string | null;
  arms: Array<{ arm: string; net: number; stressedNet: number; fills: number; unresolved: number; verifiedFees: boolean }>;
}
export function qualifyEdgeTrials(trials: EdgeTrialResult[], direction: Array<{ horizon: number; status: string }>) {
  const sorted = [...trials].sort((a, b) => a.startedAt - b.startedAt);
  if (sorted.some((t, i) => !Number.isSafeInteger(t.startedAt) || t.endedAt <= t.startedAt || (i > 0 && t.startedAt < sorted[i - 1].endedAt))) throw new Error('overlapping or invalid forward trials');
  const blockers: string[] = [], primary = sorted.map((t) => t.arms.find((a) => a.arm === 'weighted'));
  if (primary.some((p) => !p)) throw new Error('missing weighted primary');
  if (sorted.length < EDGE_ACCEPTANCE.minimumTrials) blockers.push('Too few complete non-overlapping $200 trials');
  if (direction.find((d) => d.horizon === 15)?.status !== 'positive-direction-evidence') blockers.push('Direction gain lacks positive grouped evidence');
  if (sorted.some((t) => t.failure)) blockers.push('Failed trials remain in the cohort');
  if (sorted.some((t) => t.arms.some((a) => a.unresolved > 0))) blockers.push('Unresolved positions prevent a full-account comparison');
  if (sorted.some((t) => t.arms.some((p) => p.fills > 0 && !p.verifiedFees))) blockers.push('Current fee terms were not independently verified for every traded arm');
  if (!primary.some((p) => p!.fills > 0)) blockers.push('No executable primary entries');
  const enough = sorted.length >= EDGE_ACCEPTANCE.minimumTrials;
  const absolute = enough ? bootstrapMeanCi(primary.map((p) => p!.stressedNet), 0.05, 5000, 1729) : null;
  if (!absolute || absolute.lo <= 0) blockers.push('Stressed absolute return lacks a positive lower bound');
  const names = EDGE_ACCEPTANCE.controls;
  const comparisons = names.map((arm) => {
    const delta = sorted.map((t, i) => { const control = t.arms.find((a) => a.arm === arm); if (!control) throw new Error('missing registered control'); return primary[i]!.stressedNet - control.stressedNet; });
    const interval = enough ? bootstrapMeanCi(delta, 0.05, 5000, 1729) : null;
    return { control: arm, meanGain: delta.length ? delta.reduce((a, b) => a + b, 0) / delta.length : null, interval };
  });
  if (!comparisons.length || comparisons.some((c) => !c.interval || c.interval.lo <= 0)) blockers.push('Incremental stressed profit over all controls is not established');
  return { trials: sorted.length, status: blockers.length ? 'edge-not-established' : 'paper-edge-supported', edgeVerified: blockers.length === 0,
    blockers, absolute, comparisons, automaticPromotion: false, actualVenueProfitVerified: false,
    interpretation: 'Each trial is a separate fixed $200 experiment; trials are not added together as a single continuously funded account. Bootstrap evidence is approximate and market-specific.' };
}

const engineFiles = ['research/opportunity/oracleEdge.ts', 'research/opportunity/oracleEdgeCli.ts', 'research/opportunity/oracleMatrix.ts', 'research/opportunity/oracleImportance.ts',
  'research/opportunity/atlas.ts', 'research/opportunity/train.ts', 'research/opportunity/tvHistory.ts', 'research/opportunity/tvFetch.py', 'research/opportunity/directionPaper.ts',
  'bot/fees.ts', 'bot/paper/paperExchange.ts', 'bot/kalshi/feeSchedule.ts', 'bot/marketdata/orderBook.ts', 'bot/marketdata/historyStore.ts', 'package.json', 'package-lock.json'];

export function firstSustainedRank(f: EdgeForecast, closes: ReadonlyMap<number, number>) {
  const threshold = Math.max(1, 0.25 * f.atrBps * Math.sqrt(f.horizon / 15));
  let up: number | null = null, down: number | null = null, prevUp = false, prevDown = false;
  for (let at = f.featureAt + 60000; at <= f.byAt; at += 60000) {
    const price = closes.get(at); if (!(price! > 0)) return { available: false as const };
    const move = Math.log(price! / f.anchor) * 10000, future = at > f.publishedAt;
    if (future && prevUp && move >= threshold * 0.75 && up === null) up = at;
    if (future && prevDown && -move >= threshold * 0.75 && down === null) down = at;
    prevUp = future && move >= threshold; prevDown = future && -move >= threshold;
  }
  const first = up === null && down === null ? null : down === null || (up !== null && up < down) ? 'up' : 'down';
  const hit = (p: number[]) => Number(first !== null && edgeDirection(p) === first);
  return { available: true as const, first, upConfirmedAt: up, downConfirmedAt: down, weightedHit: hit(f.p), priorHit: hit(f.prior), uniformHit: hit(f.uniform) };
}
export async function aggregateOracleEdge(dirs: string[]) {
  let protocol: string | undefined;
  const trials: EdgeTrialResult[] = [], outcomes: ReturnType<typeof scoreEdgeForecast>[] = [], pathScores: ReturnType<typeof scoreEdgeForecast>[] = [], inputs: Record<string, string> = {};
  for (const dir of dirs) {
    const file = path.join(dir, 'report.json'), r = JSON.parse(fs.readFileSync(file, 'utf8')); inputs[file] = await sha256File(file);
    if (r.schema !== 'atlas-oracle-forward-edge-v1' || r.mode !== 'locked-forward-trial' || r.policy.id !== EDGE_POLICY.id || r.noFit !== true || r.primary !== 'weighted') throw new Error('Only registered locked forward trials may enter edge qualification');
    const identity = digest([r.policy, r.paper.map((p: { arm: string }) => p.arm), r.models, r.assets, r.cycles, engineFiles.map((f) => [f, r.codeHashes[f]])]);
    if (protocol && identity !== protocol) throw new Error('changed models, policy or implementation require a separate study'); protocol = identity;
    for (const [name, expected] of [['forecasts.jsonl', r.forecastsSha256], ['books.jsonl', r.booksSha256], ['outcomes.jsonl', r.outcomesSha256]]) {
      const file = path.join(dir, name); if (await sha256File(file) !== expected) throw new Error('changed forward evidence file'); inputs[file] = expected;
    }
    const forecasts = await readJsonLines<EdgeForecast>(path.join(dir, 'forecasts.jsonl')), byId = new Map(forecasts.map((f) => [f.id, f]));
    const prices = new Map<string, Map<number, number>>();
    for (const a of await readJsonLines<any>(path.join(dir, 'acquisitions.jsonl'))) if (a.report && a.knownAt <= r.endedAt) {
      const rawFile = path.join(dir, 'tv-history/tvdatafeed-receipts', path.basename(a.report.rawFile));
      if (await sha256File(rawFile) !== a.report.rawSha256) throw new Error('changed tvdatafeed acquisition receipt');
      const raw = JSON.parse(fs.readFileSync(rawFile, 'utf8'));
      for (const series of raw.payload.series) if (series.id.endsWith(':1m') && !series.error) {
        const asset = series.id.split(':')[0], ps = prices.get(asset) ?? new Map<number, number>(); prices.set(asset, ps);
        for (const row of series.rows) if (row[0] + 60000 <= Date.parse(a.report.acquiredAt) && !ps.has(row[0] + 60000)) ps.set(row[0] + 60000, row[4]);
      }
    }
    for (const f of forecasts) { const { id, ...core } = f;
      if (digest(core) !== id || f.publishedAt < r.startedAt || f.publishedAt > r.endedAt || f.featuresKnownAt > f.publishedAt || f.featureAt > f.featuresKnownAt || f.byAt <= f.publishedAt ||
          !r.models.some((m: { id: string; asset: string; learnedThrough: number }) => m.id === f.modelId && m.asset === f.asset && m.learnedThrough + 3600000 <= f.featureAt)) throw new Error('backdated, changed or future-trained forecast'); }
    for (const y of await readJsonLines<ReturnType<typeof scoreEdgeForecast>>(path.join(dir, 'outcomes.jsonl'))) {
      const f = byId.get(y.id); if (!f) throw new Error('outcome lacks a published forecast');
      if (y.status === 'complete' && (y.byAt !== f.byAt || y.publishedAt !== f.publishedAt || y.byAt > r.endedAt)) throw new Error('unexpired outcome or changed target');
      outcomes.push(y);
      if (y.status === 'complete') {
        const early = firstSustainedRank(f, prices.get(f.asset) ?? new Map());
        if (early.available) pathScores.push({ ...y, weightedLoss: 1 - early.weightedHit, priorLoss: 1 - early.priorHit, uniformLoss: 1 - early.uniformHit });
      }
    }
    const books = await readJsonLines<{ contract: { ticker: string }; quote: { knownAt: number }; fees: { schedule: Parameters<typeof orderFee>[3] } }>(path.join(dir, 'books.jsonl'));
    const schedules = new Map(books.map((b) => [`${b.contract.ticker}:${b.quote.knownAt}`, b.fees.schedule]));
    const arms = [];
    for (const p of r.paper) {
      const fills = await readJsonLines<{ at: number; ticker: string; action: string; sidePrice: number; quantity: number; fee: number }>(path.join(dir, `${p.arm}-fills.jsonl`));
      let stressCost = 0;
      for (const f of fills) {
        const schedule = schedules.get(`${f.ticker}:${f.at}`); if (!schedule) throw new Error('fill lacks same-arrival fee/book evidence');
        const price = Math.max(0, Math.min(1, f.sidePrice + (f.action === 'entry' ? 1 : -1) * EDGE_ACCEPTANCE.adversePricePerFill));
        stressCost += f.quantity * Math.abs(price - f.sidePrice) + orderFee(f.quantity, f.action === 'entry' ? price : 1 - price, true, schedule) - f.fee;
      }
      if (p.startingCash !== 200 || !p.noRefills || !Number.isFinite(p.endingCash) || fills.length !== p.fills) throw new Error('paper funding or fill count differs');
      arms.push({ arm: p.arm, net: p.endingCash - 200, stressedNet: p.endingCash - 200 - stressCost, fills: p.fills,
        unresolved: p.unresolvedPositions.length, verifiedFees: p.feeAsOfVerified === true });
    }
    trials.push({ startedAt: r.startedAt, endedAt: r.endedAt, failure: r.failure, arms });
  }
  const terminal = edgeEvidence(outcomes), direction = edgeEvidence(pathScores).map(({ calibration, ...score }) => ({ ...score,
    target: 'First confirmed two-minute sustained direction after actual forecast publication; missing paths unavailable, no-move cases count as misses for every ranking', loss: '0/1 directional-ranking miss' }));
  return { schema: 'atlas-oracle-edge-assessment-v1', acceptance: EDGE_ACCEPTANCE, protocol, inputs, direction, terminal, trials,
    assessment: qualifyEdgeTrials(trials, direction), stressMeaning: 'Fixed recorded fills with one cent adverse price per fill and recomputed fees; this is a cost sensitivity, not a second fill simulation' };
}
if (process.argv[1] && /(^|[/\\])oracleEdgeAggregate\.(ts|js)$/.test(process.argv[1])) {
  const args = process.argv.slice(2), out = args.shift();
  if (!out || !args.length) throw new Error('Expected output JSON then locked trial directories');
  void aggregateOracleEdge(args).then((r) => { fs.writeFileSync(out, JSON.stringify(r, null, 2) + '\n', { flag: 'wx' }); console.log(JSON.stringify(r.assessment)); })
    .catch((e) => { console.error(e instanceof Error ? e.stack : e); process.exitCode = 1; });
}
