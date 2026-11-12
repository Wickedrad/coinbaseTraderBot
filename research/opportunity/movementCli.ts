/** GitHub-runner workflow for the owner's advance-movement objective. */
import fs from 'node:fs';
import path from 'node:path';
import { atomicDirectory, codeHashes, readJsonLines, readNeededIndex, source, unchanged, type AssemblySpec, type RecordedDecision } from './productCli';
import { buildContractObservation, digest, encodeContractObservation, freezeIndexEvidence, labelTimelyMovement, stamp, type IndexEvidence, type TimelyMovementOutcome } from './contractDataset';
import { sha256File } from './jointPathData';
import { studyPolicy } from './studyPolicy';
import { compareAdvanceSnn, createAdvanceProduct, MOVEMENT_SCHEMA, movementDeadline, movementObservationKey, movementRows, queryAdvanceProduct, qualifyAdvanceSnn, runAdvanceStudy, validateAdvanceProduct,
  type AdvanceProduct, type MovementExample } from './movementStudy';
import { evaluateProfitExit, movementTargetPolicy, profitExitBy, validateProfitPolicy, type ProfitExitRequest, type ProfitPolicy } from './profitExit';
import { validateStudyPlan, type ContractFitOptions, type ContractStudyPlan } from './contractLearner';

interface Manifest {
  schema: typeof MOVEMENT_SCHEMA; studyPolicyId: string; objective: 'advance-price-movement'; finalOutcomesWithheld: true;
  targetPolicySha256: string; counts: Record<string, number>; inputs: Record<string, string>; codeHashes: Record<string, string>;
  outputs: { examples: { file: string; sha256: string } };
}
export async function assembleMovementDataset(specFile: string, policyFile: string, outDir: string) {
  const specPath = fs.realpathSync(specFile), base = path.dirname(specPath), spec = JSON.parse(fs.readFileSync(specPath, 'utf8')) as AssemblySpec;
  const policyPath = fs.realpathSync(policyFile), policy = JSON.parse(fs.readFileSync(policyPath, 'utf8')) as ProfitPolicy;
  validateProfitPolicy(policy);
  const registered = studyPolicy(spec.studyPolicyId), code = await codeHashes();
  if (spec.schema !== 'opportunity-recording-spec-v1' || !stamp(spec.knownBy)) throw new Error('invalid movement input spec');
  const inputs: Record<string, string> = { [specPath]: await sha256File(specPath), [policyPath]: await sha256File(policyPath) };
  const decisionsFile = await source(base, spec.decisions); inputs[decisionsFile] = spec.decisions.sha256;
  const raw = await readJsonLines<RecordedDecision>(decisionsFile, 20000);
  const deadline = (d: RecordedDecision) => Math.min(d.contract.closeTime - d.executionBufferMs, profitExitBy(d.contract, policy));
  const decisions = raw.filter((d) => deadline(d) - (d.asOf ?? d.frame.decisionAt) >= Math.max(1000, policy.minimumLeadMs) + d.event.sustainSec * 1000);
  const indices: IndexEvidence[] = [];
  for (const receipt of spec.indices) {
    const file = await source(base, receipt); inputs[file] = receipt.sha256;
    indices.push(freezeIndexEvidence({ asset: receipt.asset, reference: receipt.reference, sourceSha256: receipt.sha256, basis: receipt.basis,
      prints: await readNeededIndex(file, decisions, receipt.asset, receipt.reference, registered.finalFrom, deadline) }));
  }
  return atomicDirectory(outDir, async (staging) => {
    const file = path.join(staging, 'examples.jsonl'), fd = fs.openSync(file, 'wx'), keys = new Set<string>();
    const counts = { sourceDecisions: raw.length, inactive: raw.length - decisions.length, deduplicated: 0, observations: 0, complete: 0, pending: 0, missing: 0, withheld: 0 };
    try { for (const d of decisions) {
      const evidence = indices.find((i) => i.asset === d.contract.asset && i.reference === d.contract.settlementReference);
      if (!evidence) throw new Error('movement decision lacks exact index evidence');
      const observation = buildContractObservation(d.frame, d.contract, d.event, evidence, { side: d.side, executionBufferMs: d.executionBufferMs,
        termsSourceSha256: spec.decisions.sha256, asOf: d.asOf, snn: d.snn, anchor: d.anchor, termsBasis: d.termsBasis });
      const byAt = movementDeadline(observation, policy), key = movementObservationKey(observation, byAt);
      if (keys.has(key)) { counts.deduplicated++; continue; } keys.add(key);
      const reserved = observation.query.asOf >= registered.finalFrom || byAt >= registered.finalFrom, cutoff = Math.min(spec.knownBy, registered.finalFrom - 1);
      const outcome: TimelyMovementOutcome = reserved ? { schema: 'opportunity-timely-movement-v1', observationId: observation.id, plannedThrough: byAt, knownAt: cutoff,
        status: 'pending', timelyMove: null, advanceMove: null, firstMoveAt: null, minimumLeadMs: policy.minimumLeadMs, leadMs: null, mfeBps: null, maeBps: null, reason: 'frozen-final-outcomes-withheld' }
        : labelTimelyMovement(observation, evidence, cutoff, byAt, policy.minimumLeadMs);
      fs.writeSync(fd, JSON.stringify({ observation, byAt, outcome } satisfies MovementExample) + '\n'); counts.observations++;
      if (reserved) counts.withheld++; else if (outcome.status === 'complete') counts.complete++; else if (outcome.status === 'pending') counts.pending++; else counts.missing++;
    } } finally { fs.closeSync(fd); }
    // No reported results, settlement labels, quotes or P/L credits were read to construct this target.
    const manifest: Manifest = { schema: MOVEMENT_SCHEMA, studyPolicyId: registered.id, objective: 'advance-price-movement', finalOutcomesWithheld: true,
      targetPolicySha256: digest(movementTargetPolicy(policy)),
      counts, inputs, codeHashes: code, outputs: { examples: { file: 'examples.jsonl', sha256: await sha256File(file) } } };
    await unchanged(inputs, code); fs.writeFileSync(path.join(staging, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n'); return manifest;
  });
}
export async function loadMovementDataset(dir: string, policy: ProfitPolicy) {
  const root = fs.realpathSync(dir), manifestFile = path.join(root, 'manifest.json'), manifestHash = await sha256File(manifestFile);
  const manifest = JSON.parse(fs.readFileSync(manifestFile, 'utf8')) as Manifest;
  if (manifest.targetPolicySha256 !== digest(movementTargetPolicy(policy)) || manifest.schema !== MOVEMENT_SCHEMA || manifest.objective !== 'advance-price-movement' || manifest.finalOutcomesWithheld !== true || manifest.outputs.examples.file !== 'examples.jsonl') throw new Error('invalid movement dataset manifest');
  const file = await source(root, manifest.outputs.examples), examples = await readJsonLines<MovementExample>(file, 20000);
  if (examples.length !== manifest.counts.observations) throw new Error('movement dataset counts differ');
  movementRows(examples, { from: 0, through: studyPolicy(manifest.studyPolicyId).finalFrom }, policy, manifest.studyPolicyId);
  return { manifest, examples, hashes: { [manifestFile]: manifestHash, [file]: manifest.outputs.examples.sha256 } };
}
export async function exportAdvanceStudy(dataset: string, planFile: string, policyFile: string, outDir: string, options: ContractFitOptions = {}) {
  const policy = JSON.parse(fs.readFileSync(policyFile, 'utf8')) as ProfitPolicy, plan = JSON.parse(fs.readFileSync(planFile, 'utf8')) as ContractStudyPlan;
  const data = await loadMovementDataset(dataset, policy), code = await codeHashes();
  if (studyPolicy(plan.studyPolicyId).id !== data.manifest.studyPolicyId) throw new Error('movement dataset/study registration differs');
  const inputs = { ...data.hashes, [fs.realpathSync(planFile)]: await sha256File(planFile), [fs.realpathSync(policyFile)]: await sha256File(policyFile) };
  return atomicDirectory(outDir, async (staging) => {
    const study = runAdvanceStudy(data.examples, plan, policy, options), product = createAdvanceProduct(study, code, inputs);
    fs.writeFileSync(path.join(staging, 'product.json'), JSON.stringify(product) + '\n');
    const report = { productId: product.id, objective: study.objective, status: study.status, blockers: study.blockers,
      selected: study.selected ? { id: study.selected.id, family: study.selected.family, headKind: study.selected.head.model.kind, trainingEvents: study.selected.head.trainingEvents,
        included: study.selected.included, calibrated: study.selected.head.calibrationFitted } : null,
      candidates: study.candidates.map((c) => ({ id: c.model.id, family: c.model.family, included: c.model.included, headKind: c.model.head.model.kind, selectionLoss: c.selectionLoss, rows: c.rows })),
      retention: study.retention, audit: study.audit, movementBands: study.calibration?.bins ?? [], researchOnly: true, liveEntryAllowed: false,
      qualificationBasis: 'Advance-movement predictive reliability only; settlement wins and fee-net trade profitability are not movement labels or retention gates', inputs, codeHashes: code };
    await unchanged(inputs, code); fs.writeFileSync(path.join(staging, 'report.json'), JSON.stringify(report, null, 2) + '\n'); return report;
  });
}
export async function exportMovementShadow(productFile: string, observationsFile: string, policyFile: string, outDir: string,
  options: { historicalAudit: boolean; maximumCalibrationAgeMs: number; minimumMoveLowerBound: number }) {
  const product = JSON.parse(fs.readFileSync(productFile, 'utf8')) as AdvanceProduct, policy = JSON.parse(fs.readFileSync(policyFile, 'utf8')) as ProfitPolicy;
  validateAdvanceProduct(product); validateProfitPolicy(policy);
  const inputs: Record<string, string> = {};
  for (const f of [productFile, observationsFile, policyFile]) inputs[fs.realpathSync(f)] = await sha256File(f);
  const examples = await readJsonLines<Pick<MovementExample, 'observation'>>(observationsFile, 20000), code = await codeHashes();
  let firstDeadline = Infinity, maximumSustainMs = 0, oldestAsOf = Infinity;
  const report = await atomicDirectory(outDir, async (staging) => {
    const fd = fs.openSync(path.join(staging, 'shadow.jsonl'), 'wx'), counts: Record<string, number> = {};
    let last = 0, queries = 0;
    try { for (const e of examples) {
      const o = e.observation, now = Date.now();
      if (o.query.asOf < product.study.plan.audit.through) continue;
      encodeContractObservation(o);
      if (o.query.asOf < last) throw new Error('movement shadow observations must be in arrival order'); last = o.query.asOf;
      firstDeadline = Math.min(firstDeadline, movementDeadline(o, policy));
      oldestAsOf = Math.min(oldestAsOf, o.query.asOf);
      maximumSustainMs = Math.max(maximumSustainMs, o.event.sustainSec * 1000);
      if (!options.historicalAudit && (now < last || now - last > 1000 || now - o.index.at > 3000 ||
          (o.snn && now - o.snn.stateAt > 2000) || now >= firstDeadline || product.createdAt > last)) throw new Error('forward movement capture requires an already-published model and fresh request/index/SNN clocks before its deadline');
      const result = queryAdvanceProduct(product, o, policy, options); counts[result.status] = (counts[result.status] ?? 0) + 1; queries++;
      const producedAt = Date.now();
      if (!options.historicalAudit && producedAt - last > 1000) throw new Error('forward movement computation missed its fresh capture window');
      fs.writeSync(fd, JSON.stringify({ observationId: o.id, asOf: last, recordedAt: producedAt, capturedAt: now, mode: options.historicalAudit ? 'historical-audit' : 'forward-paper', result }) + '\n');
    } } finally { fs.closeSync(fd); }
    await unchanged(inputs, code);
    if (!options.historicalAudit && Date.now() >= firstDeadline) throw new Error('movement shadow batch expired before publication');
    const report = { productId: product.id, objective: 'advance-price-movement', queries, statuses: counts,
      mode: options.historicalAudit ? 'historical-audit' : 'forward-paper', researchOnly: true, liveEntryAllowed: false,
      executionBasis: 'Read-only movement forecasts; no orders, simulated fills or settlement-based entry decisions', inputs, codeHashes: code,
      outputSha256: await sha256File(path.join(staging, 'shadow.jsonl')) };
    fs.writeFileSync(path.join(staging, 'report.json'), JSON.stringify(report, null, 2) + '\n'); return report;
  });
  // This timestamp follows the atomic rename: the forecast file is already available
  // to the runner's consumer. A feature timestamp cannot backdate its publication.
  const publishedAt = Date.now();
  const core = { schema: 'opportunity-movement-publication-v1' as const, productId: product.id, mode: report.mode, publishedAt,
    modelCreatedAt: product.createdAt, oldestAsOf: report.queries ? oldestAsOf : null,
    minimumLeadMs: policy.minimumLeadMs, earliestEligibleMoveAt: publishedAt + policy.minimumLeadMs,
    firstDeadline: report.queries ? firstDeadline : null, maximumSustainMs, outputSha256: report.outputSha256,
    forwardTimingEligible: !options.historicalAudit && report.queries > 0 && publishedAt - oldestAsOf <= 1000 && publishedAt + policy.minimumLeadMs + maximumSustainMs <= firstDeadline };
  const publication = { ...core, id: digest(core) };
  fs.writeFileSync(path.join(outDir, 'publication.json'), JSON.stringify(publication, null, 2) + '\n', { flag: 'wx' });
  if (!options.historicalAudit && !publication.forwardTimingEligible) throw new Error('forward movement batch published too late; publication receipt is ineligible');
  return { ...report, publication };
}
/** Score actual delivery lead; this diagnostic never refits on forward outcomes. */
export function movementLeadAfterPublication(y: TimelyMovementOutcome, receipt: { id: string; [key: string]: unknown }) {
  const { id, ...core } = receipt;
  if (digest(core) !== id || receipt.schema !== 'opportunity-movement-publication-v1' || receipt.mode !== 'forward-paper' ||
      receipt.forwardTimingEligible !== true || !stamp(receipt.publishedAt as number) || !stamp(receipt.minimumLeadMs as number) ||
      (receipt.minimumLeadMs as number) < 1000 || !stamp(receipt.oldestAsOf as number) || (receipt.publishedAt as number) < (receipt.oldestAsOf as number) ||
      (receipt.publishedAt as number) - (receipt.oldestAsOf as number) > 1000 ||
      y.status !== 'complete' || y.knownAt < (receipt.publishedAt as number)) throw new Error('complete outcome and eligible forward publication receipt required');
  const leadMs = y.firstMoveAt === null ? null : y.firstMoveAt - (receipt.publishedAt as number);
  return { leadMs, advanceMove: leadMs !== null && leadMs >= (receipt.minimumLeadMs as number),
    basis: 'First observed sustained move measured from persisted forecast publication, not its earlier feature timestamp' };
}
export async function runObservedMovementStudy(o: { source: string; plan: string; policy: string; out: string }) {
  // Register the objective and fixed settings before any labels are read.
  const parameters = { epochs: 40, hidden: 6, trees: 12, seed: 17 };
  const root = path.resolve(o.out);
  const registration = { objective: 'advance-price-movement', parameters, plan: JSON.parse(fs.readFileSync(o.plan, 'utf8')),
      policy: JSON.parse(fs.readFileSync(o.policy, 'utf8')), declaredBeforeLabels: true, source: 'Existing receipt-checked observed inputs; no settlement outcomes consumed', researchOnly: true, liveEntryAllowed: false, autoPromote: false };
  validateProfitPolicy(registration.policy); validateStudyPlan(registration.plan);
  await atomicDirectory(root, async (staging) => { fs.writeFileSync(path.join(staging, 'registration.json'), JSON.stringify(registration, null, 2) + '\n'); });
  const variants = [];
  for (const name of ['base', 'S5', 'S6']) {
    console.log(`Assembling/fitting ${name} advance-movement targets`);
    const dir = path.join(root, name), dataset = path.join(dir, 'dataset');
    const manifest = await assembleMovementDataset(path.join(o.source, name, 'inputs/spec.json'), o.policy, dataset);
    const study = await exportAdvanceStudy(dataset, o.plan, o.policy, path.join(dir, 'study'), parameters);
    const shadow = await exportMovementShadow(path.join(dir, 'study/product.json'), path.join(dataset, 'examples.jsonl'), o.policy,
      path.join(dir, 'shadow'), { historicalAudit: true, maximumCalibrationAgeMs: 14 * 86400000, minimumMoveLowerBound: 0.8 });
    variants.push({ name, dataset: manifest.counts, study, shadow });
  }
  const products = ['S5', 'S6'].map((name) => JSON.parse(fs.readFileSync(path.join(root, name, 'study/product.json'), 'utf8')) as AdvanceProduct);
  const policy = registration.policy as ProfitPolicy;
  const data5 = await loadMovementDataset(path.join(root, 'S5/dataset'), policy), data6 = await loadMovementDataset(path.join(root, 'S6/dataset'), policy);
  const comparison = products.every((p) => p.study.selected && p.study.baseline)
    ? compareAdvanceSnn(products[0].study, data5.examples, products[1].study, data6.examples, policy)
    : { recommended: 'none', reason: 'insufficient movement rows', researchOnly: true, liveEntryAllowed: false };
  fs.writeFileSync(path.join(root, 'comparison.json'), JSON.stringify(comparison, null, 2) + '\n');
  if ('schema' in comparison && comparison.recommended !== 'none') {
    const selected = products[comparison.recommended === 'S5' ? 0 : 1];
    const qualified = createAdvanceProduct(qualifyAdvanceSnn(selected.study, comparison), selected.codeHashes, selected.inputHashes);
    fs.writeFileSync(path.join(root, 'compared-product.json'), JSON.stringify(qualified) + '\n');
  }
  const report = { registration, variants, comparison, researchOnly: true, liveEntryAllowed: false, autoPromote: false,
    interpretation: 'Movement reliability is learned independently. Existing quota/fees own profit-taking; these archives are development data, not a forward trial.' };
  fs.writeFileSync(path.join(root, 'summary.json'), JSON.stringify(report, null, 2) + '\n'); return report;
}
const arg = (name: string, fallback?: string) => { const i = process.argv.indexOf(`--${name}`); const v = i < 0 ? fallback : process.argv[i + 1]; if (!v) throw new Error(`--${name} required`); return v; };
async function main() {
  const command = process.argv[2], policyFile = arg('policy', 'research/opportunity/examples/profit-policy.json');
  if (command === 'run') console.log(JSON.stringify(await runObservedMovementStudy({ source: arg('source'), plan: arg('plan', 'research/opportunity/examples/prospective-prefix-plan.json'), policy: policyFile, out: arg('out') }), null, 2));
  else if (command === 'assemble') console.log(JSON.stringify(await assembleMovementDataset(arg('spec'), policyFile, arg('out')), null, 2));
  else if (command === 'study') console.log(JSON.stringify(await exportAdvanceStudy(arg('dataset'), arg('plan'), policyFile, arg('out')), null, 2));
  else if (command === 'shadow') console.log(JSON.stringify(await exportMovementShadow(arg('product'), arg('observations'), policyFile, arg('out'),
    { historicalAudit: process.argv.includes('--historical-audit'), maximumCalibrationAgeMs: Number(arg('maximum-calibration-age-ms', String(14 * 86400000))), minimumMoveLowerBound: Number(arg('minimum-move-lower-bound', '0.8')) }), null, 2));
  else if (command === 'query') console.log(JSON.stringify(queryAdvanceProduct(JSON.parse(fs.readFileSync(arg('product'), 'utf8')),
    JSON.parse(fs.readFileSync(arg('observation'), 'utf8')), JSON.parse(fs.readFileSync(policyFile, 'utf8')),
    { historicalAudit: process.argv.includes('--historical-audit'), maximumCalibrationAgeMs: Number(arg('maximum-calibration-age-ms', String(14 * 86400000))), minimumMoveLowerBound: Number(arg('minimum-move-lower-bound', '0.8')) }), null, 2));
  else if (command === 'exit') console.log(JSON.stringify(evaluateProfitExit(JSON.parse(fs.readFileSync(arg('request'), 'utf8')) as ProfitExitRequest,
    JSON.parse(fs.readFileSync(policyFile, 'utf8')) as ProfitPolicy), null, 2));
  else throw new Error('Usage: research:opportunity-movement <run|assemble|study|query|shadow|exit> --...');
}
if (process.argv[1] && /(^|[/\\])movementCli\.(ts|js)$/.test(process.argv[1])) void main().catch((e) => { console.error(e instanceof Error ? e.stack : e); process.exitCode = 1; });
