import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'fs';
import os from 'os';
import path from 'path';
import zlib from 'zlib';
import { decodeBlock, encodeBlock, encodeLines } from '../bot/marketdata/compactRecording';
import { recordingFiles, recordingLines, capRecordings } from '../bot/marketdata/recordingFiles';

const LINES = [
  JSON.stringify({ t: 1761955200123, k: 'delta', ticker: 'KXBTC15M-25NOV0215-15', side: 'bid', price: 0.53, delta: -12, ts: 1761955200120 }),
  JSON.stringify({ t: 1761955200150, k: 'delta', ticker: 'KXETH15M-25NOV0215-15', side: 'ask', price: 0.4701, delta: 3.5, ts: 1761955200149 }),
  JSON.stringify({ t: 1761955200160, k: 'book', ticker: 'X', bids: [{ price: 0.5, size: 10 }], asks: [], ts: 1761955200160 }),
  JSON.stringify({ t: 1761955200170, k: 'index', asset: 'BTC', value: 110233.123456789, ts: 1761955200170, src: null }),
  JSON.stringify({ t: 1761955200180, k: 'odd', a: 1e-7, b: 12345678901234567890, c: -0.000001, d: 'é"\\', e: true }),
  JSON.stringify({ t: 1761955200190, k: 'delta', ticker: 'KXBTC15M-25NOV0215-15', side: 'bid', price: 0.1 + 0.2, delta: 0, ts: 1761955200190 }),
  '{"t": 1, "k":"spaced"}',
  '{"t":1,"k":"torn","x":',
  '',
];

test('mdc block: every line comes back byte for byte', () => {
  assert.deepEqual(decodeBlock(encodeBlock(LINES, false)).lines, LINES);
});

test('mdc file: recordingLines reads it like the gzip, and recordingFiles prefers gzip when both exist', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mdc-'));
  const gz = path.join(dir, 'md-2026-11-01.jsonl.gz');
  fs.writeFileSync(gz, zlib.gzipSync(LINES.join('\n') + '\n'));
  const r = await encodeLines(recordingLines(gz), path.join(dir, 'md-2026-11-01.mdc'), { blockLines: 3 });
  assert.equal(r.lines, LINES.length);
  assert.equal(recordingFiles(dir)[0].file, gz);
  fs.rmSync(gz);
  const mdc = recordingFiles(dir)[0].file;
  assert.ok(mdc.endsWith('.mdc'));
  const back: string[] = [];
  for await (const l of recordingLines(mdc)) back.push(l);
  assert.deepEqual(back, LINES);
  fs.writeFileSync(path.join(dir, 'md-2026-11-02.jsonl'), '');
  fs.writeFileSync(path.join(dir, 'md-2026-11-03.jsonl'), '');
  capRecordings(dir, 2);
  assert.ok(!fs.existsSync(mdc));
});
