/** Reads the paper bot's audit day files (from the Drive archive, inside a private job) and writes its OPENING
 *  fills on the coin Price Prediction series to a file that never leaves the runner. Prints counts only. */
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { createGunzip } from 'node:zlib';

export interface OpenFill { ticker: string; side: 'yes' | 'no'; ts: number; price: number; count: number; fee: number }
const SERIES = /^KX(BTC|ETH|SOL|XRP)(15M|D)-/;
const r4 = (x: number) => Math.round(x * 10000) / 10000;

/** The opening part of one audited fill, if any. `position` is the signed YES position AFTER the fill. */
export function openingPart(d: { fill?: { ticker?: string; side?: string; count?: number; price?: number; ts?: number }; fee?: number; position?: number }): OpenFill | undefined {
  const f = d.fill;
  if (!f || typeof f.ticker !== 'string' || !SERIES.test(f.ticker) || !(f.count! > 0) || !(f.price! > 0 && f.price! < 1) || !Number.isFinite(f.ts) || !Number.isFinite(d.position)) return undefined;
  const signed = f.side === 'bid' ? f.count! : f.side === 'ask' ? -f.count! : NaN;
  if (!Number.isFinite(signed)) return undefined;
  const after = d.position!, before = after - signed;
  // Same direction (or flat before): the whole fill opens. Through zero: only the part past zero opens.
  const opened = Math.abs(before) < 1e-9 || Math.sign(before) === Math.sign(signed) ? f.count! : Math.max(0, f.count! - Math.abs(before));
  if (!(opened > 1e-9)) return undefined;
  return { ticker: f.ticker, side: signed > 0 ? 'yes' : 'no', ts: f.ts!, price: r4(signed > 0 ? f.price! : 1 - f.price!), count: Math.round(opened * 100) / 100, fee: r4((d.fee ?? 0) * opened / f.count!) };
}

export async function readOpeningFills(dir: string, from: number, to: number): Promise<{ fills: OpenFill[]; files: number; fillLines: number }> {
  const fills: OpenFill[] = []; let files = 0, fillLines = 0;
  for (const name of fs.readdirSync(dir).filter((n) => /^audit-\d{4}-\d{2}-\d{2}.*\.jsonl(\.gz)?$/.test(n)).sort()) {
    files++;
    const raw = fs.createReadStream(path.join(dir, name)), input = name.endsWith('.gz') ? raw.pipe(createGunzip()) : raw;
    for await (const line of readline.createInterface({ input, crlfDelay: Infinity })) {
      if (!line.includes('"kind":"fill"')) continue;
      let rec: any; try { rec = JSON.parse(line); } catch { continue; }
      if (rec.kind !== 'fill' || !rec.data) continue;
      fillLines++;
      const o = openingPart(rec.data);
      if (o && o.ts >= from && o.ts < to) fills.push(o);
    }
  }
  return { fills, files, fillLines };
}

const arg = (name: string, fallback = '') => { const i = process.argv.indexOf(`--${name}`); return i < 0 ? fallback : process.argv[i + 1]; };
if (process.argv[1] && /(^|[/\\])botFills\.(ts|js)$/.test(process.argv[1])) {
  void readOpeningFills(arg('audit'), Date.parse(arg('from', '1970-01-01T00:00:00Z')), Date.parse(arg('to', '2100-01-01T00:00:00Z'))).then((r) => {
    fs.writeFileSync(arg('out'), r.fills.map((f) => JSON.stringify(f)).join('\n') + (r.fills.length ? '\n' : ''));
    const k = (f: OpenFill) => /15M-/.test(f.ticker) ? '15m' : 'hourly';
    console.log(JSON.stringify({ auditFiles: r.files, fillLines: r.fillLines, openingFills: r.fills.length, m15: r.fills.filter((f) => k(f) === '15m').length, hourly: r.fills.filter((f) => k(f) === 'hourly').length }));
  }).catch((e) => { console.error(e instanceof Error ? e.message : e); process.exitCode = 1; });
}
