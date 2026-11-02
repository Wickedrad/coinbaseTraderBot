// Compact recordings tool (bot/marketdata/compactRecording.ts).
//
//   npx tsx scripts/mdc.ts encode <md-DAY.jsonl[.gz]> [out.mdc]      lossless compact copy (checks the round trip)
//   npx tsx scripts/mdc.ts decode <md-DAY.mdc> [out.jsonl.gz]         back to the bot's own gzip form
//   npx tsx scripts/mdc.ts cat <file>                                 the day's lines as plain JSONL on stdout
//   npx tsx scripts/mdc.ts verify <md-DAY.mdc> <md-DAY.jsonl[.gz]>    same lines, byte for byte?
//   npx tsx scripts/mdc.ts expand <dir>                               decode every .mdc in <dir> to .jsonl.gz beside it
//   npx tsx scripts/mdc.ts bench <md-DAY.jsonl.gz> [level...]         sizes, encode and read times (prints aggregates only)
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

/** Does the source end with a newline? (Only the plain form can be checked cheaply; the bot's files always do.) */
function endsWithNewline(file: string): boolean {
  if (file.endsWith('.jsonl')) {
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

async function encode(src: string, dst = outName(src, '.mdc'), o = opts()) {
  const t0 = Date.now();
  const r = await encodeLines(recordingLines(src), dst, { ...o, endsWithNewline: endsWithNewline(src) });
  return { ...r, ms: Date.now() - t0, dst };
}

/** md-DAY.mdc -> md-DAY.jsonl.gz; any other x.mdc -> x.gz (x.csv.mdc -> x.csv.gz). */
const decodedName = (f: string) => (/(^|\/)md-\d{4}-\d{2}-\d{2}\.mdc$/.test(f) ? outName(f, '.jsonl.gz') : f.replace(/\.mdc$/, '') + '.gz');

async function decode(src: string, dst = decodedName(src)) {
  async function* text() { for await (const l of recordingLines(src)) yield l + '\n'; }
  const tmp = `${dst}.tmp`;
  await pipeline(Readable.from(text()), zlib.createGzip({ level: 6 }), fs.createWriteStream(tmp, { mode: 0o600 }));
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
    for (const f of fs.readdirSync(a).filter((f) => /^md-\d{4}-\d{2}-\d{2}\.mdc$/.test(f)).sort()) {
      const dst = path.join(a, outName(f, '.jsonl.gz'));
      if (!fs.existsSync(dst)) console.log(await decode(path.join(a, f), dst));
    }
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
    console.error('usage: mdc.ts encode|decode|cat|verify|expand|bench ... (see the header)');
    process.exitCode = 2;
  }
}

main().catch((e) => { console.error(String(e?.stack ?? e)); process.exit(1); });
