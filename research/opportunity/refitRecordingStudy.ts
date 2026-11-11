/** Refit a frozen observed dataset without repeating archive reads or SNN replay. */
import fs from 'node:fs';
import path from 'node:path';
import { exportContractStudy, exportPaperShadow, exportSnnComparison } from './productCli';

export async function refitRecordingStudy(o: { source: string; out: string; plan: string; paperPolicy: string }) {
  const root = path.resolve(o.out);
  if (fs.existsSync(root)) throw new Error('new refit output required');
  for (const name of ['base', 'S5', 'S6']) if (!fs.existsSync(path.join(o.source, name, 'dataset/manifest.json'))) throw new Error(`complete ${name} dataset required; a partial replay cannot be refitted`);
  fs.mkdirSync(root, { recursive: true });
  const parameters = { epochs: 40, hidden: 6, trees: 12, seed: 17 };
  fs.writeFileSync(path.join(root, 'registration.json'), JSON.stringify({ parameters,
    plan: JSON.parse(fs.readFileSync(o.plan, 'utf8')), declaredBeforeFit: true,
    purpose: 'Refit identical observed datasets with the current model/registry validation; no new labels or inputs',
    researchOnly: true, liveEntryAllowed: false, autoPromote: false }, null, 2) + '\n');
  const reports = [];
  for (const name of ['base', 'S5', 'S6']) {
    console.log(`Refitting ${name} from its verified dataset`);
    const report = await exportContractStudy(path.join(o.source, name, 'dataset'), o.plan, o.paperPolicy, path.join(root, name), parameters);
    reports.push({ name, productId: report.productId, status: report.status, blockers: report.blockers });
  }
  const products = ['S5', 'S6'].map((v) => JSON.parse(fs.readFileSync(path.join(root, v, 'product.json'), 'utf8')));
  const comparison = products.every((p) => p.study.selected && p.study.baseline)
    ? await exportSnnComparison(path.join(root, 'S5/product.json'), path.join(o.source, 'S5/dataset'),
      path.join(root, 'S6/product.json'), path.join(o.source, 'S6/dataset'), path.join(root, 'comparison'))
    : { status: 'blocked-insufficient-contract-rows', recommended: 'none', liveEntryAllowed: false };
  const shadow = await exportPaperShadow(path.join(root, 'base/product.json'), path.join(o.source, 'paper-requests.jsonl'),
    o.paperPolicy, path.join(root, 'paper-shadow'), 86400000, 'historical-audit');
  const report = { reports, comparison, shadow, researchOnly: true, liveEntryAllowed: false, autoPromote: false,
    interpretation: 'Same observations and frozen SNN states; strict current contract support. Historical paper replay is not forward evidence.' };
  fs.writeFileSync(path.join(root, 'summary.json'), JSON.stringify(report, null, 2) + '\n'); return report;
}
const arg = (name: string, fallback: string) => { const i = process.argv.indexOf(`--${name}`); return i < 0 ? fallback : process.argv[i + 1]; };
if (process.argv[1] && /(^|[/\\])refitRecordingStudy\.(ts|js)$/.test(process.argv[1])) void refitRecordingStudy({
  source: arg('source', 'research/out/atlas-recording-study'), out: arg('out', 'research/out/atlas-recording-refit'),
  plan: arg('plan', 'research/opportunity/examples/prospective-prefix-plan.json'), paperPolicy: arg('paper-policy', 'research/opportunity/examples/paper-policy.json') })
  .then((r) => console.log(`Refit complete; ${r.reports.length} products; no promotion or live trading.`))
  .catch((e) => { console.error(e instanceof Error ? e.stack : e); process.exitCode = 1; });
