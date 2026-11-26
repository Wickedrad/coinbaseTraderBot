// Audit path part B (research/audit_path/PREREG-AP.md): the lane's own call rule, run on recorded reader files.
//
// Reads one JSON object per line from the input file: { id, now, file }, where `file` is a HeatCallsFile as the reader
// publishes it (python/heat_reader) and `now` is the lane's tick time in ms. For each line it does what the lane does
// with the reader's file: parseHeatCalls (the lane's own checks), then readHeatCalls(now, cfg, snap), which
// keeps the rows no older than HEAT_ENTRY_LAG_SEC, decides one call per coin and horizon with decideCall (top N) and
// skips a pair that calls against its single. Writes one JSON line per input line: { id, fresh, unfit, notes }.
// Nothing here reads a price, a log or the bot's state. Run from the repository root after npm ci:
//   node --import tsx research/audit_path/decideCalls.ts <in.jsonl> <out.jsonl>
import fs from 'fs';
import { readHeatCalls } from '../../bot/heat/heatLane';
import { parseHeatCalls } from '../../bot/heat/heatSource';
import type { HeatConfig } from '../../bot/heat/types';

// The lane's deployed defaults (bot/config.ts, the HEAT_* settings), only the fields readHeatCalls reads.
const cfg = {
  assets: ['BTC', 'ETH', 'SOL', 'XRP'],
  horizons: [15, 60],
  topN: 10,
  maxAgeSec: 90,
  entryLagSec: 45,
  perps: 'entry',
  perpsDaily: 'context',
  pairConflict: 'skip',
} as unknown as HeatConfig;

const [inPath, outPath] = process.argv.slice(2);
if (!inPath || !outPath) {
  console.error('usage: decideCalls.ts <in.jsonl> <out.jsonl>');
  process.exit(2);
}
const lines = fs.readFileSync(inPath, 'utf8').split('\n').filter((l) => l.trim());
const out: string[] = [];
for (const line of lines) {
  const { id, now, file } = JSON.parse(line);
  const parsed = parseHeatCalls(JSON.stringify(file));
  if (parsed.snapshot === undefined) {
    out.push(JSON.stringify({ id, error: parsed.error }));
    continue;
  }
  const r = readHeatCalls(now, cfg, parsed.snapshot);
  out.push(JSON.stringify({ id, fresh: r.fresh, unfit: r.unfit, notes: r.notes }));
}
fs.writeFileSync(outPath, out.length ? out.join('\n') + '\n' : '');
