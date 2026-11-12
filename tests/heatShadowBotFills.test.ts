import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { gzipSync } from 'node:zlib';
import { openingPart, readOpeningFills } from '../research/heatmap_live/botFills';

const fill = (side: 'bid' | 'ask', count: number, price: number, position: number, ticker = 'KXBTC15M-26NOV111030-30', fee = 0.2) =>
  ({ fill: { ticker, side, count, price, ts: 1000 }, fee, position });

test('opening fills: buys of YES or NO that grow the position, split when a fill goes through zero', () => {
  assert.deepEqual(openingPart(fill('bid', 20, 0.48, 20)), { ticker: 'KXBTC15M-26NOV111030-30', side: 'yes', ts: 1000, price: 0.48, count: 20, fee: 0.2 });
  assert.deepEqual(openingPart(fill('ask', 20, 0.48, -20))!.side, 'no');
  assert.equal(openingPart(fill('ask', 20, 0.48, -20))!.price, 0.52, 'a NO bought through a YES ask costs 1 minus the YES price');
  assert.equal(openingPart(fill('bid', 10, 0.5, 30))!.count, 10, 'adding to a long');
  assert.equal(openingPart(fill('ask', 10, 0.6, 10)), undefined, 'selling part of a long is an exit');
  assert.equal(openingPart(fill('ask', 20, 0.6, 0)), undefined, 'closing a long is an exit');
  const through = openingPart(fill('ask', 30, 0.6, -10))!;
  assert.deepEqual([through.side, through.count, through.price, through.fee], ['no', 10, 0.4, 0.0667]);
  assert.equal(openingPart(fill('bid', 20, 0.48, 20, 'KXDOGE15M-X')), undefined, 'no DOGE');
  assert.equal(openingPart(fill('bid', 20, 0.48, 20, 'KXATPMATCH-X')), undefined, 'only the coin series');
  assert.equal(openingPart({ fee: 0, position: 1 }), undefined);
});

test('reads plain and gzipped audit day files, in a time range', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'audit-'));
  const line = (kind: string, data: unknown) => JSON.stringify({ seq: 1, ts: 'x', kind, data });
  fs.writeFileSync(path.join(dir, 'audit-2026-11-11.jsonl'), [line('decision', { ticker: 'x' }), line('fill', fill('bid', 20, 0.48, 20)), 'not json', line('fill', fill('ask', 20, 0.6, 0))].join('\n'));
  fs.writeFileSync(path.join(dir, 'audit-2026-11-11.1.jsonl.gz'), gzipSync(line('fill', { ...fill('ask', 5, 0.3, -5), fill: { ...fill('ask', 5, 0.3, -5).fill, ts: 5000 } }) + '\n'));
  fs.writeFileSync(path.join(dir, 'paper_exchange.json'), '{}');
  const all = await readOpeningFills(dir, 0, 10_000);
  assert.deepEqual([all.files, all.fillLines, all.fills.length], [2, 3, 2]);
  assert.equal((await readOpeningFills(dir, 2000, 10_000)).fills.length, 1);
});
