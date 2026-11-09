/** Atomic research-only fit/export. No live model paths or promotion hooks. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { loadJointPathDataset, sha256File } from './jointPathData';
import { DEFAULT_FOLD_PLAN, JOINT_PATH_SCHEMA, trainJointPaths, type FoldPlan } from './jointPathLearner';
import type { GbdtParams } from '../gbdt';
import { studyPolicy } from './studyPolicy';

function realOutput(file: string) {
  const tail: string[] = []; let cursor = path.resolve(file);
  while (!fs.existsSync(cursor)) { tail.unshift(path.basename(cursor)); cursor = path.dirname(cursor); }
  return path.join(fs.realpathSync(cursor), ...tail);
}
export async function exportJointPathStudy(o: { datasetDir: string; outDir: string; smokeTest?: boolean; plan?: FoldPlan;
  studyPolicyId?: string;
  params?: Partial<GbdtParams>; maxHorizonMin?: number; maxDecisions?: number; maxPaths?: number; maxRiskRows?: number;
  onProgress?: (message: string) => void }) {
  const input = fs.realpathSync(o.datasetDir), out = realOutput(o.outDir), rel = path.relative(input, out);
  if (rel === '' || (!rel.startsWith(`..${path.sep}`) && rel !== '..' && !path.isAbsolute(rel))) throw new Error('study output must be outside the dataset');
  if (fs.existsSync(out)) throw new Error('study output already exists');
  const repo = fileURLToPath(new URL('../../', import.meta.url)), codeHashes: Record<string, string> = {};
  for (const name of ['research/opportunity/jointPathData.ts', 'research/opportunity/jointPathLearner.ts', 'research/opportunity/jointPathCli.ts',
    'research/opportunity/studyPolicy.ts', 'research/gbdt.ts', 'research/stats.ts', 'bot/model/trees.ts', 'bot/model/calibration.ts', 'bot/util/num.ts']) codeHashes[name] = await sha256File(path.join(repo, name));
  const data = await loadJointPathDataset(input, o);
  const fitted = await trainJointPaths(data, o);
  for (const [name, hash] of Object.entries(data.inputHashes)) if (await sha256File(path.join(input, name)) !== hash) throw new Error('dataset changed during fit');
  for (const [name, hash] of Object.entries(codeHashes)) if (await sha256File(path.join(repo, name)) !== hash) throw new Error('learner code changed during fit');
  fs.mkdirSync(path.dirname(out), { recursive: true });
  const staging = `${out}.${randomUUID()}.tmp`; fs.mkdirSync(staging);
  try {
    const folds = [];
    for (const [i, { model, baseline, ...metrics }] of fitted.folds.entries()) {
      const artifacts: Record<string, { file: string; sha256: string; modelId: string }> = {};
      for (const [kind, artifact] of [['joint', model], ['geometry', baseline]] as const) {
        const file = `fold-${i + 1}-${kind}.json`;
        fs.writeFileSync(path.join(staging, file), JSON.stringify(artifact) + '\n');
        artifacts[kind] = { file, sha256: await sha256File(path.join(staging, file)), modelId: artifact.id };
      }
      folds.push({ ...metrics, artifacts });
    }
    const report = { ...fitted, folds, createdAt: new Date().toISOString(), codeHashes };
    fs.writeFileSync(path.join(staging, 'report.json'), JSON.stringify(report, null, 2) + '\n');
    if (fs.existsSync(out)) throw new Error('study output appeared during fitting');
    fs.renameSync(staging, out); return report;
  } catch (error) { fs.rmSync(staging, { recursive: true, force: true }); throw error; }
}
function arg(name: string, fallback: string) { const i = process.argv.indexOf(`--${name}`); return i < 0 ? fallback : process.argv[i + 1] ?? fallback; }
async function main() {
  const smokeTest = process.argv.includes('--smoke-test'), day = 86400000;
  const report = await exportJointPathStudy({ datasetDir: path.resolve(arg('dataset', 'research/out/opportunity-decisions')),
    studyPolicyId: arg('study-policy', studyPolicy().id),
    outDir: path.resolve(arg('out', 'research/out/opportunity-joint-study')), smokeTest,
    params: { nTrees: Number(arg('trees', '48')), maxDepth: Number(arg('depth', '3')) },
    maxHorizonMin: Number(arg('max-horizon-min', '60')), maxDecisions: Number(arg('max-decisions', '20000')),
    maxPaths: Number(arg('max-paths', '500000')), maxRiskRows: Number(arg('max-risk-rows', '200000')),
    plan: smokeTest ? undefined : { ...DEFAULT_FOLD_PLAN, expanding: !process.argv.includes('--rolling'), trainMs: Number(arg('train-days', '3')) * day,
      stoppingMs: Number(arg('stopping-days', '1')) * day, calibrationMs: Number(arg('calibration-days', '1')) * day,
      evaluationMs: Number(arg('evaluation-days', '1')) * day, stepMs: Number(arg('step-days', '1')) * day,
      embargoMs: Number(arg('embargo-minutes', '60')) * 60000, maxFolds: Number(arg('folds', '8')) },
    onProgress: console.log });
  console.log(`${JOINT_PATH_SCHEMA}: ${report.status}; ${report.folds.length} fitted folds. Research only; no live entry or calibration approval.`);
}
if (process.argv[1] && /(^|[/\\])jointPathCli\.(ts|js)$/.test(process.argv[1])) void main().catch((e) => { console.error(e); process.exitCode = 1; });
