import './tmpScope'; // one temp folder per run, removed at exit
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
  '{}',
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

test('mdc block: CSV rows (candles, funding) round trip, odd fields kept', () => {
  const csv = ['ts,o,h,l,c,v', '1500000000000,4261.48,4261.48,4261.48,4261.48,1.775183', '1500000060000,4261.5,4280,4261.48,4270.01,0', '1500000120000,01.50,,x,-0,1e-7', 'a,"b,c",d', '1500000180000,4270.01,4271,4269,4270,12.5'];
  assert.deepEqual(decodeBlock(encodeBlock(csv, true)).lines, csv);
});

test('mdc numbers: fixed-point digits match how JS prints them, or the column is kept as text', () => {
  const vals: number[] = [];
  for (let i = 0; i < 20000; i++) vals.push(Math.round((Math.random() - 0.5) * 10 ** (1 + (i % 12))) / 10 ** (i % 9));
  vals.push(0, -0, 1e-7, 123456789.12345678, 1761955200123, 0.1 + 0.2, 5e-324, 1e21, -1e-6);
  const lines = vals.map((v, i) => JSON.stringify({ t: i, v }));
  assert.deepEqual(decodeBlock(encodeBlock(lines, true)).lines, lines);
  const csv = vals.map((v, i) => `${i},${v}`);
  assert.deepEqual(decodeBlock(encodeBlock(csv, true)).lines, csv);
});

test('mdc file: blocks decoded on worker threads come back in order, byte for byte', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mdcw-'));
  const lines = Array.from({ length: 5000 }, (_, i) => JSON.stringify({ t: 1761955200000 + i, k: i % 7 ? 'delta' : 'trade', ticker: `T${i % 13}`, price: (i % 99) / 100, ts: 1761955200000 + i }));
  const f = path.join(dir, 'md-2026-11-01.mdc');
  await encodeLines(lines, f, { blockLines: 400, level: 3 });
  const prev = { min: process.env.MDC_WORKER_MIN_BYTES, n: process.env.MDC_WORKERS };
  process.env.MDC_WORKER_MIN_BYTES = '0'; process.env.MDC_WORKERS = '2';
  try {
    const back: string[] = [];
    for await (const l of recordingLines(f)) back.push(l);
    assert.deepEqual(back, lines);
  } finally {
    if (prev.min === undefined) delete process.env.MDC_WORKER_MIN_BYTES; else process.env.MDC_WORKER_MIN_BYTES = prev.min;
    if (prev.n === undefined) delete process.env.MDC_WORKERS; else process.env.MDC_WORKERS = prev.n;
  }
});
