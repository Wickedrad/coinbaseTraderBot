/** Complete offline workflow. Outputs are new files under research/out or /tmp only. */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import readline from 'node:readline';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { buildContractObservation, CONTRACT_DATASET_SCHEMA, CONTRACT_LABEL_SCHEMA, encodeContractObservation, freezeIndexEvidence, labelContract,
  type ContractObservation, type ContractOutcome, type IndexEvidence, type OfficialPrint, type TimelyMoveDefinition } from './contractDataset';
import type { AtlasFeatureFrame, MinuteEntryAnchor } from './features';
import type { AtlasSnnState } from './snnState';
import type { TimedPriceContract } from './contractTiming';
import { FROZEN_FINAL_FROM, sha256File } from './jointPathData';
import { contractRows, type ContractExample, type ContractFitOptions, type ContractStudyPlan } from './contractLearner';
import { runContractStudy } from './contractStudy';
import { AtlasRegistry, createAtlasProduct, type AtlasProduct } from './registry';
import { evaluatePaperPosition, type PaperPolicy, type PaperPosition, type PaperQuote } from './paper';
import { replayAtlasSnnTape } from './snnReplay';
import { writeRecordingInputs, type RecordingImportOptions } from './recordingImport';
import { compareSnnStudies, qualifySnnStudy } from './snnComparison';
import { writeProductDemoInputs } from './demo';
import { studyPolicy } from './studyPolicy';

const repo = fileURLToPath(new URL('../../', import.meta.url));
interface Receipt { file: string; sha256: string }
export interface AssemblySpec {
  studyPolicyId?: string;
  schema: 'opportunity-recording-spec-v1'; knownBy: number;
  indices: Array<Receipt & { asset: string; reference: string; basis: IndexEvidence['basis'] }>;
  decisions: Receipt; results?: Receipt;
}
export interface RecordedDecision {
  frame: AtlasFeatureFrame; contract: TimedPriceContract; event: TimelyMoveDefinition; side: 'yes' | 'no';
  executionBufferMs: number; asOf?: number; snn?: AtlasSnnState | null; quote?: PaperQuote;
  anchor?: MinuteEntryAnchor | null;
  termsBasis?: ContractObservation['termsBasis'];
}
interface DatasetManifest {
  studyPolicyId?: string;
  schema: typeof CONTRACT_DATASET_SCHEMA; researchOnly: true; finalOutcomesWithheld: true;
  inputs: Record<string, string>; codeHashes: Record<string, string>; outputs: { examples: Receipt }; counts: Record<string, number>;
}
function realDestination(file: string) {
  const tail: string[] = []; let cursor = path.resolve(file);
  while (!fs.existsSync(cursor)) { tail.unshift(path.basename(cursor)); cursor = path.dirname(cursor); }
  return path.join(fs.realpathSync(cursor), ...tail);
}
function newDestination(file: string) {
  const dest = realDestination(file), allowed = [path.join(repo, 'research/out'), fs.realpathSync(os.tmpdir())];
  if (!allowed.some((root) => dest.startsWith(root + path.sep)) || fs.existsSync(dest)) throw new Error('output must be a new path under research/out or the system temporary directory');
  return dest;
}
export async function codeHashes() {
  const names = new Set(['package.json', 'package-lock.json', 'tsconfig.json', 'research/mlp.ts', 'research/gbdt.ts', 'research/stats.ts', 'research/snnTape.ts', 'research/snnReplay.ts', 'research/replay.ts',
    'bot/fees.ts', 'bot/kalshi/feeSchedule.ts', 'bot/risk/quotaPacer.ts', 'bot/strategy/fairValueStrategy.ts', 'bot/paper/paperExchange.ts']);
  for (const dir of ['research/opportunity', 'research/history', 'bot/snn', 'bot/ta', 'bot/model', 'bot/util', 'bot/marketdata'])
    for (const name of fs.readdirSync(path.join(repo, dir))) if (name.endsWith('.ts') || name.endsWith('.py')) names.add(`${dir}/${name}`);
  const out: Record<string, string> = {};
  for (const name of [...names].sort()) out[name] = await sha256File(path.join(repo, name));
  return out;
}
export async function unchanged(inputs: Record<string, string>, code: Record<string, string>) {
  for (const [name, hash] of Object.entries(inputs)) if (await sha256File(name) !== hash) throw new Error('input changed during processing');
  for (const [name, hash] of Object.entries(code)) if (await sha256File(path.join(repo, name)) !== hash) throw new Error('code changed during processing');
}
export async function atomicDirectory<T>(outDir: string, action: (staging: string) => Promise<T>) {
  const out = newDestination(outDir);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  const staging = `${out}.${randomUUID()}.tmp`; fs.mkdirSync(staging);
  try {
    const result = await action(staging);
    if (fs.existsSync(out)) throw new Error('output appeared during processing');
    fs.renameSync(staging, out); return result;
  } catch (e) { fs.rmSync(staging, { recursive: true, force: true }); throw e; }
}
export async function readJsonLines<T>(file: string, maxRows = 100000): Promise<T[]> {
  if (fs.statSync(file).size > 512 * 1024 * 1024) throw new Error('JSONL input exceeds 512 MiB');
  const input = fs.createReadStream(file), reader = readline.createInterface({ input, crlfDelay: Infinity }), rows: T[] = [];
  try { for await (const line of reader) { if (line.length > 2 * 1024 * 1024) throw new Error('JSONL row exceeds 2 MiB');
    if (line.trim()) { if (rows.length >= maxRows) throw new Error('JSONL row limit exceeded'); rows.push(JSON.parse(line)); } } }
  finally { reader.close(); input.destroy(); }
  return rows;
}
/** Audit an arbitrarily long time-ordered index stream, retaining only predeclared
 * feature/label windows. The sampling schedule is fixed before reading outcomes. */
export async function readNeededIndex(file: string, decisions: RecordedDecision[], asset: string, reference: string, finalFrom: number, plannedThrough?: (d: RecordedDecision) => number): Promise<OfficialPrint[]> {
  const spans = decisions.filter((d) => d.contract.asset === asset && d.contract.settlementReference === reference).map((d) => {
    const at = d.asOf ?? d.frame.decisionAt, through = plannedThrough?.(d) ?? d.contract.closeTime, reserved = at >= finalFrom || through >= finalFrom;
    return { from: Math.min(at - d.event.priorWindowSec * 1000 - 3000, d.contract.closeTime - (d.contract.averagingSec ?? 60) * 1000 - 3000),
      through: reserved ? at : through };
  }).sort((a, b) => a.from - b.from);
  const windows: Array<{ from: number; through: number }> = [];
  for (const s of spans) { const last = windows.at(-1); if (last && s.from <= last.through) last.through = Math.max(last.through, s.through); else windows.push({ ...s }); }
  const input = fs.createReadStream(file), reader = readline.createInterface({ input, crlfDelay: Infinity }), out: OfficialPrint[] = [];
  let cursor = 0, lastTs = -1, count = 0;
  try { for await (const line of reader) {
    if (line.length > 16384 || ++count > 500000000) throw new Error('index stream row/line limit exceeded');
    if (!line.trim()) continue;
    const p = JSON.parse(line) as OfficialPrint;
    if (!Number.isSafeInteger(p.ts) || p.ts < 0 || p.ts <= lastTs || !Number.isSafeInteger(p.knownAt) || p.knownAt < p.ts ||
        !Number.isFinite(p.value) || p.value <= 0) throw new Error('invalid or unordered source index stream');
    lastTs = p.ts;
    while (cursor < windows.length && p.ts > windows[cursor].through) cursor++;
    if (cursor < windows.length && p.ts >= windows[cursor].from) { if (out.length >= 2000000) throw new Error('selected index windows exceed two million prints; reduce observation density'); out.push(p); }
  } } finally { reader.close(); input.destroy(); }
  return out;
}
export async function source(base: string, r: Receipt) {
  if (!r || path.isAbsolute(r.file) || r.file.split(/[\\/]/).includes('..') || !/^[a-f0-9]{64}$/.test(r.sha256)) throw new Error('invalid source receipt');
  const file = fs.realpathSync(path.join(base, r.file));
  if (!file.startsWith(fs.realpathSync(base) + path.sep) || await sha256File(file) !== r.sha256) throw new Error('source path/hash mismatch');
  return file;
}
export async function exportRecordingInputs(recordingsDir: string, configFile: string, outDir: string) {
  const options = JSON.parse(fs.readFileSync(configFile, 'utf8')) as RecordingImportOptions, code = await codeHashes();
  const configHash = await sha256File(configFile);
  return atomicDirectory(outDir, async (staging) => {
    const report = await writeRecordingInputs(recordingsDir, staging, options);
    await unchanged({ [fs.realpathSync(configFile)]: configHash }, code);
    return report;
  });
}
export async function assembleContractDataset(specFile: string, outDir: string) {
  const specPath = fs.realpathSync(specFile), spec = JSON.parse(fs.readFileSync(specPath, 'utf8')) as AssemblySpec;
  const base = path.dirname(specPath), inputs: Record<string, string> = { [specPath]: await sha256File(specPath) }, code = await codeHashes();
  const policy = studyPolicy(spec.studyPolicyId);
  if (spec.schema !== 'opportunity-recording-spec-v1' || !Number.isSafeInteger(spec.knownBy) || spec.knownBy < 0 ||
      !spec.indices.length || spec.indices.length > 10 || new Set(spec.indices.map((i) => `${i.asset}:${i.reference}`)).size !== spec.indices.length) throw new Error('invalid recording spec');
  const decisionsFile = await source(base, spec.decisions); inputs[decisionsFile] = spec.decisions.sha256;
  const decisions = await readJsonLines<RecordedDecision>(decisionsFile, 20000);
  const indices: IndexEvidence[] = [];
  for (const r of spec.indices) {
    const file = await source(base, r); inputs[file] = r.sha256;
    indices.push(freezeIndexEvidence({ asset: r.asset, reference: r.reference, basis: r.basis, sourceSha256: r.sha256,
      prints: await readNeededIndex(file, decisions, r.asset, r.reference, policy.finalFrom) }));
  }
  const results = new Map<string, { yes: boolean; knownAt: number }>();
  if (spec.results) {
    const file = await source(base, spec.results); inputs[file] = spec.results.sha256;
    for (const row of await readJsonLines<{ ticker: string; yes: boolean; knownAt: number }>(file)) {
      if (row.knownAt >= policy.finalFrom) throw new Error('reported results include frozen-final outcomes');
      if (results.has(row.ticker)) throw new Error('duplicate reported settlement'); results.set(row.ticker, row);
    }
  }
  return atomicDirectory(outDir, async (staging) => {
    const file = path.join(staging, 'examples.jsonl'), fd = fs.openSync(file, 'wx'), counts: Record<string, number> = { observations: 0, complete: 0, withheld: 0, pending: 0, missing: 0, disagreement: 0 };
    try { for (const d of decisions) {
      const evidence = indices.find((i) => i.asset === d.contract.asset && i.reference === d.contract.settlementReference);
      if (!evidence) throw new Error('decision has no exact index source');
      const o = buildContractObservation(d.frame, d.contract, d.event, evidence, { side: d.side, executionBufferMs: d.executionBufferMs,
        termsSourceSha256: spec.decisions.sha256, asOf: d.asOf, snn: d.snn, anchor: d.anchor, termsBasis: d.termsBasis });
      const reserved = o.query.asOf >= policy.finalFrom || o.query.contract.closeTime >= policy.finalFrom;
      const cutoff = Math.min(spec.knownBy, policy.finalFrom - 1);
      const y: ContractOutcome = reserved ? { schema: CONTRACT_LABEL_SCHEMA, observationId: o.id, plannedThrough: o.query.contract.closeTime, knownAt: cutoff,
        status: 'pending' as const, category: null, timelyMove: null, sidePays: null, settlementAverage: null, officialResultConfirmed: false,
        firstMoveAt: null, mfeBps: null, maeBps: null, terminalMoveBps: null, basis: 'reconstructed-official-index-rule' as const, reason: 'frozen-final-outcomes-withheld' }
        : labelContract(o, evidence, cutoff, results.get(d.contract.ticker));
      const example: ContractExample = { observation: o, outcome: y, ...(d.quote ? { quote: d.quote } : {}) };
      fs.writeSync(fd, JSON.stringify(example) + '\n'); counts.observations++;
      if (reserved) counts.withheld++;
      else if (y.status === 'complete') counts.complete++;
      else if (y.status === 'pending') counts.pending++;
      else if (y.status === 'missing-index') counts.missing++;
      else counts.disagreement++;
    } } finally { fs.closeSync(fd); }
    const manifest: DatasetManifest = { schema: CONTRACT_DATASET_SCHEMA, studyPolicyId: policy.id, researchOnly: true, finalOutcomesWithheld: true, inputs, codeHashes: code,
      outputs: { examples: { file: 'examples.jsonl', sha256: await sha256File(file) } }, counts };
    await unchanged(inputs, code);
    fs.writeFileSync(path.join(staging, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n'); return manifest;
  });
}
export async function loadContractDataset(dir: string) {
  const root = fs.realpathSync(dir), manifestFile = path.join(root, 'manifest.json'), manifestHash = await sha256File(manifestFile);
  const manifest = JSON.parse(fs.readFileSync(manifestFile, 'utf8')) as DatasetManifest;
  if (manifest.schema !== CONTRACT_DATASET_SCHEMA || manifest.researchOnly !== true || manifest.finalOutcomesWithheld !== true || manifest.outputs.examples.file !== 'examples.jsonl') throw new Error('invalid contract dataset manifest');
  const file = await source(root, manifest.outputs.examples), examples = await readJsonLines<ContractExample>(file, 20000);
  if (examples.length !== manifest.counts.observations) throw new Error('contract dataset counts differ');
  // Validate all nonfinal observations/labels, including joins and duplicate timestamps.
  contractRows(examples, { from: 0, through: studyPolicy(manifest.studyPolicyId).finalFrom }, manifest.studyPolicyId);
  return { examples, manifest, hashes: { [manifestFile]: manifestHash, [file]: manifest.outputs.examples.sha256 } };
}
export async function exportContractStudy(datasetDir: string, planFile: string, policyFile: string, outDir: string,
  options: ContractFitOptions & { onProgress?: (message: string) => void } = {}) {
  const data = await loadContractDataset(datasetDir), code = await codeHashes();
  const inputs = { ...data.hashes, [fs.realpathSync(planFile)]: await sha256File(planFile), [fs.realpathSync(policyFile)]: await sha256File(policyFile) };
  const plan = JSON.parse(fs.readFileSync(planFile, 'utf8')) as ContractStudyPlan, policy = JSON.parse(fs.readFileSync(policyFile, 'utf8')) as PaperPolicy;
  if (studyPolicy(plan.studyPolicyId).id !== studyPolicy(data.manifest.studyPolicyId).id) throw new Error('dataset and study use different registered partitions');
  const study = runContractStudy(data.examples, plan, policy, options), product = createAtlasProduct(study, code, inputs);
  return atomicDirectory(outDir, async (staging) => {
    await unchanged(inputs, code);
    fs.writeFileSync(path.join(staging, 'product.json'), JSON.stringify(product) + '\n');
    const registry = new AtlasRegistry(); registry.register(product);
    const report = { productId: product.id, status: study.status, blockers: study.blockers, retention: study.retention,
      audit: study.audit, calibration: study.calibration, candidates: study.candidates.map(({ model, ...m }) => ({ ...m, id: model.id, family: model.family, included: model.included })),
      registry: registry.status(), plan, policy, inputHashes: inputs, codeHashes: code, createdAt: product.createdAt, liveEntryAllowed: false, autoPromote: false };
    fs.writeFileSync(path.join(staging, 'report.json'), JSON.stringify(report, null, 2) + '\n'); return report;
  });
}
export interface PaperRequest { observation: ContractObservation; quote: PaperQuote | null; position: PaperPosition | null;
  allowance: { riskApprovedQuantity: number; remainingRiskDollars: number } }
export async function exportPaperShadow(productFile: string, requestsFile: string, policyFile: string, outDir: string,
  maximumCalibrationAgeMs: number, mode: 'forward-paper' | 'historical-audit' = 'forward-paper') {
  const inputs: Record<string, string> = {};
  for (const file of [productFile, requestsFile, policyFile]) inputs[fs.realpathSync(file)] = await sha256File(file);
  const code = await codeHashes(), product = JSON.parse(fs.readFileSync(productFile, 'utf8')) as AtlasProduct;
  const policy = JSON.parse(fs.readFileSync(policyFile, 'utf8')) as PaperPolicy, registry = new AtlasRegistry(); registry.register(product);
  const requests = await readJsonLines<PaperRequest>(requestsFile, 20000);
  return atomicDirectory(outDir, async (staging) => {
    const fd = fs.openSync(path.join(staging, 'shadow.jsonl'), 'wx'), counts: Record<string, number> = {};
    let lastAt = 0, earliestClose = Infinity;
    try { for (const r of requests) {
      encodeContractObservation(r.observation);
      if (r.observation.query.asOf < lastAt) throw new Error('paper requests must be in arrival order'); lastAt = r.observation.query.asOf;
      const recordedAt = Date.now(), close = r.observation.query.contract.closeTime;
      earliestClose = Math.min(earliestClose, close);
      if (mode === 'forward-paper' && (lastAt > recordedAt || recordedAt - lastAt > 5000 || recordedAt >= close)) {
        throw new Error('forward-paper capture requires a current request within five seconds and before expiry; replay requires explicit historical-audit mode');
      }
      const result = registry.query(product.id, r.observation, { maximumCalibrationAgeMs, mode });
      const decision = evaluatePaperPosition(r.observation, result.forecast, r.quote, r.position, policy, r.allowance);
      counts[decision.action] = (counts[decision.action] ?? 0) + 1;
      fs.writeSync(fd, JSON.stringify({ observationId: r.observation.id, asOf: lastAt, recordedAt, mode,
        forecast: result, decision, position: r.position, quote: r.quote }) + '\n');
    } } finally { fs.closeSync(fd); }
    await unchanged(inputs, code);
    const report = { productId: product.id, researchOnly: true, liveEntryAllowed: false, autoPromote: false, mode,
      requests: requests.length, actions: counts, preparedAt: Date.now(), maximumForwardCaptureLagMs: 5000,
      positionBasis: 'Caller-reported positions; recommendations are not fills',
      inputs, codeHashes: code, outputSha256: await sha256File(path.join(staging, 'shadow.jsonl')) };
    if (mode === 'forward-paper' && Date.now() >= earliestClose) throw new Error('forward-paper batch expired before publication');
    fs.writeFileSync(path.join(staging, 'report.json'), JSON.stringify(report, null, 2) + '\n'); return report;
  });
}
export async function exportSnnComparison(s5ProductFile: string, s5DatasetDir: string, s6ProductFile: string, s6DatasetDir: string, outDir: string) {
  const code = await codeHashes(), data5 = await loadContractDataset(s5DatasetDir), data6 = await loadContractDataset(s6DatasetDir);
  const s5 = JSON.parse(fs.readFileSync(s5ProductFile, 'utf8')) as AtlasProduct, s6 = JSON.parse(fs.readFileSync(s6ProductFile, 'utf8')) as AtlasProduct;
  const r = new AtlasRegistry(); r.register(s5); r.register(s6);
  const inputs = { ...data5.hashes, ...data6.hashes, [fs.realpathSync(s5ProductFile)]: await sha256File(s5ProductFile), [fs.realpathSync(s6ProductFile)]: await sha256File(s6ProductFile) };
  const evidence = compareSnnStudies(s5.study, data5.examples, s6.study, data6.examples);
  return atomicDirectory(outDir, async (staging) => {
    await unchanged(inputs, code);
    fs.writeFileSync(path.join(staging, 'comparison.json'), JSON.stringify(evidence, null, 2) + '\n');
    if (evidence.recommended !== 'none') {
      const study = qualifySnnStudy(evidence.recommended === 'S5' ? s5.study : s6.study, evidence);
      const product = createAtlasProduct(study, code, inputs);
      fs.writeFileSync(path.join(staging, 'product.json'), JSON.stringify(product) + '\n');
    }
    return evidence;
  });
}
export async function runProductDemo(outDir: string) {
  const staging = newDestination(outDir);
  fs.mkdirSync(staging, { recursive: true });
  try {
    const inputs = path.join(staging, 'inputs'); await writeProductDemoInputs(inputs);
    await assembleContractDataset(path.join(inputs, 'spec.json'), path.join(staging, 'dataset'));
    const study = await exportContractStudy(path.join(staging, 'dataset'), path.join(inputs, 'plan.json'), path.join(inputs, 'policy.json'),
      path.join(staging, 'study'), { epochs: 150, hidden: 12, trees: 48 });
    const ds = await loadContractDataset(path.join(staging, 'dataset')), row = ds.examples.at(-1)!;
    const requests = path.join(staging, 'requests.jsonl');
    fs.writeFileSync(requests, JSON.stringify({ observation: row.observation, quote: row.quote, position: null,
      allowance: { riskApprovedQuantity: 1, remainingRiskDollars: 1 } }) + '\n');
    const shadow = await exportPaperShadow(path.join(staging, 'study/product.json'), requests, path.join(inputs, 'policy.json'),
      path.join(staging, 'shadow'), 86400000, 'historical-audit');
    const report = { synthetic: true, purpose: 'Software demonstration only; no market edge, model qualification or live enablement',
      studyStatus: study.status, blockers: study.blockers, candidates: study.candidates, actions: shadow.actions, liveEntryAllowed: false, autoPromote: false };
    fs.writeFileSync(path.join(staging, 'demo-report.json'), JSON.stringify(report, null, 2) + '\n'); return report;
  } catch (e) { fs.rmSync(staging, { recursive: true, force: true }); throw e; }
}
const arg = (name: string, fallback?: string) => { const i = process.argv.indexOf(`--${name}`); const value = i < 0 ? fallback : process.argv[i + 1]; if (value === undefined || value.startsWith('--')) throw new Error(`--${name} required`); return value; };
async function main() {
  const command = process.argv[2];
  if (command === 'demo') console.log(JSON.stringify(await runProductDemo(arg('out')), null, 2));
  else if (command === 'recordings') console.log(JSON.stringify(await exportRecordingInputs(arg('recordings'), arg('config'), arg('out')), null, 2));
  else if (command === 'assemble') console.log(JSON.stringify(await assembleContractDataset(arg('spec'), arg('out')), null, 2));
  else if (command === 'study') console.log(JSON.stringify(await exportContractStudy(arg('dataset'), arg('plan'), arg('policy'), arg('out'),
    { epochs: Number(arg('epochs', '150')), hidden: Number(arg('hidden', '12')), trees: Number(arg('trees', '64')), onProgress: console.log }), null, 2));
  else if (command === 'status') {
    const r = new AtlasRegistry(); r.register(JSON.parse(fs.readFileSync(arg('product'), 'utf8'))); console.log(JSON.stringify(r.status(), null, 2));
  } else if (command === 'shadow') console.log(JSON.stringify(await exportPaperShadow(arg('product'), arg('requests'), arg('policy'), arg('out'),
    Number(arg('maximum-calibration-age-ms', String(14 * 86400000))), process.argv.includes('--historical-audit') ? 'historical-audit' : 'forward-paper'), null, 2));
  else if (command === 'query') {
    const r = new AtlasRegistry(), p = JSON.parse(fs.readFileSync(arg('product'), 'utf8')) as AtlasProduct;
    r.register(p); console.log(JSON.stringify(r.query(p.id, JSON.parse(fs.readFileSync(arg('observation'), 'utf8')),
      { maximumCalibrationAgeMs: Number(arg('maximum-calibration-age-ms', String(14 * 86400000))), mode: process.argv.includes('--historical-audit') ? 'historical-audit' : 'forward-paper' }), null, 2));
  } else if (command === 'compare-snn') console.log(JSON.stringify(await exportSnnComparison(arg('s5-product'), arg('s5-dataset'), arg('s6-product'), arg('s6-dataset'), arg('out')), null, 2));
  else if (command === 'snn-replay') {
    const tape = fs.realpathSync(arg('tape')), hash = await sha256File(tape), code = await codeHashes();
    console.log(JSON.stringify(await atomicDirectory(arg('out'), async (staging) => {
      const reports = [];
      for (const variant of ['S5', 'S6'] as const) {
        const fd = fs.openSync(path.join(staging, `${variant}.jsonl`), 'wx');
        const domain = arg('domain', 'crypto'); if (!['crypto', 'perps'].includes(domain)) throw new Error('SNN domain must be crypto or perps');
        try { reports.push(replayAtlasSnnTape(tape, { variant, domain: domain as 'crypto' | 'perps', studyPolicyId: arg('study-policy', studyPolicy().id), inputLagMs: Number(arg('input-lag-ms', '1000')), sourceSha256: hash, onState: (state) => fs.writeSync(fd, JSON.stringify(state) + '\n') })); }
        finally { fs.closeSync(fd); }
      }
      await unchanged({ [tape]: hash }, code);
      fs.writeFileSync(path.join(staging, 'report.json'), JSON.stringify({ reports, codeHashes: code }, null, 2) + '\n'); return reports;
    }), null, 2));
  } else throw new Error('Usage: research:opportunity-product <demo|recordings|assemble|study|status|query|shadow|snn-replay|compare-snn> --...; see docs/OPPORTUNITY_ATLAS_OPERATIONS.md');
}
if (process.argv[1] && /(^|[/\\])productCli\.(ts|js)$/.test(process.argv[1])) void main().catch((e) => { console.error(e instanceof Error ? e.message : e); process.exitCode = 1; });
