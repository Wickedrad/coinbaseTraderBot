/** Bounded observed-recording study, built and fitted on a GitHub runner. No order client. */
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { recordSnnTape } from '../snnTape';
import { domainParams } from '../../bot/snn/params';
import { recordingFiles } from '../../bot/marketdata/recordingFiles';
import { replayAtlasSnnTape } from './snnReplay';
import { combineSnnStates, type AtlasSnnState } from './snnState';
import { sha256File } from './jointPathData';
import { studyPolicy } from './studyPolicy';
import { assembleContractDataset, exportContractStudy, exportPaperShadow, exportRecordingInputs, exportSnnComparison,
  loadContractDataset, type AssemblySpec, type RecordedDecision } from './productCli';
import type { RecordingImportOptions } from './recordingImport';

async function* decisions(file: string) {
  const stream = fs.createReadStream(file), reader = readline.createInterface({ input: stream, crlfDelay: Infinity });
  try { for await (const line of reader) if (line) yield JSON.parse(line) as RecordedDecision; }
  finally { reader.close(); stream.destroy(); }
}
export async function runRecordingStudy(o: { recordings: string; config: string; plan: string; paperPolicy: string; out: string }) {
  const root = path.resolve(o.out), config = JSON.parse(fs.readFileSync(o.config, 'utf8')) as RecordingImportOptions;
  const policy = studyPolicy(config.studyPolicyId), plan = JSON.parse(fs.readFileSync(o.plan, 'utf8'));
  if (fs.existsSync(root)) throw new Error('new recording-study output required');
  fs.mkdirSync(root, { recursive: true });
  const parameters = { epochs: 40, hidden: 6, trees: 12, seed: 17 };
  fs.writeFileSync(path.join(root, 'registration.json'), JSON.stringify({ policy, config,
    plan, parameters, declaredBeforeLabels: true,
    snnReplayPolicy: { domains: ['crypto', 'perps'], maximumInputPriceAgeMs: 3000, maximumInputGapMs: 3000, roundedInputLagMs: 1000 },
    purpose: 'Observed bounded-prefix engineering and exploratory study, not complete-archive or live replay qualification',
    researchOnly: true, liveEntryAllowed: false, autoPromote: false }, null, 2) + '\n');
  const receiptDays = new Set<string>();
  for (const name of fs.readdirSync(o.recordings).filter((n) => /^public-\d{4}-\d{2}-\d{2}\.json$/.test(n))) {
    const report = JSON.parse(fs.readFileSync(path.join(o.recordings, name), 'utf8'));
    const day = name.slice(7, 17), file = path.join(o.recordings, `md-${day}.jsonl.gz`);
    if (report.observed_only !== true || report.book_every_ms !== 0 || report.last_arrival >= policy.finalFrom ||
        await sha256File(file) !== report.filtered_sha256) throw new Error('unverified, sampled-book, changed or final-period prefix cannot enter this development study');
    receiptDays.add(day);
    fs.copyFileSync(path.join(o.recordings, name), path.join(root, name));
  }
  if (!receiptDays.size || recordingFiles(o.recordings).some((f) => !receiptDays.has(f.day))) throw new Error('all study recordings require an observed-prefix receipt');
  const base = path.join(root, 'base');
  console.log('Importing observed arrivals, native candles and exact contract geometry');
  const imported = await exportRecordingInputs(o.recordings, o.config, path.join(base, 'inputs'));
  const baseSpecFile = path.join(base, 'inputs/spec.json');
  const assembled = await assembleContractDataset(baseSpecFile, path.join(base, 'dataset'));
  console.log(`Base contract dataset: ${assembled.counts.complete} complete of ${assembled.counts.observations}`);
  const study = await exportContractStudy(path.join(base, 'dataset'), o.plan, o.paperPolicy, path.join(base, 'study'), parameters);
  const desiredSeconds = new Set<number>();
  for await (const d of decisions(path.join(base, 'inputs/decisions.jsonl'))) desiredSeconds.add(Math.floor(d.asOf! / 1000) * 1000);
  const snapshots: Record<string, Map<number, AtlasSnnState>> = {}, replayReports = [];
  const domainStates: Record<string, Record<string, Map<number, AtlasSnnState>>> = {};
  for (const domain of ['crypto', 'perps'] as const) {
    const tape = path.join(root, `observed-${domain}.tape`); domainStates[domain] = {};
    console.log(`Recording the existing ${domain} SNN input mapping on observed prefixes`);
    await recordSnnTape(o.recordings, tape, { params: domainParams(domain), domain, lean: true,
      skipModel: true, fromDay: config.fromDay, toDay: config.toDay, scoreEverySec: 60, assetEverySec: 5, maximumInputPriceAgeMs: 3000 });
    const tapeHash = await sha256File(tape);
    for (const variant of ['S5', 'S6'] as const) {
      const selected = new Map<number, AtlasSnnState>(); domainStates[domain][variant] = selected;
      console.log(`Replaying ${domain} ${variant}; weights freeze at ${new Date(policy.trainBefore).toISOString()}`);
      replayReports.push(replayAtlasSnnTape(tape, { variant, domain, sourceSha256: tapeHash, studyPolicyId: policy.id,
        everyMs: 1000, maximumInputPriceAgeMs: 3000, captureAt: desiredSeconds, params: domainParams(domain),
        onState: (state) => selected.set(state.asOf, state) }));
    }
  }
  for (const variant of ['S5', 'S6'] as const) {
    const selected = new Map<number, AtlasSnnState>(); snapshots[variant] = selected;
    for (const second of [...desiredSeconds].sort((a, b) => a - b)) {
      const states = ['crypto', 'perps'].map((domain) => domainStates[domain][variant].get(second));
      if (states.every((s) => s !== undefined)) selected.set(second, combineSnnStates(states as AtlasSnnState[]));
    }
    fs.writeFileSync(path.join(root, `states-${variant}.jsonl`), [...selected.values()].map((s) => JSON.stringify(s)).join('\n') + '\n');
  }
  const spec = JSON.parse(fs.readFileSync(baseSpecFile, 'utf8')) as AssemblySpec;
  const variants = [];
  for (const variant of ['S5', 'S6'] as const) {
    const dir = path.join(root, variant), inputs = path.join(dir, 'inputs'); fs.mkdirSync(inputs, { recursive: true });
    for (const receipt of [...spec.indices, ...(spec.results ? [spec.results] : [])]) fs.linkSync(path.join(base, 'inputs', receipt.file), path.join(inputs, receipt.file));
    const file = path.join(inputs, 'decisions.jsonl'), fd = fs.openSync(file, 'wx'); let missingSnn = 0;
    try { for await (const d of decisions(path.join(base, 'inputs/decisions.jsonl'))) {
      const second = Math.floor(d.asOf! / 1000) * 1000;
      if (!snapshots.S5.has(second) || !snapshots.S6.has(second)) { missingSnn++; continue; }
      fs.writeSync(fd, JSON.stringify({ ...d, snn: { ...snapshots[variant].get(second)!, asOf: d.asOf } }) + '\n');
    } } finally { fs.closeSync(fd); }
    const changed = { ...spec, decisions: { file: 'decisions.jsonl', sha256: await sha256File(file) } };
    fs.writeFileSync(path.join(inputs, 'spec.json'), JSON.stringify(changed, null, 2) + '\n');
    const dataset = await assembleContractDataset(path.join(inputs, 'spec.json'), path.join(dir, 'dataset'));
    const fitted = await exportContractStudy(path.join(dir, 'dataset'), o.plan, o.paperPolicy, path.join(dir, 'study'), parameters);
    variants.push({ variant, missingSnn, dataset: dataset.counts, status: fitted.status, blockers: fitted.blockers, productId: fitted.productId });
  }
  const products = ['S5', 'S6'].map((v) => JSON.parse(fs.readFileSync(path.join(root, v, 'study/product.json'), 'utf8')));
  const comparison = products.every((p) => p.study.selected && p.study.baseline)
    ? await exportSnnComparison(path.join(root, 'S5/study/product.json'), path.join(root, 'S5/dataset'),
      path.join(root, 'S6/study/product.json'), path.join(root, 'S6/dataset'), path.join(root, 'comparison'))
    : { status: 'blocked-insufficient-contract-rows', recommended: 'none', liveEntryAllowed: false };
  const data = await loadContractDataset(path.join(base, 'dataset'));
  const requests = path.join(root, 'paper-requests.jsonl');
  fs.writeFileSync(requests, data.examples.filter((e) => e.observation.query.asOf >= plan.audit.through)
    .map((e) => JSON.stringify({ observation: e.observation, quote: e.quote ?? null, position: null,
      allowance: { riskApprovedQuantity: 1, remainingRiskDollars: 1 } })).join('\n') + '\n');
  const shadow = await exportPaperShadow(path.join(base, 'study/product.json'), requests, o.paperPolicy, path.join(root, 'paper-shadow'), 86400000, 'historical-audit');
  const report = { policy, imported, dataset: assembled.counts, base: { status: study.status, blockers: study.blockers, productId: study.productId },
    replayReports, variants, comparison, shadow, researchOnly: true, liveEntryAllowed: false, autoPromote: false,
    limitations: ['Bounded prefixes cover selected hours, not full days or all recorded data',
      'Post-audit paper queries use explicit historical-audit mode and are not prospective forecasts made before their outcomes',
      'Source arrival and original websocket gap fidelity still require independent verification',
      'Missing SNN input intervals clear transients and pending labels while preserving weights; no unobserved market paths are synthesized',
      'Fresh forward-paper observations and independent weeks remain required; this job cannot qualify live trading'] };
  fs.writeFileSync(path.join(root, 'summary.json'), JSON.stringify(report, null, 2) + '\n');
  return report;
}
const arg = (name: string, fallback: string) => { const i = process.argv.indexOf(`--${name}`); return i < 0 ? fallback : process.argv[i + 1]; };
if (process.argv[1] && /(^|[/\\])runRecordingStudy\.(ts|js)$/.test(process.argv[1])) void runRecordingStudy({
  recordings: arg('recordings', 'research/out/atlas-recordings'), config: arg('config', 'research/opportunity/examples/prospective-prefix-import.json'),
  plan: arg('plan', 'research/opportunity/examples/prospective-prefix-plan.json'), paperPolicy: arg('paper-policy', 'research/opportunity/examples/paper-policy.json'),
  out: arg('out', 'research/out/atlas-recording-study') })
  .then((r) => console.log(`Recording study ${r.base.status}; SNN recommendation ${r.comparison.recommended}; no promotion.`))
  .catch((e) => { console.error(e instanceof Error ? e.stack : e); process.exitCode = 1; });
