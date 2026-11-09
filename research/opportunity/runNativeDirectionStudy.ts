/** Real native SNN training plus continuous sustained-movement decoders. GitHub research only. */
import fs from 'node:fs';
import path from 'node:path';
import { domainParams } from '../../bot/snn/params';
import { replayAtlasSnnTape, type FrozenSnnEvidence } from './snnReplay';
import { combineSnnStates, type AtlasSnnState } from './snnState';
import { sha256File } from './jointPathData';
import { source, readJsonLines, type AssemblySpec, type RecordedDecision } from './productCli';
import { assembleMovementDataset, loadMovementDataset } from './movementCli';
import { fitAdvanceModel, movementRows, scoreAdvanceModel, type MovementScore } from './movementStudy';
import { binaryResponseProbability, featureFamily, type ContractStudyPlan, type FeatureFamily } from './contractLearner';
import { digest } from './contractDataset';
import { studyPolicy } from './studyPolicy';
import type { ProfitPolicy } from './profitExit';
import { directionStudyEvents } from './directionStudyEvents';

const write = (file: string, value: unknown) => fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n', { flag: 'wx' });
const metric = (scores: MovementScore[]) => {
  const mass = scores.reduce((s, r) => s + r.weight, 0), high = scores.filter((r) => r.p >= 0.6);
  const weighted = (rows: MovementScore[], f: (r: MovementScore) => number) => rows.length ? rows.reduce((s, r) => s + r.weight * f(r), 0) / rows.reduce((s, r) => s + r.weight, 0) : null;
  return { rows: scores.length, events: new Set(scores.map((r) => r.eventKey)).size, mass, logLoss: weighted(scores, (r) => r.loss),
    brier: weighted(scores, (r) => (r.p - r.y) ** 2), accuracy: weighted(scores, (r) => Number((r.p >= 0.5) === Boolean(r.y))),
    above60: { rows: high.length, events: new Set(high.map((r) => r.eventKey)).size, predicted: weighted(high, (r) => r.p), observed: weighted(high, (r) => r.y) },
    calibration: Array.from({ length: 10 }, (_, bin) => { const rs = scores.filter((r) => Math.min(9, Math.floor(r.p * 10)) === bin);
      return { from: bin / 10, through: (bin + 1) / 10, rows: rs.length, predicted: weighted(rs, (r) => r.p), observed: weighted(rs, (r) => r.y) }; }) };
};
export async function runNativeDirectionStudy(o: { source: string; plan: string; policy: string; out: string; snapshots?: string }) {
  const root = path.resolve(o.out), original = path.resolve(o.source), plan = JSON.parse(fs.readFileSync(o.plan, 'utf8')) as ContractStudyPlan;
  const profit = JSON.parse(fs.readFileSync(o.policy, 'utf8')) as ProfitPolicy, policy = studyPolicy(plan.studyPolicyId);
  if (fs.existsSync(root)) throw new Error('new native-direction output required'); fs.mkdirSync(root, { recursive: true });
  const inputsDir = path.join(original, 'base/inputs'), specPath = path.join(inputsDir, 'spec.json');
  const spec = JSON.parse(fs.readFileSync(specPath, 'utf8')) as AssemblySpec;
  if (spec.studyPolicyId !== policy.id) throw new Error('source policy differs');
  const originalDecisions = await readJsonLines<RecordedDecision>(await source(inputsDir, spec.decisions), 20000);
  const raw = originalDecisions.filter((d) => d.event.kind === 'move' && d.side === 'yes').flatMap((d) => directionStudyEvents()
    .filter((e) => e.direction === d.event.direction).map((event) => ({ ...d, event })));
  const extraDir = o.snapshots ? path.resolve(o.snapshots) : undefined;
  const extraSpec = extraDir ? JSON.parse(fs.readFileSync(path.join(extraDir, 'spec.json'), 'utf8')) as AssemblySpec : undefined;
  const extra = extraDir && extraSpec ? await readJsonLines<RecordedDecision>(await source(extraDir, extraSpec.decisions), 20000) : [];
  if (extraSpec && extraSpec.studyPolicyId !== policy.id) throw new Error('snapshot policy differs');
  const desired = new Set([...raw, ...extra].map((d) => Math.floor(d.asOf! / 1000) * 1000));
  const parameters = { epochs: 80, hidden: 8, trees: 12, seed: 17 };
  write(path.join(root, 'registration.json'), { policy, plan, parameters, events: directionStudyEvents(), declaredBeforeReplay: true,
    decoderTarget: 'Observed sustained move with at least five seconds lead before exact sale deadline; no payout, fee or settlement labels',
    nativeDirectionTarget: 'Native price-higher-at-horizon readout; reported separately from the sustained-move decoder',
    iterations: ['movement geometry prior', 'continuous TA/context', 'continuous TA/context + native S5', 'continuous TA/context + native S6'],
    researchOnly: true, liveEntryAllowed: false, autoPromote: false });
  const states: Record<string, Map<number, AtlasSnnState>> = {}, replayReports = [];
  const frozen: Array<{ variant: string; domain: string; file: string; modelId: string; evidence: FrozenSnnEvidence }> = [];
  for (const variant of ['S5', 'S6'] as const) {
    const domains: Map<number, AtlasSnnState>[] = [];
    for (const domain of ['crypto', 'perps'] as const) {
      const file = path.join(original, `observed-${domain}.tape`), sha256 = await sha256File(file), selected = new Map<number, AtlasSnnState>();
      console.log(`Native ${variant}/${domain}: direction-only replay, freeze ${new Date(policy.trainBefore).toISOString()}`);
      const report = replayAtlasSnnTape(file, { variant, domain, sourceSha256: sha256, studyPolicyId: policy.id,
        directionOnly: true, maximumInputPriceAgeMs: 3000, maximumInputGapMs: 3000, inputLagMs: 1000,
        captureAt: desired, everyMs: 1000, params: domainParams(domain), onState: (s) => selected.set(s.asOf, s),
        onFrozenModel: (model, evidence) => {
          const name = `native-${variant}-${domain}.json`; write(path.join(root, name), model);
          frozen.push({ variant, domain, file: name, modelId: digest(model), evidence });
          write(path.join(root, `native-${variant}-${domain}-evidence.json`), { variant, domain, modelId: digest(model), evidence });
        } });
      if (!report.frozenModelExported) throw new Error('native tape did not cross the registered training boundary');
      replayReports.push(report); domains.push(selected);
    }
    const combined = new Map<number, AtlasSnnState>(); states[variant] = combined;
    for (const at of [...desired].sort((a, b) => a - b)) {
      const parts = domains.map((d) => d.get(at)); if (parts.every(Boolean)) combined.set(at, combineSnnStates(parts as AtlasSnnState[]));
    }
    fs.writeFileSync(path.join(root, `states-${variant}.jsonl`), [...combined.values()].map((s) => JSON.stringify(s)).join('\n') + '\n');
  }
  const variants = [];
  for (const name of ['base', 'S5', 'S6']) {
    const dir = path.join(root, name), dest = path.join(dir, 'inputs'); fs.mkdirSync(dest, { recursive: true });
    for (const receipt of spec.indices) fs.copyFileSync(await source(inputsDir, receipt), path.join(dest, receipt.file));
    const selected = name === 'base' ? raw : raw.filter((d) => states.S5.has(Math.floor(d.asOf! / 1000) * 1000) && states.S6.has(Math.floor(d.asOf! / 1000) * 1000));
    const changed = selected.map((d) => ({ ...d, snn: name === 'base' ? null : { ...states[name].get(Math.floor(d.asOf! / 1000) * 1000)!, asOf: d.asOf } }));
    const decisions = path.join(dest, 'decisions.jsonl'); fs.writeFileSync(decisions, changed.map((d) => JSON.stringify(d)).join('\n') + '\n');
    write(path.join(dest, 'spec.json'), { ...spec, results: undefined, decisions: { file: 'decisions.jsonl', sha256: await sha256File(decisions) } });
    const manifest = await assembleMovementDataset(path.join(dest, 'spec.json'), o.policy, path.join(dir, 'dataset'));
    const data = await loadMovementDataset(path.join(dir, 'dataset'), profit);
    const rows = { train: movementRows(data.examples, plan.train, profit, policy.id), stopping: movementRows(data.examples, plan.stopping, profit, policy.id),
      calibration: movementRows(data.examples, plan.calibration, profit, policy.id) };
    const context: FeatureFamily[] = ['ta', 'dominance', 'clock', 'micro', 'daily'];
    const candidates: Array<{ name: string; family: 'smooth' | 'temporal-linear'; groups: FeatureFamily[] }> = name === 'base'
      ? [{ name: 'geometry-prior', family: 'temporal-linear', groups: [] }, { name: 'continuous-context', family: 'smooth', groups: context }]
      : [{ name: `continuous-context-${name}`, family: 'smooth', groups: [...context, 'snn'] },
        { name: `linear-context-${name}`, family: 'temporal-linear', groups: [...context, 'snn'] }];
    const fits = [];
    for (const c of candidates) {
      console.log(`Fitting ${c.name}; native and decoder weights remain research artifacts`);
      const model = fitAdvanceModel(rows, plan, profit, c.family, c.groups, parameters);
      write(path.join(dir, `${c.name}.json`), model);
      const scores = (role: 'selection' | 'audit') => scoreAdvanceModel(model, movementRows(data.examples, plan[role], profit, policy.id), profit);
      const selection = scores('selection'), audit = scores('audit');
      fs.writeFileSync(path.join(dir, `${c.name}-scores.jsonl`), [...selection.map((s) => ({ role: 'selection', ...s })), ...audit.map((s) => ({ role: 'audit', ...s }))].map((s) => JSON.stringify(s)).join('\n') + '\n');
      // Permute one group across the same rows to measure its fitted contribution.
      // This is descriptive sensitivity, not a reason to recycle audit labels for training.
      const trainSensitivity = c.groups.map((group) => {
        const names = model.featureNames.map((n, i) => ({ n, i })).filter(({ n }) => featureFamily(n) === group);
        const ps = rows.train.map((r) => binaryResponseProbability(model.head, model.featureNames.map((n) => r.values[n] ?? NaN)));
        let change = 0;
        for (let i = 0; i < rows.train.length; i++) { const x = model.featureNames.map((n) => rows.train[i].values[n] ?? NaN), other = rows.train[(i + 1) % rows.train.length];
          for (const { n, i: j } of names) x[j] = other.values[n] ?? NaN;
          change += Math.abs(binaryResponseProbability(model.head, x) - ps[i]); }
        return { group, features: names.length, meanAbsoluteProbabilityChange: rows.train.length ? change / rows.train.length : null };
      });
      fits.push({ name: c.name, id: model.id, family: model.family, features: model.featureNames.length, learnedFeatureNames: model.featureNames,
        headKind: model.head.model.kind, trainingEvents: model.head.trainingEvents, calibrated: model.head.calibrationFitted,
        selection: metric(selection), audit: metric(audit), trainSensitivity });
    }
    variants.push({ name, dataset: manifest.counts, missingSnn: raw.length - selected.length, fits });
    if (extraDir && extraSpec) {
      const extraDest = path.join(dir, 'snapshot-inputs'); fs.mkdirSync(extraDest);
      for (const receipt of extraSpec.indices) fs.copyFileSync(await source(extraDir, receipt), path.join(extraDest, receipt.file));
      const records = extra.map((d) => { const at = Math.floor(d.asOf! / 1000) * 1000, snn = states[name]?.get(at);
        return { ...d, snn: name === 'base' ? null : snn ? { ...snn, asOf: d.asOf } : null }; });
      const file = path.join(extraDest, 'decisions.jsonl'); fs.writeFileSync(file, records.map((d) => JSON.stringify(d)).join('\n') + '\n');
      write(path.join(extraDest, 'spec.json'), { ...extraSpec, results: undefined, decisions: { file: 'decisions.jsonl', sha256: await sha256File(file) } });
    }
  }
  const summary = { schema: 'atlas-native-direction-iterations-v1', policy, plan, parameters, frozen, replayReports, variants,
    sourceSpecSha256: await sha256File(specPath), researchOnly: true, liveEntryAllowed: false, autoPromote: false,
    limitations: ['Reused historical development periods, not a new forward trial', 'Native one-second replay covers the observed prefixes, not the 2017–2026 minute archive',
      'Learned continuous decoder weights are distinct from the original 406 uniformly averaged Oracle curves',
      'Calibration point estimates and one audit week do not establish reliable 60% success or live qualification',
      'No contract settlement/readout labels train this direction-only replay; no simulated minute-to-second paths'] };
  write(path.join(root, 'summary.json'), summary); return summary;
}
const arg = (name: string, fallback: string) => { const i = process.argv.indexOf(`--${name}`); return i < 0 ? fallback : process.argv[i + 1]; };
if (process.argv[1] && /(^|[/\\])runNativeDirectionStudy\.(ts|js)$/.test(process.argv[1])) void runNativeDirectionStudy({
  source: arg('source', ''), snapshots: arg('snapshots', '') || undefined,
  plan: arg('plan', 'research/opportunity/examples/prospective-prefix-plan.json'), policy: arg('policy', 'research/opportunity/examples/profit-policy.json'),
  out: arg('out', 'research/out/atlas-native-direction') }).then(() => console.log('Native direction study saved; no deployment.'))
  .catch((e) => { console.error(e instanceof Error ? e.stack : e); process.exitCode = 1; });
