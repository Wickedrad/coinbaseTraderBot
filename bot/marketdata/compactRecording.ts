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
import zlib from 'zlib';

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
    let v = 0, m = 1, c: number;
    do { c = this.b[this.i++]; v += (c & 127) * m; m *= 128; } while (c & 128);
    return v;
  }
  sv(): number { const z = this.uv(); return z % 2 ? -(z + 1) / 2 : z / 2; }
  str(): string { const len = this.uv(); const s = this.b.toString('utf8', this.i, this.i + len); this.i += len; return s; }
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
      if (ints.every((x, i) => Math.abs(x) <= Number.MAX_SAFE_INTEGER / 2 && x / POW[k] === vals[i])) {
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

function readColumn(r: R, n: number): unknown[] {
  const tag = r.byte();
  const out = new Array<unknown>(n);
  if (tag === 0) {
    const k = r.uv(), delta = r.byte() === 1, p = POW[k];
    let prev = 0;
    for (let i = 0; i < n; i++) { const d = r.sv(); const x = delta ? prev + d : d; prev = x; out[i] = x / p; }
  } else if (tag === 1) {
    const dict: string[] = [];
    for (let i = r.uv(); i > 0; i--) dict.push(r.str());
    for (let i = 0; i < n; i++) out[i] = dict[r.uv()];
  } else if (tag === 2) {
    for (let i = 0; i < n; i++) out[i] = JSON.parse(r.str());
  } else throw new Error(`mdc: bad column tag ${tag}`);
  return out;
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

/** Lines of one block payload, and whether the block ended with a newline. */
export function decodeBlock(payload: Buffer): { lines: string[]; endsWithNewline: boolean } {
  const r = new R(payload);
  const n = r.uv(), endsWithNewline = r.byte() === 1;
  const sigs: [string[] | null, Ty[]][] = [];
  for (let i = r.uv(); i > 0; i--) sigs.push(JSON.parse(r.str()));
  const ids = new Array<number>(n), count = new Array<number>(sigs.length + 1).fill(0);
  for (let i = 0; i < n; i++) { ids[i] = r.uv(); count[ids[i]]++; }
  const raw: string[] = [];
  for (let i = 0; i < count[0]; i++) raw.push(r.str());
  const cols: unknown[][][] = sigs.map(([, types], s) => types.map(() => readColumn(r, count[s + 1])));
  const at = new Array<number>(sigs.length + 1).fill(0);
  const lines = new Array<string>(n);
  for (let i = 0; i < n; i++) {
    const id = ids[i], j = at[id]++;
    if (id === 0) { lines[i] = raw[j]; continue; }
    const keys = sigs[id - 1][0], c = cols[id - 1];
    if (!keys) { const f = new Array<unknown>(c.length); for (let k = 0; k < c.length; k++) f[k] = c[k][j]; lines[i] = f.join(','); continue; }
    const o: Record<string, unknown> = {};
    for (let k = 0; k < keys.length; k++) o[keys[k]] = c[k][j];
    lines[i] = JSON.stringify(o);
  }
  return { lines, endsWithNewline };
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
export async function* mdcLines(file: string): AsyncGenerator<string> {
  const fh = await fs.promises.open(file, 'r');
  try {
    const head = Buffer.alloc(MDC_MAGIC.length);
    await fh.read(head, 0, head.length, 0);
    if (!head.equals(MDC_MAGIC)) throw new Error(`${file}: not an .mdc file`);
    let pos = MDC_MAGIC.length;
    const lenBuf = Buffer.alloc(4);
    for (;;) {
      const { bytesRead } = await fh.read(lenBuf, 0, 4, pos);
      if (bytesRead < 4) return;
      const len = lenBuf.readUInt32LE(0);
      const frame = Buffer.allocUnsafe(len);
      const got = (await fh.read(frame, 0, len, pos + 4)).bytesRead;
      if (got < len) throw new Error(`${file}: block cut short at byte ${pos}`);
      pos += 4 + len;
      const { lines } = decodeBlock(unzstd(frame));
      for (const l of lines) yield l;
    }
  } finally { await fh.close(); }
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
