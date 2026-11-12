// Memory reading (bot/util/memoryWatch.ts): the heap figures, the walk over the bot's objects (paths, sizes, sampling,
// cycles, getters and proxies left alone, the object cap), and the watch's first / hourly / fresh readings.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { AddressInfo } from 'node:net';
import { heapReading, MemoryWatch, walkCollections } from '../bot/util/memoryWatch';
import { createApi, type ApiDeps } from '../bot/api/server';
import { loadConfig } from '../bot/config';

test('heap reading: resident set, heap, external memory and the heap spaces, in MB', () => {
  const h = heapReading(123);
  assert.equal(h.at, 123);
  assert.ok(h.rssMb > 0 && h.heapUsedMb > 0 && h.heapTotalMb >= h.heapUsedMb);
  assert.ok(h.externalMb >= h.arrayBuffersMb);
  assert.ok('old' in h.spaces && 'new' in h.spaces, JSON.stringify(h.spaces));
});

test('walk: maps, sets, arrays and records by path, entries sampled, small ones left out', () => {
  class Book { levels = Array.from({ length: 80 }, (_, i) => i); }
  class Engine {
    status = new Map(Array.from({ length: 120 }, (_, i) => [`T${i}`, { history: Array.from({ length: i + 1 }, () => 0) }]));
    seen = new Set(Array.from({ length: 60 }, (_, i) => i));
    small = new Map([['a', 1]]);
    books = { BTC: new Book() };
    byTicker: Record<string, { n: number }> = Object.fromEntries(Array.from({ length: 70 }, (_, i) => [`K${i}`, { n: i }]));
  }
  const w = walkCollections({ engine: new Engine() });
  const by = Object.fromEntries(w.sizes.map((s) => [s.path, s]));
  assert.deepEqual(by['engine.status'], { path: 'engine.status', kind: 'map', n: 120 });
  // Entries looked at: the first, the middle and the last; the largest of them is listed.
  assert.deepEqual(by['engine.status[*].history'], { path: 'engine.status[*].history', kind: 'array', n: 120 });
  assert.equal(by['engine.seen'].kind, 'set');
  assert.equal(by['engine.books.BTC.levels'].n, 80);
  assert.deepEqual(by['engine.byTicker'], { path: 'engine.byTicker', kind: 'record', n: 70 });
  assert.equal(by['engine.small'], undefined, 'under minSize');
  assert.ok(w.sizes[0].n >= w.sizes[w.sizes.length - 1].n, 'largest first');
  assert.equal(w.capped, false);
});

test('walk: long strings and large buffers are listed; cycles end; the shortest path names a shared object', () => {
  const shared = { rows: Array.from({ length: 55 }, () => 1) };
  const a: Record<string, unknown> = { text: 'x'.repeat(150_000), buf: Buffer.alloc(200_000), shared };
  const b: Record<string, unknown> = { deep: { deeper: { shared } } };
  a.self = a; b.a = a;
  const w = walkCollections({ a, b });
  const by = Object.fromEntries(w.sizes.map((s) => [s.path, s]));
  assert.deepEqual(by['a.text'], { path: 'a.text', kind: 'string', n: 150_000 });
  assert.deepEqual(by['a.buf'], { path: 'a.buf', kind: 'bytes', n: 200_000 });
  assert.equal(by['a.shared.rows'].n, 55);
  assert.equal(by['b.deep.deeper.shared.rows'], undefined, 'one visit per object');
});

test('walk: a Map or Set subclass is sized by the built-in, never by its own getter', () => {
  class Loud extends Map<number, number> { override get size(): number { throw new Error('own size getter called'); } }
  const m = new Loud(); for (let i = 0; i < 70; i++) Map.prototype.set.call(m, i, i);
  const w = walkCollections({ m });
  assert.deepEqual(w.sizes[0], { path: 'm', kind: 'map', n: 70 });
});

test('memory watch: strings and buffers are listed apart from entry counts', () => {
  const w = new MemoryWatch(() => ({ e: { text: 'z'.repeat(130_000), list: Array.from({ length: 60 }, () => 0) } }));
  const s = w.status(1);
  assert.deepEqual(s.largest.map((r) => r.path), ['e.list']);
  assert.deepEqual(s.blobs.map((r) => [r.path, r.kind, r.n]), [['e.text', 'string', 130_000]]);
});

test('walk: getters are never called and proxies never entered', () => {
  const o = { list: Array.from({ length: 60 }, () => 0) };
  Object.defineProperty(o, 'boom', { enumerable: true, get() { throw new Error('getter called'); } });
  const p = new Proxy({}, { ownKeys() { throw new Error('proxy entered'); }, get() { throw new Error('proxy entered'); }, getOwnPropertyDescriptor() { throw new Error('proxy entered'); } });
  const w = walkCollections({ o, p });
  assert.equal(w.sizes.find((s) => s.path === 'o.list')?.n, 60);
});

test('walk: stops at the object cap and says so', () => {
  const root: Record<string, unknown> = {};
  let cur = root;
  for (let i = 0; i < 40; i++) { const n: Record<string, unknown> = { pad: i }; cur.next = n; cur = n; }
  const w = walkCollections({ root }, { maxObjects: 10, maxDepth: 100 });
  assert.equal(w.capped, true);
  assert.equal(w.objects, 10);
});

test('memory watch: the first reading stays the baseline; status shows the first, an hour ago and now, and what grew', () => {
  const engine = { orders: new Map<number, number>(), fixed: Array.from({ length: 60 }, () => 0) };
  const fill = (n: number) => { for (let i = engine.orders.size; i < n; i++) engine.orders.set(i, i); };
  const w = new MemoryWatch(() => ({ engine }));
  const t0 = 1_000_000_000;
  fill(100); w.record(t0);
  fill(250); w.record(t0 + 3_600_000);
  fill(400);
  const s = w.status(t0 + 7_200_000);
  const orders = s.largest.find((r) => r.path === 'engine.orders')!;
  assert.deepEqual(orders, { path: 'engine.orders', kind: 'map', n: 400, atFirst: 100, hourAgo: 250 });
  assert.equal(s.grown[0].path, 'engine.orders');
  assert.equal(s.grown.find((r) => r.path === 'engine.fixed'), undefined, 'unchanged is not grown');
  assert.equal(s.first?.at, t0);
  assert.equal(s.hourAgo?.at, t0 + 3_600_000);
  assert.equal(s.history.length, 2);
  assert.ok(s.history[0].rssMb > 0 && s.history[0].heapUsedMb > 0);
  // A fresh walk at most once a minute: a status asked again within the minute is the same reading.
  fill(500);
  assert.equal(w.status(t0 + 7_230_000).largest.find((r) => r.path === 'engine.orders')!.n, 400);
  assert.equal(w.status(t0 + 7_260_000).largest.find((r) => r.path === 'engine.orders')!.n, 500);
});

test('memory watch: before the first reading there is no baseline; start() timers do not hold the process', () => {
  const w = new MemoryWatch(() => ({ x: { list: Array.from({ length: 60 }, () => 0) } }), { firstAfterMs: 3_600_000 });
  w.start();
  const s = w.status(5);
  assert.equal(s.first, null);
  assert.deepEqual(s.grown, []);
  assert.equal(s.largest[0].atFirst, null);
  w.stop();
});

test('operator API: /api/memory serves the watch, null without one', async () => {
  const cfg = loadConfig({});
  const serve = async (extra: Partial<ApiDeps>) => {
    const base = { cfg, startedAt: Date.now(), audit: { write: () => undefined }, ...extra } as unknown as ApiDeps;
    const deps = new Proxy(base, { get: (t, k) => (k in t ? (t as any)[k] : undefined) });
    const srv = createApi(deps).listen(0);
    await new Promise((r) => srv.once('listening', r));
    const r = await fetch(`http://127.0.0.1:${(srv.address() as AddressInfo).port}/api/memory`);
    const j = await r.json();
    srv.close();
    return { status: r.status, j: j as any };
  };
  assert.deepEqual(await serve({}), { status: 200, j: null });
  const w = new MemoryWatch(() => ({ m: { big: new Set(Array.from({ length: 70 }, (_, i) => i)) } }));
  const got = await serve({ memory: w });
  assert.equal(got.status, 200);
  assert.equal(got.j.largest[0].path, 'm.big');
  assert.ok(got.j.now.heapUsedMb > 0);
});
