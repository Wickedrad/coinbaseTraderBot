import assert from 'node:assert/strict';
import fs from 'fs';
import os from 'os';
import path from 'path';
import zlib from 'zlib';
import { test } from 'node:test';
import { loadConfig } from '../bot/config';
import { MetaModel } from '../bot/model/metaModel';
import { runBacktest } from '../research/backtest';
import { eventsOf, readRecordingBatches, readRecordings, type RecEvent } from '../research/replay';
import { writeSyntheticRecordings } from '../research/synthetic';

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'rec-batches-test-'));
const all = async (it: AsyncIterable<RecEvent>) => { const out: string[] = []; for await (const e of it) out.push(JSON.stringify(e)); return out; };

// Day files with what the per-line reader has to cope with: several gzip members (the recorder appends one every few
// seconds), CRLF and lone-CR line ends, empty and torn lines, multi-byte characters, same-time instants (ties), a plain
// file without a trailing newline, and more than one read chunk (lines and characters cut by chunk edges).
function writeDays(dir: string): void {
  fs.mkdirSync(dir, { recursive: true });
  const t0 = Date.parse('2026-10-26T00:00:00Z');
  const rows: string[] = [];
  for (let i = 0; i < 40_000; i++) {
    const t = t0 + Math.floor(i / 3) * 250; // three events per instant: ties
    rows.push(JSON.stringify({ t, k: i % 7 ? 'delta' : 'trade', ticker: `KXBTC15M-26OCT26-${i % 11}`, price: (i % 97) / 100, note: i % 13 ? 'ü€𝄞' : 'x' }));
  }
  rows.splice(100, 0, '', '{"t":17'); // an empty and a torn line
  let text = '';
  rows.forEach((r, i) => { text += r + (i % 5 === 0 ? '\r\n' : i % 17 === 0 ? '\r' : '\n'); });
  const buf = Buffer.from(text, 'utf8');
  const members: Buffer[] = [];
  for (let at = 0; at < buf.length; at += 300_001) members.push(zlib.gzipSync(buf.subarray(at, at + 300_001))); // cuts lines and characters
  fs.writeFileSync(path.join(dir, 'md-2026-10-26.jsonl.gz'), Buffer.concat(members));
  const t1 = Date.parse('2026-10-27T00:00:00Z');
  const plain = Array.from({ length: 30_000 }, (_, i) => JSON.stringify({ t: t1 + Math.floor(i / 2) * 500, k: 'book', ticker: 'KXETHD-27OCT', s: 'ε'.repeat(i % 5) })).join('\n');
  fs.writeFileSync(path.join(dir, 'md-2026-10-27.jsonl'), plain); // no trailing newline
}

test('batched recording reader: the same events, order and tie flags as the per-line reader', async () => {
  const dir = tmp();
  writeDays(dir);
  const a = await all(readRecordings(dir, ''));
  const b = await all(eventsOf(readRecordingBatches(dir, '')));
  assert.ok(a.length > 60_000 && a.some((x) => x.includes('"tie":true')));
  assert.equal(b.length, a.length);
  assert.deepEqual(b, a);
  // A line filter: the declined lines come through as the same { t, k: 'skip' } stubs.
  const keep = (k: string) => k !== 'delta';
  assert.deepEqual(await all(eventsOf(readRecordingBatches(dir, '', undefined, undefined, keep))), await all(readRecordings(dir, '', undefined, undefined, keep)));
});

test('batched recording reader: lines before minT dropped unparsed; from the first kept event on, nothing changes', async () => {
  const dir = tmp();
  writeDays(dir);
  const a = (await all(readRecordings(dir, ''))).map((x) => JSON.parse(x) as RecEvent);
  const minT = a[Math.floor(a.length / 3)].t; // mid-instant in the first file
  const first = a.findIndex((e) => !(e.t < minT));
  const b = await all(eventsOf(readRecordingBatches(dir, '', undefined, undefined, undefined, minT)));
  assert.deepEqual(b, a.slice(first).map((e) => JSON.stringify(e)));
});

test('backtest batchedReader: the same replay as the per-line reader', async () => {
  const dir = path.join(tmp(), 'rec');
  writeSyntheticRecordings(dir, { windows: 6, seed: 12, marketNoise: 0.06 });
  const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), STRATEGY_STYLE: 'both', FV_ENTRY_GATE: 'false', LOSER_CUT: 'false', LOSER_WINDOW_CUT: 'false' });
  const first = (await all(readRecordings(dir, '')))[0];
  const startMs = (JSON.parse(first) as RecEvent).t + 30 * 60_000;
  for (const o of [{}, { startMs }]) {
    const run = (batchedReader: boolean) => runBacktest(dir, MetaModel.identity(), cfg.strategy, cfg.risk, 200, { exitPolicy: 'take_profit', batchedReader, ...o });
    const [x, y] = [await run(false), await run(true)];
    const pick = (r: typeof x) => JSON.stringify({ trades: r.trades, windows: [...r.windows], fills: r.fills, evals: r.entryEvaluations, end: r.end, days: r.days });
    assert.ok(x.trades.length > 0);
    assert.equal(pick(y), pick(x));
  }
});
