/** Transactional offline dataset export; no input files or production models are written. */
import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { buildDecisionDataset, DECISION_DATASET_SCHEMA, DECISION_PATH_SCHEMA, type DecisionDatasetOptions } from './decisionDataset';
import { hashFile } from './featuresCli';
import { PATH_LABEL_SCHEMA } from './pathLabels';
import { studyPolicy } from './studyPolicy';

function prospectiveRealPath(file: string): string {
  const tail: string[] = [];
  let cursor = path.resolve(file);
  while (!fs.existsSync(cursor)) { tail.unshift(path.basename(cursor)); cursor = path.dirname(cursor); }
  return path.join(fs.realpathSync(cursor), ...tail);
}
export async function exportDecisionDataset(o: DecisionDatasetOptions & { outDir: string }) {
  const input = fs.realpathSync(o.archiveDir), out = prospectiveRealPath(o.outDir), rel = path.relative(input, out);
  if (rel === '' || (!rel.startsWith(`..${path.sep}`) && rel !== '..' && !path.isAbsolute(rel))) throw new Error('dataset output must be outside the input archive');
  if (fs.existsSync(out)) throw new Error('dataset output already exists; select a new directory');
  fs.mkdirSync(path.dirname(out), { recursive: true });
  const staging = `${out}.${randomUUID()}.tmp`, runId = randomUUID();
  fs.mkdirSync(staging);
  let decisions: Awaited<ReturnType<typeof fs.promises.open>> | undefined;
  let labels: typeof decisions;
  try {
    const decisionsFile = path.join(staging, 'decisions.jsonl'), labelsFile = path.join(staging, 'paths.jsonl');
    decisions = await fs.promises.open(decisionsFile, 'wx'); labels = await fs.promises.open(labelsFile, 'wx');
    const metadata = { type: 'metadata', schema: DECISION_DATASET_SCHEMA, runId, manifest: 'manifest.json', researchOnly: true,
      liveEntryAllowed: false, labelsSchema: DECISION_PATH_SCHEMA, labelDefinitionSchema: PATH_LABEL_SCHEMA, joinKey: 'decisionId / entry.decisionId' };
    let decisionBuffer = JSON.stringify({ ...metadata, stream: 'decisions' }) + '\n';
    let labelBuffer = JSON.stringify({ ...metadata, stream: 'paths' }) + '\n';
    const report = await buildDecisionDataset({ ...o,
      async onDecision(row) {
        decisionBuffer += JSON.stringify(row) + '\n';
        if (decisionBuffer.length >= 1048576) { await decisions!.writeFile(decisionBuffer); decisionBuffer = ''; }
        await o.onDecision?.(row);
      },
      async onLabels(rows) {
        for (const row of rows) {
          const { schema: labelDefinitionSchema, ...values } = row;
          labelBuffer += JSON.stringify({ type: 'path-label', schema: DECISION_PATH_SCHEMA, labelDefinitionSchema, ...values }) + '\n';
          if (labelBuffer.length >= 1048576) { await labels!.writeFile(labelBuffer); labelBuffer = ''; }
        }
        await o.onLabels?.(rows);
      },
    });
    if (decisionBuffer) await decisions.writeFile(decisionBuffer);
    if (labelBuffer) await labels.writeFile(labelBuffer);
    await decisions.close(); decisions = undefined; await labels.close(); labels = undefined;
    const manifest = { ...report, runId, outputs: {
      decisions: { file: 'decisions.jsonl', sha256: await hashFile(decisionsFile), rows: report.assets.reduce((s, a) => s + a.decisions, 0) },
      paths: { file: 'paths.jsonl', sha256: await hashFile(labelsFile), rows: report.assets.reduce((s, a) => s + a.labels, 0) },
    } };
    fs.writeFileSync(path.join(staging, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
    if (fs.existsSync(out)) throw new Error('dataset output appeared during export; refusing to replace it');
    fs.renameSync(staging, out);
    return manifest;
  } catch (error) {
    await decisions?.close(); await labels?.close(); fs.rmSync(staging, { recursive: true, force: true }); throw error;
  }
}
function arg(name: string, fallback: string) { const i = process.argv.indexOf(`--${name}`); return i < 0 ? fallback : process.argv[i + 1] ?? fallback; }
async function main() {
  const policy = studyPolicy(arg('study-policy', studyPolicy().id));
  const report = await exportDecisionDataset({ archiveDir: path.resolve(arg('archive', 'data/opportunity-archive')),
    outDir: path.resolve(arg('out', 'research/out/opportunity-decisions')), assets: arg('assets', 'BTC,ETH').split(',').map((s) => s.trim().toUpperCase()),
    source: arg('source', 'binance-1m'),
    maxMinutes: Number(arg('max-minutes', '1500')), everyMinutes: Number(arg('every-minutes', '1')),
    studyPolicyId: policy.id, trainBefore: Date.parse(arg('train-before', new Date(policy.trainBefore).toISOString())), finalFrom: Date.parse(arg('final-from', new Date(policy.finalFrom).toISOString())),
    path: { horizonsMin: arg('horizons-min', '5,15,60,240,1440').split(',').map(Number),
      targetsAtr: arg('targets-atr', '1').split(',').map(Number), stopsAtr: arg('stops-atr', '1').split(',').map(Number),
      costs: { feePerSideBps: Number(arg('fee-bps', '0')), halfSpreadBps: Number(arg('half-spread-bps', '0')), slippagePerSideBps: Number(arg('slippage-bps', '0')) } },
    onProgress: console.log });
  console.log(`Exported ${report.outputs.decisions.rows} decisions and ${report.outputs.paths.rows} spot-path labels. Final outcomes withheld; no fitting or live changes.`);
}
if (process.argv[1] && /(^|[/\\])decisionDatasetCli\.(ts|js)$/.test(process.argv[1])) void main().catch((e) => { console.error(e); process.exitCode = 1; });
