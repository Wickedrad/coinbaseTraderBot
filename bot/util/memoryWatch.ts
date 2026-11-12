// Memory reading (read-only): where the bot's memory goes, so a climb can be traced to the part that holds it.
// The V8 heap and what sits outside it (external memory, array buffers), the heap's spaces, and the largest
// collections reachable from the bot's main objects: Map, Set and Array sizes, records used as maps (many keys),
// long strings and large buffers. Each is kept as it stood at the first reading after start and once an hour,
// so the operator API (/api/memory) shows what grew. Nothing here changes the bot: properties are read as data
// (getters are never called, proxies are never entered) and the walk is bounded.

import v8 from 'v8';
import { types } from 'util';

const mb = (x: number): number => +(x / 1e6).toFixed(1);

/** The process's memory now, in MB: resident set, V8 heap (used, reserved), memory outside the heap that JS objects
 *  hold (external, which includes array buffers and Node Buffers), and the used size of each heap space ("old" holds
 *  long-lived objects, "large_object" single objects over about 128 KB such as big strings and arrays). */
export interface HeapReading {
  at: number;
  rssMb: number;
  heapUsedMb: number;
  heapTotalMb: number;
  externalMb: number;
  arrayBuffersMb: number;
  spaces: Record<string, number>;
}

export function heapReading(now = Date.now()): HeapReading {
  const m = process.memoryUsage();
  const spaces: Record<string, number> = {};
  for (const s of v8.getHeapSpaceStatistics()) spaces[s.space_name.replace(/_space$/, '')] = mb(s.space_used_size);
  return { at: now, rssMb: mb(m.rss), heapUsedMb: mb(m.heapUsed), heapTotalMb: mb(m.heapTotal), externalMb: mb(m.external), arrayBuffersMb: mb(m.arrayBuffers), spaces };
}

/** One collection found by the walk. `n` counts entries (map, set, array, record keys), characters (string) or
 *  bytes (bytes). The path names the field from a root: `engine.status`, `[*]` for an entry of a collection (the
 *  largest of the entries looked at). */
export interface CollectionSize {
  path: string;
  kind: 'map' | 'set' | 'array' | 'record' | 'string' | 'bytes';
  n: number;
}

export interface WalkOptions {
  /** Field levels below a root that are opened (default 6). */
  maxDepth?: number;
  /** Objects opened at most (default 20000): the walk stops there and says so. */
  maxObjects?: number;
  /** Collections smaller than this are not listed (default 50). Strings are listed from 100,000 characters and
   *  buffers from 100 KB. */
  minSize?: number;
  /** A plain object with at least this many keys is a record used as a map (default 50): it is counted and only a
   *  few of its values are opened, like a Map's. */
  recordKeys?: number;
}

export interface WalkResult {
  sizes: CollectionSize[];
  /** Objects opened. */
  objects: number;
  /** True when maxObjects stopped the walk before it was done. */
  capped: boolean;
  ms: number;
}

// The built-in size and values of Map and Set, so a subclass's own getter is never what is called.
const mapSize = Object.getOwnPropertyDescriptor(Map.prototype, 'size')!.get!;
const setSize = Object.getOwnPropertyDescriptor(Set.prototype, 'size')!.get!;
const mapValues = Map.prototype.values;
const setValues = Set.prototype.values;

const BIG_STRING = 100_000;
const BIG_BYTES = 100_000;
/** Entries of a collection opened: the first, the middle and the last (one of a very large Map or Set is the
 *  first three, so the walk never iterates millions of entries). */
const SAMPLE_ITERATE_MAX = 200_000;

function samplesOf<T>(items: Iterable<T>, size: number): T[] {
  if (size === 0) return [];
  const want = new Set(size > SAMPLE_ITERATE_MAX ? [0, 1, 2] : [0, Math.floor(size / 2), size - 1]);
  const last = Math.max(...want);
  const out: T[] = [];
  let i = 0;
  for (const v of items) {
    if (want.has(i)) out.push(v);
    if (++i > last) break;
  }
  return out;
}

/** Breadth-first walk from the roots (so a path is the shortest one to its collection), one visit per object. */
export function walkCollections(roots: Record<string, unknown>, o: WalkOptions = {}): WalkResult {
  const t0 = performance.now();
  const maxDepth = o.maxDepth ?? 6, maxObjects = o.maxObjects ?? 20_000, minSize = o.minSize ?? 50, recordKeys = o.recordKeys ?? 50;
  const found = new Map<string, CollectionSize>();
  const note = (path: string, kind: CollectionSize['kind'], n: number) => {
    const had = found.get(path);
    if (!had || n > had.n) found.set(path, { path, kind, n });
  };
  const seen = new WeakSet<object>();
  let queue: Array<{ v: unknown; path: string; depth: number }> = Object.entries(roots).map(([k, v]) => ({ v, path: k, depth: 0 }));
  let objects = 0, capped = false;
  while (queue.length) {
    const next: typeof queue = [];
    for (const { v, path, depth } of queue) {
      if (typeof v === 'string') { if (v.length >= BIG_STRING) note(path, 'string', v.length); continue; }
      if (v === null || typeof v !== 'object') continue; // functions, numbers, ...: nothing to open
      if (seen.has(v)) continue;
      if (objects >= maxObjects) { capped = true; break; }
      seen.add(v);
      objects++;
      if (types.isProxy(v)) continue;
      const open = (child: unknown, p: string) => { if (depth < maxDepth) next.push({ v: child, path: p, depth: depth + 1 }); };
      if (ArrayBuffer.isView(v) || v instanceof ArrayBuffer || types.isSharedArrayBuffer(v)) {
        const bytes = (v as ArrayBuffer | ArrayBufferView).byteLength;
        if (bytes >= BIG_BYTES) note(path, 'bytes', bytes);
        continue;
      }
      if (types.isMap(v)) {
        const n = mapSize.call(v) as number;
        if (n >= minSize) note(path, 'map', n);
        for (const x of samplesOf(mapValues.call(v) as Iterable<unknown>, n)) open(x, `${path}[*]`);
        continue;
      }
      if (types.isSet(v)) {
        const n = setSize.call(v) as number;
        if (n >= minSize) note(path, 'set', n);
        for (const x of samplesOf(setValues.call(v) as Iterable<unknown>, n)) open(x, `${path}[*]`);
        continue;
      }
      if (Array.isArray(v)) {
        if (v.length >= minSize) note(path, 'array', v.length);
        const n = v.length;
        for (const i of n ? [...new Set([0, Math.floor(n / 2), n - 1])] : []) {
          const d = Object.getOwnPropertyDescriptor(v, i);
          if (d && 'value' in d) open(d.value, `${path}[*]`);
        }
        continue;
      }
      if (v instanceof WeakMap || v instanceof WeakSet || v instanceof Promise || v instanceof WeakRef) continue;
      const keys = Object.keys(v);
      const asRecord = keys.length >= recordKeys;
      if (asRecord) note(path, 'record', keys.length);
      for (const k of asRecord ? samplesOf(keys, keys.length) : keys) {
        // Data properties only: a getter could do work or change something.
        const d = Object.getOwnPropertyDescriptor(v, k);
        if (!d || !('value' in d)) continue;
        open(d.value, asRecord ? `${path}[*]` : `${path}.${k}`);
      }
    }
    if (capped) break;
    queue = next;
  }
  const sizes = [...found.values()].filter((s) => (s.kind === 'string' ? s.n >= BIG_STRING : s.kind === 'bytes' ? s.n >= BIG_BYTES : s.n >= minSize)).sort((a, b) => b.n - a.n);
  return { sizes, objects, capped, ms: +(performance.now() - t0).toFixed(1) };
}

interface Snapshot { at: number; heap: HeapReading; sizes: Map<string, CollectionSize>; objects: number; capped: boolean; ms: number }

export interface MemoryWatchOptions extends WalkOptions {
  /** The first reading, this long after start (default 5 minutes: markets, books and models are loaded by then). */
  firstAfterMs?: number;
  /** A reading is kept this often (default an hour), the last 24. */
  everyMs?: number;
  /** Rows in the status (default 25 largest, 10 most grown). */
  top?: number;
}

/** Keeps the first reading after start and one an hour; status() adds a fresh one (at most once a minute). */
export class MemoryWatch {
  private first?: Snapshot;
  private hourly: Snapshot[] = [];
  private fresh?: Snapshot;
  private timers: NodeJS.Timeout[] = [];
  constructor(private readonly roots: () => Record<string, unknown>, private readonly o: MemoryWatchOptions = {}) {}

  start(): void {
    const t = setTimeout(() => {
      this.record();
      const i = setInterval(() => this.record(), this.o.everyMs ?? 3_600_000);
      i.unref();
      this.timers.push(i);
    }, this.o.firstAfterMs ?? 300_000);
    t.unref();
    this.timers.push(t);
  }

  stop(): void { for (const t of this.timers) clearTimeout(t); this.timers = []; }

  private read(now: number): Snapshot {
    const w = walkCollections(this.roots(), this.o);
    return { at: now, heap: heapReading(now), sizes: new Map(w.sizes.map((s) => [s.path, s])), objects: w.objects, capped: w.capped, ms: w.ms };
  }

  /** Take a reading and keep it (the first one stays as the baseline). */
  record(now = Date.now()): void {
    const s = this.read(now);
    this.first ??= s;
    this.hourly.push(s);
    if (this.hourly.length > 24) this.hourly.shift();
    this.fresh = s;
  }

  status(now = Date.now()) {
    if (!this.fresh || now - this.fresh.at >= 60_000) this.fresh = this.read(now);
    const cur = this.fresh, first = this.first;
    // The kept reading closest to an hour before this one (none when the oldest is under 30 minutes old).
    const hourAgo = this.hourly.filter((h) => cur.at - h.at >= 1_800_000).sort((a, b) => Math.abs(cur.at - a.at - 3_600_000) - Math.abs(cur.at - b.at - 3_600_000))[0];
    const top = this.o.top ?? 25;
    const row = (s: CollectionSize) => ({ path: s.path, kind: s.kind, n: s.n, atFirst: first?.sizes.get(s.path)?.n ?? null, hourAgo: hourAgo?.sizes.get(s.path)?.n ?? null });
    // Entries (maps, sets, arrays, records) and sizes in characters or bytes (strings, buffers) are listed apart.
    const isBlob = (s: CollectionSize) => s.kind === 'string' || s.kind === 'bytes';
    const all = [...cur.sizes.values()].filter((s) => !isBlob(s));
    const blobs = [...cur.sizes.values()].filter(isBlob).sort((a, b) => b.n - a.n).slice(0, 10).map(row);
    const grown = first ? all.map((s) => ({ s, d: s.n - (first.sizes.get(s.path)?.n ?? 0) })).filter((x) => x.d > 0).sort((a, b) => b.d - a.d).slice(0, Math.min(10, top)).map((x) => row(x.s)) : [];
    const heapRow = (h: HeapReading) => ({ at: h.at, rssMb: h.rssMb, heapUsedMb: h.heapUsedMb, externalMb: h.externalMb, arrayBuffersMb: h.arrayBuffersMb, oldMb: h.spaces.old ?? null, largeObjectMb: h.spaces.large_object ?? null });
    return {
      now: cur.heap,
      first: first ? { at: first.at, heap: first.heap } : null,
      hourAgo: hourAgo ? { at: hourAgo.at, heap: hourAgo.heap } : null,
      walk: { at: cur.at, objects: cur.objects, capped: cur.capped, ms: cur.ms },
      largest: all.sort((a, b) => b.n - a.n).slice(0, top).map(row),
      grown,
      blobs,
      history: this.hourly.map((h) => heapRow(h.heap)),
    };
  }
}
