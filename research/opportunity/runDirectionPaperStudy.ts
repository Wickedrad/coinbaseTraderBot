/** $200 accounts using the native PaperExchange, actual snapshots, learned direction only. */
import fs from 'node:fs';
import path from 'node:path';
import { DEFAULT_FEES } from '../../bot/fees';
import { DirectionPaperAccount, type DirectionPaperPolicy, type DirectionPaperSignal, type PaperFeeTerms, type SnapshotEvidence } from './directionPaper';
import type { TimedPriceContract } from './contractTiming';
import type { ProfitPolicy } from './profitExit';
import { digest } from './contractDataset';
import { sha256File } from './jointPathData';
import { readJsonLines } from './productCli';
import { assembleMovementDataset, loadMovementDataset } from './movementCli';
import { advanceModelSupports, encodeAdvanceMovement, validateAdvanceModel, type AdvanceModel } from './movementStudy';
import { binaryResponseProbability, missingRequiredInputs } from './contractLearner';
import { studyPolicy } from './studyPolicy';

export async function runDirectionPaperStudy(o: { native: string; snapshots: string; policy: string; out: string }) {
  const root = path.resolve(o.out), profit = JSON.parse(fs.readFileSync(o.policy, 'utf8')) as ProfitPolicy;
  const nativeSummary = JSON.parse(fs.readFileSync(path.join(o.native, 'summary.json'), 'utf8'));
  const registered = studyPolicy(nativeSummary.policy.id), plan = nativeSummary.plan;
  if (fs.existsSync(root)) throw new Error('new cash-paper output required'); fs.mkdirSync(root, { recursive: true });
  const receipt = JSON.parse(fs.readFileSync(path.join(o.snapshots, 'import-report.json'), 'utf8'));
  const snapshotFile = path.join(o.snapshots, 'snapshots.jsonl');
  if (!receipt.sampling.snapshotDecisionsOnly || await sha256File(snapshotFile) !== receipt.snapshots.sha256) throw new Error('full-snapshot receipt differs');
  const snapshots = await readJsonLines<{ contract: TimedPriceContract; quote: SnapshotEvidence }>(snapshotFile, 100000);
  if (!snapshots.length || snapshots.some((s, i) => s.quote.knownAt >= registered.finalFrom || (i > 0 && s.quote.knownAt < snapshots[i - 1].quote.knownAt))) throw new Error('reserved or unordered snapshots');
  const fees: PaperFeeTerms = { basis: 'assumed-schedule', knownAt: Date.now(), effectiveFrom: 0,
    schedule: { ...DEFAULT_FEES, balancePrecision: 0.01, takerRate: 0.07, makerRate: 0.0175 }, sourceSha256: digest(DEFAULT_FEES) };
  const variants = [
    { key: 'base', model: 'geometry-prior' }, { key: 'base', model: 'continuous-context' },
    { key: 'S5', model: 'continuous-context-S5' }, { key: 'S6', model: 'continuous-context-S6' },
  ];
  const settings = [ { name: 'any-positive-fee-net', targetContractRoi: 0 },
    ...[0.05, 0.1, 0.25].map((targetContractRoi) => ({ name: `contract-${targetContractRoi}`, targetContractRoi })),
    ...[0.05, 0.1, 0.25].map((targetUnderlyingReturn) => ({ name: `underlying-${targetUnderlyingReturn}`, targetContractRoi: 0, targetUnderlyingReturn })) ];
  const basePolicy: DirectionPaperPolicy = { startingCash: 200, maximumPositionCost: 20, maximumContracts: 40, maximumOpenPositions: 8,
    minimumNetTakeUsd: 0.01, targetContractRoi: 0, minimumSignalProbability: 0.6, maximumQuoteAgeMs: 2000, maximumSignalAgeMs: 2000, saleBufferMs: profit.saleBufferMs };
  const registration = { schema: 'atlas-direction-cash-paper-v1', policy: registered, plan, basePolicy, settings, fees,
    fixedBeforeReadingMovementOutcomes: true, onlyPredictorPointProbabilityUsedForExploratoryEntry: true,
    historicalCounterfactual: true, qualification: 'Research-only; point probability >= 0.60 is not a verified win rate',
    sourceSnapshotSha256: receipt.snapshots.sha256, sourceNativeSummarySha256: await sha256File(path.join(o.native, 'summary.json')) };
  fs.writeFileSync(path.join(root, 'registration.json'), JSON.stringify(registration, null, 2) + '\n');
  const reports = [];
  for (const v of variants) {
    const model = JSON.parse(fs.readFileSync(path.join(o.native, v.key, `${v.model}.json`), 'utf8')) as AdvanceModel;
    validateAdvanceModel(model);
    const dataset = path.join(root, `snapshot-dataset-${v.key}`);
    if (!fs.existsSync(dataset)) await assembleMovementDataset(path.join(o.native, v.key, 'snapshot-inputs/spec.json'), o.policy, dataset);
    const data = await loadMovementDataset(dataset, profit), signals = new Map<string, DirectionPaperSignal[]>();
    const counts = { observations: 0, unsupported: 0, unavailableInputs: 0, predicted: 0 };
    for (const e of data.examples) {
      const observation = e.observation, at = observation.query.asOf; counts.observations++;
      // No future outcome/status is consulted here. Gappy labels can still produce
      // a causal forecast, and must not be removed from the paper account's cohort.
      if (at < plan.selection.from || observation.event.thresholdAtr !== 0.25) continue;
      if (!advanceModelSupports(model, observation, e.byAt, profit)) { counts.unsupported++; continue; }
      const x = encodeAdvanceMovement(observation, e.byAt, profit);
      if (missingRequiredInputs(model, x).length) { counts.unavailableInputs++; continue; }
      const p = binaryResponseProbability(model.head, model.featureNames.map((n) => x[n] ?? NaN));
      const key = `${observation.query.asset}:${at}:${e.byAt}`, list = signals.get(key) ?? [];
      list.push({ id: observation.id, modelId: model.id, asOf: at, producedAt: at, featuresKnownAt: observation.query.featuresKnownAt,
        byAt: e.byAt, direction: observation.event.direction, probability: p }); signals.set(key, list); counts.predicted++;
    }
    for (const setting of settings) {
      const policy = { ...basePolicy, ...setting }, account = new DirectionPaperAccount(policy, profit, snapshots[0].quote.knownAt);
      let observed = 0;
      for (const s of snapshots) {
        if (s.quote.knownAt < plan.selection.from) continue; observed++;
        const key = `${s.contract.asset}:${s.quote.knownAt}:${s.contract.closeTime - profit.saleBufferMs}`;
        const choices = [...(signals.get(key) ?? [])].sort((a, b) => b.probability - a.probability);
        const signal = choices.length && (choices.length === 1 || choices[0].probability > choices[1].probability) ? choices[0] : null;
        await account.observe(s.contract, s.quote, fees, signal);
      }
      const report = { model: v.model, modelId: model.id, setting, observedSnapshots: observed, forecastCounts: counts, ...account.report(),
        underlyingThresholdSales: [0.05, 0.1, 0.25].map((threshold) => ({ threshold, count: account.sales.filter((s) => s.underlyingMoveBps !== null &&
          Number(s.underlyingMoveBps) * (s.direction === 'up' ? 1 : -1) >= threshold * 10000).length })) };
      const prefix = path.join(root, `${v.model}-${setting.name}`);
      fs.writeFileSync(`${prefix}-report.json`, JSON.stringify(report, null, 2) + '\n');
      fs.writeFileSync(`${prefix}-sales.jsonl`, account.sales.map((s) => JSON.stringify(s)).join('\n') + '\n');
      fs.writeFileSync(`${prefix}-fills.jsonl`, account.fills.map((s) => JSON.stringify(s)).join('\n') + '\n');
      reports.push(report);
    }
  }
  const summary = { ...registration, reports, researchOnly: true, liveEntryAllowed: false, autoPromote: false, actualVenueProfitVerified: false,
    limitations: ['Historical snapshot-taker simulation, not observed private fills or a forward paper trial',
      'Published standard fees are explicit assumptions; archived per-series as-of fee schedules were not present',
      'Snapshot-only coverage cannot certify an exit between snapshots; missing exits retain cash-funded unresolved exposure',
      'No automatic depth replenishment, bankroll refills, settlement payouts or imputed contract prices',
      'Underlying direction alone does not guarantee contract mark-up after spread, remaining-time decay and fees'] };
  fs.writeFileSync(path.join(root, 'summary.json'), JSON.stringify(summary, null, 2) + '\n'); return summary;
}
const arg = (name: string, fallback = '') => { const i = process.argv.indexOf(`--${name}`); return i < 0 ? fallback : process.argv[i + 1]; };
if (process.argv[1] && /(^|[/\\])runDirectionPaperStudy\.(ts|js)$/.test(process.argv[1])) void runDirectionPaperStudy({ native: arg('native'), snapshots: arg('snapshots'), out: arg('out'),
  policy: arg('policy', 'research/opportunity/examples/profit-policy.json') }).then(() => console.log('Cash paper study saved; no live orders.'))
  .catch((e) => { console.error(e instanceof Error ? e.stack : e); process.exitCode = 1; });
