/** Fixed exploratory family comparison on one already-exported historical dataset. */
import fs from 'node:fs';
import path from 'node:path';
import { exportJointPathStudy } from './jointPathCli';
import { studyPolicy } from './studyPolicy';

export async function runHistoryComparison(options: { dataset: string; out: string; policyId: string; mlpEngine: 'ts' | 'torch' | 'auto' }) {
  const root = path.resolve(options.out), policy = studyPolicy(options.policyId);
  if (fs.existsSync(root)) throw new Error('new comparison output required');
  fs.mkdirSync(root, { recursive: true });
  const plan = { expanding: false, trainMs: 90 * 86400000, stoppingMs: 30 * 86400000, calibrationMs: 30 * 86400000,
    evaluationMs: 30 * 86400000, stepMs: 400 * 86400000, maxFolds: 9, embargoMs: 3600000 };
  const smoothParams = { hidden: 8, l2: 0.002, lr: 0.015, maxEpochs: 100, patience: 20, seed: 17, residual: -1 };
  fs.writeFileSync(path.join(root, 'registration.json'), JSON.stringify({ policy, plan, families: ['trees', 'smooth'], smoothParams,
    treeParams: { nTrees: 16, maxDepth: 3 }, maximumRiskHorizonMinutes: 15, declaredBeforeThisComparison: true,
    researchOnly: true, liveEntryAllowed: false, autoPromote: false,
    purpose: 'Exploratory same-period family comparison on development eras; neither family is qualified or selected on a final holdout' }, null, 2) + '\n');
  const reports = [];
  for (const family of ['trees', 'smooth'] as const) reports.push(await exportJointPathStudy({ datasetDir: options.dataset,
    outDir: path.join(root, family), studyPolicyId: policy.id, plan, family, mlpEngine: options.mlpEngine, smoothParams,
    params: { nTrees: 16, maxDepth: 3 }, maxHorizonMin: 15, maxDecisions: 20000, maxPaths: 500000, onProgress: console.log }));
  const [trees, smooth] = reports;
  if (trees.dataset.manifestSha256 !== smooth.dataset.manifestSha256 || trees.folds.length !== smooth.folds.length) throw new Error('comparison datasets or fitted fold counts differ');
  const folds = trees.folds.map((t, i) => {
    const s = smooth.folds[i];
    if (JSON.stringify(t.fold) !== JSON.stringify(s.fold) || t.evaluationEpisodes !== s.evaluationEpisodes) throw new Error('comparison evaluation rows differ');
    return { fold: t.fold, evaluationEpisodes: t.evaluationEpisodes, treesLogLoss: t.modelLoss, smoothLogLoss: s.modelLoss,
      treesBrier: t.brier, smoothBrier: s.brier, smoothMinusTreesLoss: s.modelLoss - t.modelLoss };
  });
  const report = { policy, dataset: trees.dataset, folds, smoothBackend: smooth.backend,
    status: folds.length ? 'exploratory-family-comparison' : 'blocked-insufficient-history-or-rows',
    selectedFamily: null, researchOnly: true, liveEntryAllowed: false, autoPromote: false,
    interpretation: 'Descriptive development-period comparison only. No economic, SNN, conditional-retention or final-holdout qualification.' };
  fs.writeFileSync(path.join(root, 'summary.json'), JSON.stringify(report, null, 2) + '\n');
  return report;
}
const arg = (name: string, fallback: string) => { const i = process.argv.indexOf(`--${name}`); return i < 0 ? fallback : process.argv[i + 1]; };
if (process.argv[1] && /(^|[/\\])runHistoryComparison\.(ts|js)$/.test(process.argv[1])) void runHistoryComparison({
  dataset: arg('dataset', 'research/out/atlas-history-study/dataset'), out: arg('out', 'research/out/atlas-history-comparison'),
  policyId: arg('study-policy', studyPolicy().id), mlpEngine: arg('mlp-engine', 'torch') as 'ts' | 'torch' | 'auto' })
  .then((r) => console.log(`${r.status}; ${r.folds.length} folds; no promotion or live trading.`))
  .catch((e) => { console.error(e instanceof Error ? e.message : e); process.exitCode = 1; });
