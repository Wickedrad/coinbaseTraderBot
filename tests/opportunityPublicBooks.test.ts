import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { test } from 'node:test';
import { collectContractBooks } from '../research/opportunity/collectContractBooks';

test('fresh public book capture uses GET only, preserves fractional depth and withholds all performance/training claims', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-public-books-')); t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  let now = Date.UTC(2026, 10, 10, 12); const start = now, requests: string[] = [];
  const fetcher = (async (url: string, options: RequestInit) => {
    assert.equal(options.method, 'GET'); assert.equal(options.headers && 'Authorization' in options.headers, false); requests.push(url);
    return Response.json(url.includes('/orderbook') ? { orderbook_fp: { yes_dollars: [['0.4100', '12.25']], no_dollars: [['0.5800', '5.50']] } }
      : { markets: [{ ticker: 'KXBTC15M-TEST', series_ticker: 'KXBTC15M', status: 'active', open_time: new Date(start - 60000).toISOString(), close_time: new Date(start + 900000).toISOString() }] });
  }) as unknown as typeof fetch;
  const out = path.join(root, 'capture'), r = await collectContractBooks({ out, cycles: 2, assets: ['BTC'], intervalMs: 1000, fetcher, now: () => now, wait: async (ms) => { now += ms; } });
  assert.equal(requests.length, 3); assert.equal(r.counts.bothSides, 2); assert.equal(r.counts.crossed, 0);
  assert.equal(r.labelsUsedForFitting, false); assert.equal(r.forecastsPublished, false); assert.equal(r.actualProfitVerified, false); assert.equal(r.liveEntryAllowed, false);
  const books = fs.readFileSync(path.join(out, 'books.jsonl'), 'utf8').trim().split('\n').map((s) => JSON.parse(s));
  assert.deepEqual(books[0].bids, [{ price: 0.41, size: 12.25 }]); assert.deepEqual(books[0].asks, [{ price: 0.42, size: 5.5 }]);
  assert.ok(books.every((b) => b.knownAt >= b.requestedAt));
});
