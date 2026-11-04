// Compact recordings tool (bot/marketdata/compactRecording.ts).
//
//   npx tsx scripts/mdc.ts encode <file> [out.mdc]          lossless compact copy (checks the round trip)
//   npx tsx scripts/mdc.ts decode <file.mdc> [out]          back to the original form (see names below)
//   npx tsx scripts/mdc.ts cat <file>                       the lines as plain text on stdout
//   npx tsx scripts/mdc.ts verify <a> <b>                   same lines, byte for byte? (any two forms)
//   npx tsx scripts/mdc.ts expand <dir>                     decode every .mdc under <dir> (recursive) beside itself
//   npx tsx scripts/mdc.ts encode-tree <src> <dst>          every .jsonl/.csv(.gz) under <src> -> <dst>, same tree,
//                                                           each verified against its source; existing ones skipped
//   npx tsx scripts/mdc.ts bench <file> [level...]          sizes, encode and read times (prints aggregates only)
//
// Names: a recorded day md-DAY.jsonl(.gz) <-> md-DAY.mdc (decoded to the bot's md-DAY.jsonl.gz); any other file keeps
// its own name without .gz plus .mdc (kalshi/KXBTC/2026-01-05.jsonl <-> 2026-01-05.jsonl.mdc, binance/BTC/1m.csv(.gz)
// <-> 1m.csv.mdc), decoded back to the plain file the history tools read.
//
// Env MDC_LEVEL (default 19) and MDC_WINDOW_LOG (default 27) tune zstd for encode.

import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import { pipeline } from 'stream/promises';
import { Readable } from 'stream';
import { encodeLines } from '../bot/marketdata/compactRecording';
import { recordingLines } from '../bot/marketdata/recordingFiles';

const opts = () => ({ level: Number(process.env.MDC_LEVEL ?? 19), windowLog: Number(process.env.MDC_WINDOW_LOG ?? 27) });
const mb = (b: number) => (b / 1048576).toFixed(1);
const outName = (f: string, ext: string) => f.replace(/\.(?:jsonl(?:\.gz)?|mdc)$/, '') + ext;
const DAY = /(^|[\\/])md-\d{4}-\d{2}-\d{2}\.(?:jsonl(?:\.gz)?|mdc)$/;
/** The compact name of a source file. */
export const compactName = (f: string) => (DAY.test(f) ? outName(f, '.mdc') : f.replace(/\.gz$/, '') + '.mdc');
/** The name an .mdc decodes to: a recorded day as the bot's gzip, anything else as its plain file. */
export const decodedName = (f: string) => (DAY.test(f) ? outName(f, '.jsonl.gz') : f.replace(/\.mdc$/, ''));
const SOURCE = /\.(?:jsonl|csv)(?:\.gz)?$/;
function walk(dir: string, out: string[] = [], rel = ''): string[] {
  for (const e of fs.readdirSync(path.join(dir, rel), { withFileTypes: true })) {
    const r = path.join(rel, e.name);
    if (e.isDirectory()) walk(dir, out, r); else out.push(r);
  }
  return out;
}

/** Does the source end with a newline? (Only the plain form can be checked cheaply; the bot's files always do.) */
function endsWithNewline(file: string): boolean {
  if (!file.endsWith('.gz')) {
    const size = fs.statSync(file).size;
    if (!size) return true;
    const fd = fs.openSync(file, 'r'); const b = Buffer.alloc(1); fs.readSync(fd, b, 0, 1, size - 1); fs.closeSync(fd);
    return b[0] === 10;
  }
  return true;
}

async function digest(file: string): Promise<{ lines: number; sha: string; bytes: number; ms: number }> {
  const h = crypto.createHash('sha256');
  let lines = 0, bytes = 0;
  const t0 = Date.now();
  for await (const l of recordingLines(file)) { h.update(l); h.update('\n'); lines++; bytes += Buffer.byteLength(l) + 1; }
  return { lines, sha: h.digest('hex'), bytes, ms: Date.now() - t0 };
}

async function encode(src: string, dst = compactName(src), o = opts()) {
  const t0 = Date.now();
  const r = await encodeLines(recordingLines(src), dst, { ...o, endsWithNewline: endsWithNewline(src) });
  return { ...r, ms: Date.now() - t0, dst };
}

/** md-DAY.mdc -> md-DAY.jsonl.gz; any other x.mdc -> x.gz (x.csv.mdc -> x.csv.gz). */
async function decode(src: string, dst = decodedName(src)) {
  async function* text() { for await (const l of recordingLines(src)) yield l + '\n'; }
  const tmp = `${dst}.tmp`;
  const sink = fs.createWriteStream(tmp, { mode: 0o600 });
  await (dst.endsWith('.gz') ? pipeline(Readable.from(text()), zlib.createGzip({ level: 6 }), sink) : pipeline(Readable.from(text()), sink));
  fs.renameSync(tmp, dst);
  return dst;
}

async function main() {
  const [cmd, a, b, ...rest] = process.argv.slice(2);
  if (cmd === 'encode' && a) {
    const r = await encode(a, b);
    console.log(`${path.basename(a)} -> ${path.basename(r.dst)}: ${r.lines} lines, ${mb(fs.statSync(a).size)} MB -> ${mb(r.bytes)} MB in ${(r.ms / 1000).toFixed(1)} s`);
  } else if (cmd === 'decode' && a) {
    console.log(await decode(a, b));
  } else if (cmd === 'cat' && a) {
    for await (const l of recordingLines(a)) if (!process.stdout.write(l + '\n')) await new Promise((r) => process.stdout.once('drain', r));
  } else if (cmd === 'verify' && a && b) {
    const [x, y] = await Promise.all([digest(a), digest(b)]);
    const same = x.sha === y.sha && x.lines === y.lines;
    console.log(same ? `identical: ${x.lines} lines, sha256 ${x.sha.slice(0, 16)}` : `DIFFERENT: ${x.lines} vs ${y.lines} lines`);
    process.exitCode = same ? 0 : 1;
  } else if (cmd === 'expand' && a) {
    for (const f of walk(a).filter((f) => f.endsWith('.mdc')).sort()) {
      const dst = path.join(a, decodedName(f));
      if (!fs.existsSync(dst)) console.log(await decode(path.join(a, f), dst));
    }
  } else if (cmd === 'encode-tree' && a && b) {
    let n = 0, skipped = 0, inBytes = 0, outBytes = 0;
    const t0 = Date.now();
    for (const f of walk(a).filter((f) => SOURCE.test(f)).sort()) {
      const dst = path.join(b, compactName(f));
      if (fs.existsSync(dst)) { skipped++; continue; }
      fs.mkdirSync(path.dirname(dst), { recursive: true });
      const src = path.join(a, f);
      await encode(src, dst);
      const [x, y] = await Promise.all([digest(src), digest(dst)]);
      if (x.sha !== y.sha || x.lines !== y.lines) { fs.rmSync(dst); throw new Error(`${f}: decoded copy differs from the source (removed)`); }
      n++; inBytes += fs.statSync(src).size; outBytes += fs.statSync(dst).size;
    }
    console.log(`encode-tree: ${n} files verified byte-identical (${skipped} already there), ${mb(inBytes)} MB -> ${mb(outBytes)} MB in ${((Date.now() - t0) / 1000).toFixed(0)} s`);
  } else if (cmd === 'bench' && a) {
    const levels = [b, ...rest].filter(Boolean).map(Number);
    const gz = await digest(a);
    console.log(`source ${path.basename(a)}: ${mb(fs.statSync(a).size)} MB on disk, ${mb(gz.bytes)} MB plain, ${gz.lines} lines, read ${(gz.ms / 1000).toFixed(1)} s`);
    const kinds = new Map<string, number>();
    let n = 0;
    for await (const l of recordingLines(a)) { if (n++ > 2_000_000) break; const k = /"k":"([a-z_]+)"/.exec(l)?.[1] ?? '?'; kinds.set(k, (kinds.get(k) ?? 0) + Buffer.byteLength(l)); }
    console.log(`kinds (share of plain bytes, first 2M lines): ${[...kinds].sort((x, y) => y[1] - x[1]).slice(0, 10).map(([k, v]) => `${k} ${((100 * v) / [...kinds.values()].reduce((s, x) => s + x, 0)).toFixed(0)}%`).join(', ')}`);
    for (const level of levels.length ? levels : [19]) {
      const dst = path.join(process.env.RUNNER_TEMP ?? path.dirname(a), `bench-${level}.mdc`);
      const e = await encode(a, dst, { ...opts(), level });
      const d = await digest(dst);
      console.log(`mdc level ${level}: ${mb(e.bytes)} MB (${(fs.statSync(a).size / e.bytes).toFixed(1)}x smaller than the gzip, ${(gz.bytes / e.bytes).toFixed(0)}x than plain), encode ${(e.ms / 1000).toFixed(0)} s, read ${(d.ms / 1000).toFixed(1)} s, ${d.sha === gz.sha && d.lines === gz.lines ? 'byte-identical' : 'MISMATCH'}`);
      fs.rmSync(dst);
    }
  } else {
    console.error('usage: mdc.ts encode|decode|cat|verify|expand|encode-tree|bench ... (see the header)');
    process.exitCode = 2;
  }
}

main().catch((e) => { console.error(String(e?.stack ?? e)); process.exit(1); });
