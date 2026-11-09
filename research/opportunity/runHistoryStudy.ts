/** Heavy research orchestration, intended for GitHub runners. Never imports an order client. */
import fs from 'node:fs';
import path from 'node:path';
import { exportDecisionDataset } from './decisionDatasetCli';
import { exportJointPathStudy } from './jointPathCli';
import { studyPolicy } from './studyPolicy';

export async function runHistoryStudy(options: { archive: string; out: string; policyId: string; spacing: number }) {
  const policy = studyPolicy(options.policyId), root = path.resolve(options.out);
  if (fs.existsSync(root) || !Number.isSafeInteger(options.spacing) || options.spacing < 60 || options.spacing > 10080) throw new Error('new output and valid predetermined spacing required');
  fs.mkdirSync(root, { recursive: true });
  const plan = { expanding: false, trainMs: 90 * 86400000, stoppingMs: 30 * 86400000, calibrationMs: 30 * 86400000,
    evaluationMs: 30 * 86400000, stepMs: 400 * 86400000, maxFolds: 9, embargoMs: 3600000 };
  fs.writeFileSync(path.join(root, 'registration.json'), JSON.stringify({ policy, spacing: options.spacing, plan,
    declaredBeforeLabels: true, targetsAtr: [1], stopsAtr: [1], maximumRiskHorizonMinutes: 15,
    researchOnly: true, liveEntryAllowed: false, autoPromote: false,
    purpose: 'Exploratory spot-path learning across archived eras; not official settlement/SNN/executed-profit qualification' }, null, 2) + '\n');
  const dataset = await exportDecisionDataset({ archiveDir: options.archive, outDir: path.join(root, 'dataset'), source: 'archive-binance-1m-quarantined-v1',
    assets: ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE'], studyPolicyId: policy.id, maxMinutes: 6000000, everyMinutes: options.spacing,
    path: { horizonsMin: [5, 15, 60, 240, 1440], targetsAtr: [1], stopsAtr: [1], costs: { feePerSideBps: 2, halfSpreadBps: 0.5, slippagePerSideBps: 1 } }, onProgress: console.log });
  const fit = await exportJointPathStudy({ datasetDir: path.join(root, 'dataset'), outDir: path.join(root, 'trees'), studyPolicyId: policy.id,
    plan, params: { nTrees: 16, maxDepth: 3 }, maxHorizonMin: 15, maxDecisions: 20000, maxPaths: 500000, onProgress: console.log });
  const report = { policy, dataset: { runId: dataset.runId, assets: dataset.assets, outputs: dataset.outputs },
    status: fit.status, folds: fit.folds, weeklyEvidence: fit.weeklyEvidence, researchOnly: true, liveEntryAllowed: false, autoPromote: false };
  fs.writeFileSync(path.join(root, 'summary.json'), JSON.stringify(report, null, 2) + '\n');
  return report;
}
const arg = (name: string, fallback: string) => { const i = process.argv.indexOf(`--${name}`); return i < 0 ? fallback : process.argv[i + 1]; };
if (process.argv[1] && /(^|[/\\])runHistoryStudy\.(ts|js)$/.test(process.argv[1])) void runHistoryStudy({ archive: arg('archive', 'data/opportunity-laptop-quarantined-v1'),
  out: arg('out', 'research/out/atlas-history-study'), policyId: arg('study-policy', studyPolicy().id), spacing: Number(arg('every-minutes', '1441')) })
  .then((r) => console.log(`Research ${r.status}; ${r.folds.length} folds. No promotion or live trading.`))
  .catch((e) => { console.error(e instanceof Error ? e.message : e); process.exitCode = 1; });
