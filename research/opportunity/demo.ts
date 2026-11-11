/** Reproducible software demonstration. All prices, contracts and relationships are synthetic. */
import fs from 'node:fs';
import path from 'node:path';
import { ATLAS_FEATURE_SCHEMA } from './features';
import { TANET_SCHEMA } from '../../bot/ta/taNet';
import { sha256File } from './jointPathData';
import { rng } from '../stats';
import type { AssemblySpec, RecordedDecision } from './productCli';
import type { ContractStudyPlan } from './contractLearner';
import type { PaperPolicy } from './paper';

export async function writeProductDemoInputs(dir: string) {
  fs.mkdirSync(dir);
  const start = Date.UTC(2023, 0, 2), interval = 180000, random = rng(71);
  const index = fs.openSync(path.join(dir, 'index.jsonl'), 'wx'), decisions = fs.openSync(path.join(dir, 'decisions.jsonl'), 'wx'), results = fs.openSync(path.join(dir, 'results.jsonl'), 'wx');
  const event = { id: 'synthetic-sustained-move-v1', kind: 'move' as const, direction: 'up' as const, thresholdBps: 20,
    sustainSec: 3, sustainFraction: 0.8, priorWindowSec: 0, priorDriftBps: 0 };
  try { for (let i = 0; i < 740; i++) {
    const at = start + i * interval, x = random() * 2 - 1, z = random() * 2 - 1, p = 1 / (1 + Math.exp(-7 * x * z));
    const move = random() < p, pays = random() < p, ticker = `SYNTHETIC-${i}`;
    for (let s = 0; s <= 120; s++) fs.writeSync(index, JSON.stringify({ ts: at + s * 1000, knownAt: at + s * 1000,
      value: s === 0 ? 100 : s >= 60 ? pays ? 100.08 : 99.98 : move && s >= 20 ? 100.3 : 100 }) + '\n');
    const d: RecordedDecision = { frame: { schema: ATLAS_FEATURE_SCHEMA, taSchema: TANET_SCHEMA, engine: 'builtin', asset: 'BTC', decisionAt: at,
      session: 'asia', gapsSeen: 0, groups: { spot_1m: { source: 'synthetic-demonstration-only', sha256: null, timeframe: '1m', status: 'ready', bars: 1,
        firstOpen: at - 60000, lastOpen: at - 60000, knownAt: at, publicationLagMs: 0, timing: 'synthetic demonstration', values: { x, z } } } },
      contract: { ticker, asset: 'BTC', openTime: at - 780000, closeTime: at + 120000, termsKnownAt: at - 780000,
        terms: { kind: 'greater', strike: 100.05 }, settlementReference: 'SYNTHETIC-INDEX' }, event, side: 'yes', executionBufferMs: 10000,
      quote: { ticker, side: 'yes', at, knownAt: at, bid: 0.39, ask: 0.4, bidSize: 10, askSize: 10,
        entryFee: 0.01, exitFee: 0.01, settlementFee: 0, slippage: 0.005, sourceSha256: 'a'.repeat(64) } };
    fs.writeSync(decisions, JSON.stringify(d) + '\n'); fs.writeSync(results, JSON.stringify({ ticker, yes: pays, knownAt: at + 120000 }) + '\n');
  } } finally { fs.closeSync(index); fs.closeSync(decisions); fs.closeSync(results); }
  const spec: AssemblySpec = { schema: 'opportunity-recording-spec-v1', knownBy: start + 740 * interval,
    indices: [{ file: 'index.jsonl', sha256: await sha256File(path.join(dir, 'index.jsonl')), asset: 'BTC', reference: 'SYNTHETIC-INDEX', basis: 'synthetic-fixture' }],
    decisions: { file: 'decisions.jsonl', sha256: await sha256File(path.join(dir, 'decisions.jsonl')) },
    results: { file: 'results.jsonl', sha256: await sha256File(path.join(dir, 'results.jsonl')) } };
  fs.writeFileSync(path.join(dir, 'spec.json'), JSON.stringify(spec, null, 2) + '\n');
  const w = (a: number, b: number) => ({ from: start + a * interval, through: start + b * interval });
  const plan: ContractStudyPlan = { train: w(0, 360), stopping: w(361, 421), calibration: w(422, 522), selection: w(523, 623), audit: w(624, 724), embargoMs: interval };
  const policy: PaperPolicy = { minimumMoveLowerBound: 0.8, minimumJointLowerBound: 0.7, minimumEntryEdge: 0.02, maximumQuoteAgeMs: 2000, maximumPosition: 10 };
  fs.writeFileSync(path.join(dir, 'plan.json'), JSON.stringify(plan, null, 2) + '\n'); fs.writeFileSync(path.join(dir, 'policy.json'), JSON.stringify(policy, null, 2) + '\n');
}
