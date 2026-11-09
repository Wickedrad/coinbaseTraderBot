/** Receipt-checked full snapshots and causal context from cached public recordings. */
import fs from 'node:fs';
import path from 'node:path';
import { recordingFiles } from '../../bot/marketdata/recordingFiles';
import { exportRecordingInputs } from './productCli';
import { sha256File } from './jointPathData';
import { studyPolicy } from './studyPolicy';
import { directionStudyEvents } from './directionStudyEvents';

export async function prepareDirectionSnapshots(recordings: string, out: string) {
  const policy = studyPolicy('prospective-2026-11-09-v1'), files = recordingFiles(recordings), receipts: Record<string, unknown>[] = [];
  if (!files.length) throw new Error('observed public prefixes required');
  for (const f of files) {
    const receipt = JSON.parse(fs.readFileSync(path.join(recordings, `public-${f.day}.json`), 'utf8'));
    if (receipt.observed_only !== true || receipt.book_every_ms !== 0 || receipt.last_arrival >= policy.finalFrom ||
        await sha256File(f.file) !== receipt.filtered_sha256) throw new Error('changed, sampled, synthetic or final-period recording');
    receipts.push({ day: f.day, ...receipt });
  }
  const config = { studyPolicyId: policy.id, assets: ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE'], events: directionStudyEvents(),
    everyMs: 1000, snapshotDecisionsOnly: true, executionBufferMs: 30000, maximumDecisions: 6000, maximumDecisionsPerDay: 750,
    fromDay: '2026-10-22', toDay: '2026-11-07', costs: { entryFee: 0, exitFee: 0, settlementFee: 0, slippage: 0 } };
  const configFile = path.join(path.dirname(path.resolve(out)), 'snapshot-import-config.json');
  fs.mkdirSync(path.dirname(configFile), { recursive: true }); fs.writeFileSync(configFile, JSON.stringify(config, null, 2) + '\n', { flag: 'wx' });
  const report = await exportRecordingInputs(recordings, configFile, out);
  fs.writeFileSync(path.join(out, 'prefix-receipts.json'), JSON.stringify(receipts, null, 2) + '\n', { flag: 'wx' });
  return report;
}
const arg = (name: string) => process.argv[process.argv.indexOf(`--${name}`) + 1];
if (process.argv[1] && /(^|[/\\])prepareDirectionSnapshots\.(ts|js)$/.test(process.argv[1])) void prepareDirectionSnapshots(arg('recordings'), arg('out'))
  .then((r) => console.log(JSON.stringify(r.counts))).catch((e) => { console.error(e); process.exitCode = 1; });
