// Compact recordings: md-YYYY-MM-DD.mdc, a lossless columnar form of a day's md-*.jsonl(.gz) that gives back the very
// same lines, byte for byte, through recordingLines() (bot/marketdata/recordingFiles.ts).
//
// Why: the bot writes each day as gzip in small members (one every ~10 s, so a crash loses little), and every member
// starts gzip's dictionary over, which leaves the day ~10x smaller than plain at best. Most lines repeat the same few
// shapes ({"t":..,"k":"delta","ticker":..,"side":..,"price":..,"delta":..,"ts":..}), so the format stores each shape's
// keys once and each field as its own column: timestamps as small deltas, prices and counts as scaled integers,
// tickers and sides through a dictionary. Like Watney's hex wheel, a small agreed alphabet carries the same message in
// far fewer symbols; zstd then squeezes the columns.
//
// Layout: "MDC1\n", then blocks of [u32 LE byte length][zstd frame]. A block holds up to BLOCK_LINES lines:
//   varint nLines, byte endsWithNewline, varint nShapes, shapes (length-prefixed JSON [keys, types]),
//   shape id per line (varint; 0 = a raw line kept verbatim), raw lines (length-prefixed), then per shape, per key, a
//   column: tag 0 number (varint scale, byte delta?, zigzag varints), 1 string dictionary (varint n, entries,
//   indices), 2 JSON text (length-prefixed). Plain CSV rows (no quotes) are columns too: their shape is
//   [null, types] and a row is its values joined by commas, so candle and funding CSVs shrink the same way. Any line that would not come back identical is stored raw, and
//   encodeDay() checks the round trip of every block before it writes it.

import fs from 'fs';
import os from 'os';
import path from 'path';
import { pathToFileURL } from 'url';
import { Worker } from 'worker_threads';
import zlib from 'zlib';
import { isAscii } from 'buffer';

export const MDC_MAGIC = Buffer.from('MDC1\n');
const BLOCK_LINES = 1_000_000;
const MAX_SCALE = 8;
const POW = Array.from({ length: MAX_SCALE + 1 }, (_, i) => 10 ** i);

export interface MdcOpts { level?: number; windowLog?: number; blockLines?: number }

function zstdAvailable(): boolean { return typeof (zlib as { zstdCompressSync?: unknown }).zstdCompressSync === 'function'; }
function needZstd(): void {
  if (!zstdAvailable()) throw new Error(`compact recordings (.mdc) need Node with built-in zstd (22.15+ / 23.8+); this is ${process.version}`);
}

// ---------- byte writer / reader ----------
class W {
  buf = Buffer.allocUnsafe(1 << 16);
  n = 0;
  private room(k: number): void {
    if (this.n + k <= this.buf.length) return;
    let size = this.buf.length * 2;
    while (size < this.n + k) size *= 2;
    const b = Buffer.allocUnsafe(size); this.buf.copy(b, 0, 0, this.n); this.buf = b;
  }
  byte(v: number): void { this.room(1); this.buf[this.n++] = v; }
  /** Unsigned varint for 0 <= v <= 2^53 (arithmetic, not bit ops: timestamps pass 2^31). */
  uv(v: number): void {
    this.room(8);
    while (v >= 128) { this.buf[this.n++] = (v % 128) + 128; v = Math.floor(v / 128); }
    this.buf[this.n++] = v;
  }
  /** Signed varint (zigzag). */
  sv(v: number): void { this.uv(v < 0 ? -2 * v - 1 : 2 * v); }
  str(s: string): void { const len = Buffer.byteLength(s); this.uv(len); this.room(len); this.buf.write(s, this.n, 'utf8'); this.n += len; }
  out(): Buffer { return this.buf.subarray(0, this.n); }
}

class R {
  i = 0;
  constructor(private readonly b: Buffer) {}
  byte(): number { return this.b[this.i++]; }
  uv(): number {
    const b = this.b;
    let c = b[this.i++];
    if (c < 128) return c;
    // Up to four bytes (< 2^28) on small integers, the rest in floating point (values reach 2^53).
    let v = c & 127, shift = 7;
    for (let k = 0; k < 3; k++) { c = b[this.i++]; v |= (c & 127) << shift; shift += 7; if (c < 128) return v; }
    let m = 268435456;
    do { c = b[this.i++]; v += (c & 127) * m; m *= 128; } while (c & 128);
    return v;
  }
  sv(): number { const z = this.uv(); return z % 2 ? -(z + 1) / 2 : z / 2; }
  str(): string { const len = this.uv(); const s = this.b.toString('utf8', this.i, this.i + len); this.i += len; return s; }
  /** A length-prefixed field left as bytes in place: [start, end). */
  span(): [number, number] { const len = this.uv(); const a = this.i; this.i += len; return [a, this.i]; }
}

// ---------- decimal text ----------
// A scaled integer n (value n / 10^k) printed as fixed-point decimal with trailing zeros dropped. The encoder stores a
// number column this way only when this text equals String(value) for every value in it (what JSON.stringify and the
// CSV writers print), so the decoder can write the digits straight into bytes without asking V8 to format doubles.
const ZEROS = ['', '0', '00', '000', '0000', '00000', '000000', '0000000', '00000000'];
export function decText(n: number, k: number): string {
  const neg = n < 0, a = neg ? -n : n;
  if (!k) return (neg ? '-' : '') + a;
  const ip = Math.floor(a / POW[k]), fp = a - ip * POW[k];
  if (!fp) return (neg ? '-' : '') + ip;
  let f = String(fp); f = ZEROS[k - f.length] + f;
  let e = f.length; while (f.charCodeAt(e - 1) === 48) e--;
  return (neg ? '-' : '') + ip + '.' + f.slice(0, e);
}

/** Growable output bytes for a block's text. */
class Out {
  buf: Buffer;
  n = 0;
  constructor(size: number) { this.buf = Buffer.allocUnsafe(Math.max(1024, size)); }
  room(k: number): void {
    if (this.n + k <= this.buf.length) return;
    let size = this.buf.length * 2;
    while (size < this.n + k) size *= 2;
    const b = Buffer.allocUnsafe(size); this.buf.copy(b, 0, 0, this.n); this.buf = b;
  }
  /** Short pieces are copied by hand: a native Buffer.copy per glue piece or value cost more than the copy itself. */
  bytes(src: Buffer, a = 0, b = src.length): void {
    const len = b - a;
    this.room(len);
    if (len > 32) { src.copy(this.buf, this.n, a, b); this.n += len; return; }
    const d = this.buf;
    let n = this.n;
    for (let i = a; i < b; i++) d[n++] = src[i];
    this.n = n;
  }
  /** Digits of a non-negative integer (< 2^53), `width` = minimum digits (zero padded). Split in two below 10^8 so the
   *  digit loop runs on small integers. */
  digits(a: number, width = 1): void {
    this.room(18 + width);
    if (a < 100_000_000) { this.small(a, width); return; }
    const hi = Math.floor(a / 100_000_000);
    this.small(hi, width - 8);
    this.small(a - hi * 100_000_000, 8);
  }
  private small(v: number, width: number): void {
    let len = v < 10 ? 1 : v < 100 ? 2 : v < 1000 ? 3 : v < 10000 ? 4 : v < 100000 ? 5 : v < 1000000 ? 6 : v < 10000000 ? 7 : 8;
    const d = this.buf;
    while (len < width) { d[this.n++] = 48; width--; }
    let pos = this.n + len - 1;
    v |= 0;
    do { const q = (v / 10) | 0; d[pos--] = 48 + v - q * 10; v = q; } while (v > 0);
    this.n += len;
  }
  /** decText(n, k) as bytes. */
  dec(n: number, k: number): void {
    this.room(1);
    if (n < 0) { this.buf[this.n++] = 45; n = -n; }
    if (!k) { this.digits(n); return; }
    const ip = Math.floor(n / POW[k]);
    let fp = n - ip * POW[k];
    this.digits(ip);
    if (!fp) return;
    let w = k; while (fp % 10 === 0) { fp /= 10; w--; }
    this.room(1); this.buf[this.n++] = 46;
    this.digits(fp, w);
  }
}

// ---------- columns ----------
type Ty = 'n' | 's' | 'j';
const typeOf = (v: unknown): Ty => (typeof v === 'number' && Number.isFinite(v) ? 'n' : typeof v === 'string' ? 's' : 'j');

/** Smallest decimal scale k with x == round(x*10^k)/10^k exactly, or -1. */
function scaleOf(x: number): number {
  for (let k = 0; k <= MAX_SCALE; k++) {
    const s = Math.round(x * POW[k]);
    if (Math.abs(s) > Number.MAX_SAFE_INTEGER) return -1;
    if (s / POW[k] === x) return k;
  }
  return -1;
}

function writeColumn(w: W, vals: unknown[], ty: Ty): void {
  if (ty === 'n') {
    let k = 0;
    for (const v of vals) { const s = scaleOf(v as number); if (s < 0) { k = -1; break; } if (s > k) k = s; }
    if (k >= 0) {
      const ints = vals.map((v) => Math.round((v as number) * POW[k]));
      if (ints.every((x, i) => Math.abs(x) <= Number.MAX_SAFE_INTEGER / 2 && x / POW[k] === vals[i] && decText(x, k) === String(vals[i]))) {
        // Delta when it is smaller in sum of magnitudes (a cheap stand-in for encoded size).
        let plain = 0, dsum = 0;
        for (let i = 0; i < ints.length; i++) { plain += Math.abs(ints[i]); dsum += Math.abs(ints[i] - (i ? ints[i - 1] : 0)); }
        const delta = dsum < plain;
        w.byte(0); w.uv(k); w.byte(delta ? 1 : 0);
        for (let i = 0; i < ints.length; i++) w.sv(delta ? ints[i] - (i ? ints[i - 1] : 0) : ints[i]);
        return;
      }
    }
    // Fall through: numbers kept as JSON text.
  }
  if (ty === 's') {
    const dict = new Map<string, number>();
    const idx = vals.map((v) => { const s = v as string; let i = dict.get(s); if (i === undefined) { i = dict.size; dict.set(s, i); } return i; });
    w.byte(1); w.uv(dict.size);
    for (const s of dict.keys()) w.str(s);
    for (const i of idx) w.uv(i);
    return;
  }
  w.byte(2);
  for (const v of vals) w.str(JSON.stringify(v));
}

/** A column read back in compact form (typed arrays, dictionary entries and text fields as bytes), written out as
 *  each line's bytes: numbers as fixed-point digits (see decText), strings JSON-quoted in object lines and bare in CSV
 *  rows, other values as their stored JSON. No objects or per-value strings are made, so reading runs at memcpy speed. */
type Col = { tag: 0; k: number; v: Float64Array } | { tag: 1; dict: Buffer[]; idx: Uint32Array } | { tag: 2; at: Uint32Array };

function readColumn(r: R, n: number, csv: boolean): Col {
  const tag = r.byte();
  if (tag === 0) {
    const k = r.uv(), delta = r.byte() === 1, v = new Float64Array(n);
    let prev = 0;
    for (let i = 0; i < n; i++) { const d = r.sv(); prev = delta ? prev + d : d; v[i] = prev; }
    return { tag, k, v };
  }
  if (tag === 1) {
    const dict: Buffer[] = [];
    for (let i = r.uv(); i > 0; i--) { const s = r.str(); dict.push(Buffer.from(csv ? s : JSON.stringify(s))); }
    const idx = new Uint32Array(n);
    for (let i = 0; i < n; i++) idx[i] = r.uv();
    return { tag, dict, idx };
  }
  if (tag === 2) {
    const at = new Uint32Array(2 * n);
    for (let i = 0; i < n; i++) { const [a, b] = r.span(); at[2 * i] = a; at[2 * i + 1] = b; }
    return { tag, at };
  }
  throw new Error(`mdc: bad column tag ${tag}`);
}

// ---------- blocks ----------
/** A CSV row's fields: numbers where the text is exactly how JS prints that number, else strings. */
function csvRow(line: string): unknown[] {
  return line.split(',').map((f) => { const x = f === '' ? NaN : Number(f); return Number.isFinite(x) && String(x) === f ? x : f; });
}

/** One block's payload (before zstd) from lines without their newlines. */
export function encodeBlock(lines: string[], endsWithNewline: boolean): Buffer {
  const shapes = new Map<string, number>(); // shape JSON -> id (1-based)
  const shapeTypes: Ty[][] = [];
  const rows: unknown[][][] = []; // per shape: per key column values
  const ids: number[] = new Array(lines.length);
  const raw: string[] = [];
  for (let li = 0; li < lines.length; li++) {
    const line = lines[li];
    let o: unknown;
    try { o = line[0] === '{' ? JSON.parse(line) : undefined; } catch { o = undefined; }
    let keys: string[] | null, vals: unknown[];
    if (o && typeof o === 'object' && !Array.isArray(o) && JSON.stringify(o) === line) { keys = Object.keys(o); vals = Object.values(o); }
    else if (line.length && !/["{\[\r]/.test(line)) { keys = null; vals = csvRow(line); }
    else { ids[li] = 0; raw.push(line); continue; }
    const types = vals.map(typeOf);
    const sig = JSON.stringify([keys, types]);
    let id = shapes.get(sig);
    if (id === undefined) { id = shapes.size + 1; shapes.set(sig, id); shapeTypes.push(types); rows.push(vals.map(() => [])); }
    ids[li] = id;
    const cols = rows[id - 1];
    for (let c = 0; c < vals.length; c++) cols[c].push(vals[c]);
  }
  const w = new W();
  w.uv(lines.length); w.byte(endsWithNewline ? 1 : 0);
  w.uv(shapes.size);
  for (const sig of shapes.keys()) w.str(sig);
  for (const id of ids) w.uv(id);
  for (const s of raw) w.str(s);
  for (let s = 0; s < rows.length; s++) for (let c = 0; c < rows[s].length; c++) writeColumn(w, rows[s][c], shapeTypes[s][c]);
  return Buffer.from(w.out());
}

/** One block payload back to its text: every line followed by a newline. */
export function decodeBlockText(payload: Buffer): { text: Buffer; lines: number; endsWithNewline: boolean } {
  const r = new R(payload);
  const n = r.uv(), endsWithNewline = r.byte() === 1;
  const sigs: [string[] | null, Ty[]][] = [];
  for (let i = r.uv(); i > 0; i--) sigs.push(JSON.parse(r.str()));
  const ids = new Uint32Array(n), count = new Array<number>(sigs.length + 1).fill(0);
  for (let i = 0; i < n; i++) { ids[i] = r.uv(); count[ids[i]]++; }
  const raw = new Uint32Array(2 * count[0]);
  for (let i = 0; i < count[0]; i++) { const [a, b] = r.span(); raw[2 * i] = a; raw[2 * i + 1] = b; }
  const cols: Col[][] = sigs.map(([keys, types], s) => types.map(() => readColumn(r, count[s + 1], !keys)));
  // Per shape, the bytes around the values: '{"t":' v ',"k":' v ... '}' (CSV: '' v ',' v ... ''), then the newline.
  const glue: Buffer[][] = sigs.map(([keys, types]) => (keys
    ? (keys.length ? [...keys.map((k, i) => (i ? ',' : '{') + JSON.stringify(k) + ':'), '}\n'] : ['{}\n'])
    : [...types.map((_, i) => (i ? ',' : '')), '\n']).map((g) => Buffer.from(g)));
  const at = new Array<number>(sigs.length + 1).fill(0);
  const out = new Out(payload.length * 4);
  for (let i = 0; i < n; i++) {
    const id = ids[i], j = at[id]++;
    if (id === 0) { out.bytes(payload, raw[2 * j], raw[2 * j + 1]); out.room(1); out.buf[out.n++] = 10; continue; }
    const c = cols[id - 1], g = glue[id - 1];
    for (let k = 0; k < c.length; k++) {
      out.bytes(g[k]);
      const col = c[k];
      if (col.tag === 0) out.dec(col.v[j], col.k);
      else if (col.tag === 1) out.bytes(col.dict[col.idx[j]]);
      else out.bytes(payload, col.at[2 * j], col.at[2 * j + 1]);
    }
    out.bytes(g[c.length]);
  }
  return { text: out.buf.subarray(0, out.n), lines: n, endsWithNewline };
}

/** Lines of one block payload, and whether the block ended with a newline. */
export function decodeBlock(payload: Buffer): { lines: string[]; endsWithNewline: boolean } {
  const { text, endsWithNewline } = decodeBlockText(payload);
  return { lines: textLines(text, isAscii(text)), endsWithNewline };
}

function zstd(buf: Buffer, o: MdcOpts): Buffer {
  needZstd();
  const C = zlib.constants as unknown as Record<string, number>;
  return (zlib as unknown as { zstdCompressSync: (b: Buffer, o: object) => Buffer }).zstdCompressSync(buf, {
    params: { [C.ZSTD_c_compressionLevel]: o.level ?? 19, [C.ZSTD_c_windowLog]: o.windowLog ?? 27 },
  });
}
function unzstd(buf: Buffer): Buffer {
  needZstd();
  const C = zlib.constants as unknown as Record<string, number>;
  return (zlib as unknown as { zstdDecompressSync: (b: Buffer, o: object) => Buffer }).zstdDecompressSync(buf, { params: { [C.ZSTD_d_windowLogMax]: 31 } });
}

/** True when the file starts with the .mdc magic. */
export function isMdc(file: string): boolean {
  const fd = fs.openSync(file, 'r');
  try { const b = Buffer.alloc(MDC_MAGIC.length); fs.readSync(fd, b, 0, b.length, 0); return b.equals(MDC_MAGIC); } finally { fs.closeSync(fd); }
}

/** Streams the lines of an .mdc file (without newlines), one block in memory at a time. */
/** One zstd frame to its block text; `ascii` says the text can be read as latin1 (the fast way to make JS strings). */
export function decodeFrameText(frame: Buffer): { text: Buffer; ascii: boolean } {
  const { text } = decodeBlockText(unzstd(frame));
  return { text, ascii: isAscii(text) };
}

/** A block's text to its lines (the text ends in a newline when it has any line). */
function textLines(text: Buffer, ascii: boolean): string[] {
  if (!text.length) return [];
  return text.toString(ascii ? 'latin1' : 'utf8', 0, text.length - 1).split('\n');
}

/** A block's text as batches of lines, about `piece` bytes each, cut at newlines: each batch's strings are made just
 *  before they are read and die young, instead of one 100 MB string per block that the collector keeps moving. */
function* textPieces(text: Buffer, ascii: boolean, piece = 256 * 1024): Generator<string[]> {
  const enc = ascii ? 'latin1' : 'utf8';
  for (let a = 0; a < text.length;) {
    let b = Math.min(text.length, a + piece);
    if (b < text.length) { const nl = text.indexOf(10, b); b = nl < 0 ? text.length : nl + 1; }
    yield text.toString(enc, a, b - 1).split('\n');
    a = b;
  }
}

/** The worker script for this build, or undefined (then blocks decode on this thread). */
function workerScript(): { path: string; workerData?: unknown } | undefined {
  const entry = process.argv[1] ?? '';
  if (entry.endsWith('.cjs')) { const p = path.join(path.dirname(entry), 'mdcWorker.cjs'); return fs.existsSync(p) ? { path: p } : undefined; }
  const dev = path.resolve('research', 'workerDev.mjs'), src = path.resolve('bot', 'marketdata', 'mdcWorker.ts');
  return fs.existsSync(dev) && fs.existsSync(src) ? { path: dev, workerData: { entry: pathToFileURL(src).href } } : undefined;
}

/** Decoding threads for one read: MDC_WORKERS (0 = none), else up to 3, one core always left to the reader. */
function workerCount(): number {
  const env = Number(process.env.MDC_WORKERS);
  if (Number.isFinite(env) && process.env.MDC_WORKERS !== '') return Math.max(0, Math.floor(env));
  return Math.max(0, Math.min(3, (os.availableParallelism?.() ?? os.cpus().length) - 1));
}

/** Decodes frames on worker threads, in order, at most `ahead` in flight. Falls back to this thread if a worker fails. */
class FramePool {
  private readonly workers: Worker[] = [];
  private readonly waiting = new Map<number, { resolve: (v: { text: Buffer; ascii: boolean }) => void; reject: (e: Error) => void }>();
  private next = 0;
  constructor(script: { path: string; workerData?: unknown }, n: number) {
    for (let i = 0; i < n; i++) {
      const w = new Worker(script.path, { workerData: script.workerData });
      w.on('message', (m: { id: number; text?: Uint8Array; ascii?: boolean; error?: string }) => {
        const p = this.waiting.get(m.id); if (!p) return;
        this.waiting.delete(m.id);
        if (m.error !== undefined) p.reject(new Error(m.error));
        else p.resolve({ text: Buffer.from(m.text!.buffer, m.text!.byteOffset, m.text!.byteLength), ascii: !!m.ascii });
      });
      w.on('error', (e) => { for (const p of this.waiting.values()) p.reject(e); this.waiting.clear(); });
      this.workers.push(w);
    }
  }
  decode(id: number, frame: Buffer): Promise<{ text: Buffer; ascii: boolean }> {
    return new Promise((resolve, reject) => {
      this.waiting.set(id, { resolve, reject });
      const w = this.workers[this.next++ % this.workers.length];
      const copy = new Uint8Array(frame.length); copy.set(frame);
      w.postMessage({ id, frame: copy }, [copy.buffer]);
    });
  }
  close(): void { for (const w of this.workers) void w.terminate(); }
}

/** Lines from batches of lines, through a lean iterator: one resolved promise per line instead of an async generator's
 *  full step, which was most of what reading a big day cost once the blocks decode on other threads. */
export function flattenBatches(batches: AsyncIterable<string[]>): AsyncIterable<string> {
  return {
    [Symbol.asyncIterator](): AsyncIterator<string> {
      const it = batches[Symbol.asyncIterator]();
      let cur: string[] = [], i = 0;
      const next = (): Promise<IteratorResult<string>> => {
        if (i < cur.length) return Promise.resolve({ value: cur[i++], done: false });
        return it.next().then((r) => { if (r.done) return { value: undefined, done: true }; cur = r.value; i = 0; return next(); });
      };
      return {
        next,
        return: async (): Promise<IteratorResult<string>> => { cur = []; await it.return?.(); return { value: undefined, done: true }; },
      };
    },
  };
}

/** Lines of an .mdc file (without newlines). */
export const mdcLines = (file: string): AsyncIterable<string> => flattenBatches(mdcBatches(file));

/** Streams an .mdc file one block of lines at a time. Big files decode their blocks on worker threads, a few blocks
 *  ahead of the reader, so reading costs about as much as handing out the lines; small ones decode here. */
export async function* mdcBatches(file: string): AsyncGenerator<string[]> {
  const fh = await fs.promises.open(file, 'r');
  let pool: FramePool | undefined;
  try {
    const head = Buffer.alloc(MDC_MAGIC.length);
    await fh.read(head, 0, head.length, 0);
    if (!head.equals(MDC_MAGIC)) throw new Error(`${file}: not an .mdc file`);
    let pos = MDC_MAGIC.length;
    const size = (await fh.stat()).size;
    const lenBuf = Buffer.alloc(4);
    const readFrame = async (): Promise<Buffer | undefined> => {
      const { bytesRead } = await fh.read(lenBuf, 0, 4, pos);
      if (bytesRead < 4) return undefined;
      const len = lenBuf.readUInt32LE(0);
      const frame = Buffer.allocUnsafe(len);
      const got = (await fh.read(frame, 0, len, pos + 4)).bytesRead;
      if (got < len) throw new Error(`${file}: block cut short at byte ${pos}`);
      pos += 4 + len;
      return frame;
    };
    const n = size > Number(process.env.MDC_WORKER_MIN_BYTES ?? 4 * 1048576) ? workerCount() : 0;
    const script = n > 0 ? workerScript() : undefined;
    if (script) { try { pool = new FramePool(script, n); } catch { pool = undefined; } }
    if (!pool) {
      for (let f = await readFrame(); f; f = await readFrame()) { const d = decodeFrameText(f); yield* textPieces(d.text, d.ascii); }
      return;
    }
    // Keep the workers busy: `ahead` blocks in flight while this thread hands out the lines of the oldest.
    // A worker that cannot start or fails (no TypeScript loader where it runs, out of memory) costs nothing but speed:
    // its block, and every block after it, decodes on this thread.
    const ahead = n + 1, queue: { frame: Buffer; p: Promise<{ text: Buffer; ascii: boolean }> | undefined }[] = [];
    let id = 0, done = false, broken = false;
    const fill = async () => {
      while (!done && queue.length < ahead) {
        const frame = await readFrame();
        if (!frame) { done = true; break; }
        const p = broken ? undefined : pool!.decode(id++, frame);
        p?.catch(() => undefined);
        queue.push({ frame, p });
      }
    };
    await fill();
    while (queue.length) {
      const q = queue.shift()!;
      let d: { text: Buffer; ascii: boolean };
      try { d = q.p ? await q.p : decodeFrameText(q.frame); } catch { broken = true; d = decodeFrameText(q.frame); }
      await fill();
      yield* textPieces(d.text, d.ascii);
    }
  } finally { pool?.close(); await fh.close(); }
}

/** Encodes an iterable of lines (no newlines) into `dest` (.mdc), checking every block decodes to the same lines.
 *  `endsWithNewline` is whether the source's last line ended in a newline (the bot's files always do). */
export async function encodeLines(lines: AsyncIterable<string> | Iterable<string>, dest: string, o: MdcOpts & { endsWithNewline?: boolean } = {}): Promise<{ lines: number; bytes: number }> {
  needZstd();
  const tmp = `${dest}.tmp`;
  const fd = fs.openSync(tmp, 'w', 0o600);
  let total = 0;
  const per = o.blockLines ?? BLOCK_LINES;
  let block: string[] = [];
  const flush = (last: boolean): void => {
    if (!block.length) return;
    const payload = encodeBlock(block, last ? o.endsWithNewline ?? true : true);
    const back = decodeBlock(payload).lines;
    if (back.length !== block.length || back.some((l, i) => l !== block[i])) throw new Error('mdc: round trip failed (refusing to write a lossy file)');
    const frame = zstd(payload, o);
    const len = Buffer.alloc(4); len.writeUInt32LE(frame.length, 0);
    fs.writeSync(fd, len); fs.writeSync(fd, frame);
    total += block.length;
    block = [];
  };
  try {
    fs.writeSync(fd, MDC_MAGIC);
    for await (const l of lines as AsyncIterable<string>) { block.push(l); if (block.length >= per) flush(false); }
    flush(true);
  } catch (e) { fs.closeSync(fd); fs.rmSync(tmp, { force: true }); throw e; }
  fs.closeSync(fd);
  fs.renameSync(tmp, dest);
  return { lines: total, bytes: fs.statSync(dest).size };
}
