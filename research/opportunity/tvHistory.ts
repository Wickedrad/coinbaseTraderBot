/** Explicit tvdatafeed acquisition for the offline atlas. Never splices providers/venues. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { readSeries, seriesPath, upsertSeries, type HistTf } from '../../bot/marketdata/historyStore';
import type { MinuteCandle } from './atlas';

export const TV_ATLAS_SCHEMA = 'atlas-tvdatafeed-v1';
const MIN = 60_000, DAY = 86_400_000;
export interface TvRequest { id: string; asset: string; tf: '1m' | '1d'; exchange: string; symbol: string; source: string }
export interface TvPlan { bars: number; series: TvRequest[] }
export interface TvPayload { schema: string; provider: string; clientVersion: string; clientSource: string | null;
  series: Array<{ id: string; rows: Array<Array<number | null>>; error: string | null }> }
export interface Coverage { from: string; through: string; expectedBars: number; presentBars: number; missingBars: number;
  gaps: Array<{ from: string; through: string; bars: number }>; gapCount: number; firstStored: string | null; lastStoredClose: string | null; ready: boolean }
export interface TvAcquireOptions {
  out: string; assets: string[]; exchange?: string; quote?: string; bars?: number;
  now?: number; from?: number; through?: number; python?: string;
}
export interface TvAcquisitionReport { schema: string; provider: string; acquiredAt: string; clientVersion: string;
  clientSource: string | null; rawFile: string; rawSha256: string; plan: TvPlan; ready: boolean;
  series: Array<{ request: TvRequest; fetchedBars: number; formingBarsExcluded: number; unknownVolumeBars: number;
    coverage: Coverage; file: string; error: string | null }> }

/** Reject untraceable or modified input rather than treating a folder name as provenance. */
export async function verifyTvSeries(file: string, expected: Pick<TvRequest, 'asset' | 'source' | 'tf'>): Promise<{ sha256: string; receipt: string }> {
  const proof = JSON.parse(fs.readFileSync(`${file}.provenance.json`, 'utf8'));
  const r = proof.request as TvRequest | undefined;
  const identity = r && r.asset === expected.asset && r.source === expected.source && r.tf === expected.tf &&
    (r.tf === '1d' ? r.exchange === 'CRYPTOCAP' && r.symbol === expected.asset && r.source === 'tradingview'
      : r.source === `tvdatafeed-${r.exchange.toLowerCase()}` && ['USD', 'USDT', 'USDC'].some((q) => r.symbol === `${r.asset}${q}`));
  if (proof.provider !== 'tvdatafeed' || !identity || typeof proof.lastReceipt !== 'string') throw new Error('unverified tvdatafeed input identity');
  const hash = crypto.createHash('sha256');
  for await (const chunk of fs.createReadStream(file)) hash.update(chunk);
  const digest = hash.digest('hex');
  if (digest !== proof.sha256) throw new Error('tvdatafeed input content hash mismatch');
  return { sha256: digest, receipt: proof.lastReceipt };
}

export function tvAtlasPlan(assets: string[], exchange = 'COINBASE', quote = 'USD', bars = 5000): TvPlan {
  if (!assets.length || assets.length > 20 || new Set(assets).size !== assets.length || assets.some((a) => !/^[A-Z0-9]+$/.test(a))) throw new Error('supply 1..20 unique uppercase asset symbols');
  if (!/^[A-Z0-9_]+$/.test(exchange) || !/^USD(T|C)?$/.test(quote)) throw new Error('explicit venue and USD-like quote required');
  if (!Number.isInteger(bars) || bars < 1 || bars > 5000) throw new Error('tvdatafeed bars must be 1..5000; this is not historical pagination');
  return { bars, series: [
    ...assets.map((asset): TvRequest => ({ id: `${asset}:1m`, asset, tf: '1m', exchange, symbol: `${asset}${quote}`,
      source: `tvdatafeed-${exchange.toLowerCase()}` })),
    ...['BTC.D', 'USDT.D'].map((asset): TvRequest => ({ id: `${asset}:1d`, asset, tf: '1d', exchange: 'CRYPTOCAP', symbol: asset, source: 'tradingview' })),
  ] };
}

/** Coverage is measured on exact expected opens; no interpolation or synthetic candles. */
export function tvCoverage(candles: MinuteCandle[], tf: '1m' | '1d', from: number, through: number): Coverage {
  const ms = tf === '1m' ? MIN : DAY;
  if (![from, through].every(Number.isFinite) || from < 0 || from % ms || through % ms || through <= from) throw new Error('coverage window must be positive, aligned and increasing');
  const gaps: Coverage['gaps'] = [];
  let next = from, present = 0, gapCount = 0, missing = 0;
  const gap = (end: number) => {
    if (end <= next) return;
    const bars = (end - next) / ms; missing += bars; gapCount++;
    if (gaps.length < 10) gaps.push({ from: new Date(next).toISOString(), through: new Date(end).toISOString(), bars });
  };
  for (let i = 0; i < candles.length; i++) {
    const b = candles[i];
    if (!Number.isFinite(b.ts) || b.ts % ms || (i > 0 && b.ts <= candles[i - 1].ts)) throw new Error('coverage input must be aligned and strictly increasing');
    if (b.ts < from || b.ts >= through) continue;
    gap(b.ts); present++; next = b.ts + ms;
  }
  gap(through);
  return { from: new Date(from).toISOString(), through: new Date(through).toISOString(),
    expectedBars: (through - from) / ms, presentBars: present, missingBars: missing, gaps, gapCount,
    firstStored: candles.length ? new Date(candles[0].ts).toISOString() : null,
    lastStoredClose: candles.length ? new Date(candles.at(-1)!.ts + ms).toISOString() : null,
    ready: missing === 0 };
}

export function closedTvRows(rows: Array<Array<number | null>>, request: TvRequest, now: number): {
  candles: MinuteCandle[]; formingBarsExcluded: number; unknownVolumeBars: number;
} {
  const ms = request.tf === '1m' ? MIN : DAY;
  const candles: MinuteCandle[] = [];
  let last = -Infinity, forming = 0, unknownVolume = 0;
  for (const row of rows) {
    const [ts, o, h, l, c, v] = row;
    if (row.length !== 6 || ![ts, o, h, l, c].every((x) => typeof x === 'number' && Number.isFinite(x)) ||
      ts! < 0 || ts! % ms || ts! <= last || l! <= 0 || h! < Math.max(o!, c!) || l! > Math.min(o!, c!)) throw new Error('invalid, unordered or misaligned tvdatafeed OHLC rows');
    last = ts!;
    if (ts! + ms > now) { forming++; continue; }
    if (v === null && request.tf === '1d') unknownVolume++;
    else if (typeof v !== 'number' || !Number.isFinite(v) || v < 0) throw new Error('invalid tvdatafeed spot volume');
    candles.push({ ts: ts!, o: o!, h: h!, l: l!, c: c!, v: v ?? 0 });
  }
  return { candles, formingBarsExcluded: forming, unknownVolumeBars: unknownVolume };
}

export type TvAcquireRunner = (plan: TvPlan, python: string) => Promise<TvPayload>;
export const runAtlasTv: TvAcquireRunner = (plan, python) => new Promise((resolve, reject) => {
  const script = fileURLToPath(new URL('./tvFetch.py', import.meta.url));
  const child = spawn(python, [script], { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true });
  const chunks: Buffer[] = []; let size = 0, stderr = '';
  const timer = setTimeout(() => { child.kill('SIGTERM'); reject(new Error('tvdatafeed acquisition timed out')); }, 120_000);
  child.stdout.on('data', (b: Buffer) => {
    size += b.length;
    if (size > 32 * 1024 * 1024) { child.kill('SIGTERM'); reject(new Error('tvdatafeed response exceeded 32 MiB')); }
    else chunks.push(b);
  });
  child.stderr.on('data', (b: Buffer) => { stderr = (stderr + b.toString()).slice(-2000); });
  child.on('error', (e) => { clearTimeout(timer); reject(e); });
  child.stdin.on('error', () => { /* A failed child may close stdin before consuming the plan. */ });
  child.on('close', (code) => {
    clearTimeout(timer);
    if (code !== 0) { reject(new Error(`tvdatafeed runner failed (${code}): ${stderr}`)); return; }
    try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); } catch { reject(new Error('invalid tvdatafeed response JSON')); }
  });
  child.stdin.end(JSON.stringify(plan));
});

const sha = (s: string | Buffer): string => crypto.createHash('sha256').update(s).digest('hex');
function saveJson(file: string, data: unknown): void {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(temp, JSON.stringify(data, null, 2) + '\n', { flag: 'wx' }); fs.renameSync(temp, file);
}

export async function acquireAtlasTv(o: TvAcquireOptions, run: TvAcquireRunner = runAtlasTv): Promise<TvAcquisitionReport> {
  const now = o.now ?? Date.now();
  const plan = tvAtlasPlan(o.assets, o.exchange, o.quote, o.bars);
  const through = o.through ?? Math.floor(now / MIN) * MIN, from = o.from ?? through - Math.max(1, plan.bars - 1) * MIN;
  tvCoverage([], '1m', from, through); // validate the requested bounds before network/disk work
  if (through > now) throw new Error('requested window includes future candles');
  if (from < 2 * DAY) throw new Error('coverage start must allow two preceding daily bars');
  const payload = await run(plan, o.python ?? process.env.TV_PYTHON ?? 'python3');
  if (payload.schema !== TV_ATLAS_SCHEMA || payload.provider !== 'tvdatafeed' || !payload.clientVersion || !Array.isArray(payload.series) ||
    payload.series.length !== plan.series.length || new Set(payload.series.map((s) => s.id)).size !== plan.series.length ||
    payload.series.some((s) => !plan.series.some((p) => p.id === s.id))) throw new Error('tvdatafeed response identities do not match the requested plan');
  const receipt = { acquiredAt: new Date(now).toISOString(), requestedWindow: { from, through }, plan, payload };
  const digest = sha(JSON.stringify(receipt, null, 2) + '\n');
  const rawFile = path.resolve(o.out, 'tvdatafeed-receipts', `${now}-${digest.slice(0, 16)}.json`);
  saveJson(rawFile, receipt);
  const report: TvAcquisitionReport = { schema: TV_ATLAS_SCHEMA, provider: 'tvdatafeed', acquiredAt: new Date(now).toISOString(),
    clientVersion: payload.clientVersion, clientSource: payload.clientSource, rawFile, rawSha256: digest, plan, ready: false, series: [] };
  for (const request of plan.series) {
    const result = payload.series.find((r) => r.id === request.id)!;
    const file = seriesPath(o.out, request.source, request.asset, request.tf);
    const sidecar = `${file}.provenance.json`;
    let candles: MinuteCandle[] = [], formingBarsExcluded = 0, unknownVolumeBars = 0, error: string | null = null;
    try {
      if (fs.existsSync(file)) {
        if (!fs.existsSync(sidecar)) throw new Error('existing series lacks tvdatafeed provenance; use a separate history directory');
        const old = JSON.parse(fs.readFileSync(sidecar, 'utf8'));
        if (old.provider !== 'tvdatafeed' || JSON.stringify(old.request) !== JSON.stringify(request) || old.sha256 !== sha(fs.readFileSync(file))) throw new Error('existing series provider, venue, symbol or content provenance mismatch');
        candles = closedTvRows(readSeries(file).map((b) => [b.ts, b.o, b.h, b.l, b.c, b.v]), request, now).candles;
      }
      if (result.error) throw new Error(result.error);
      if (!Array.isArray(result.rows)) throw new Error('invalid tvdatafeed rows');
      const parsed = closedTvRows(result.rows, request, now);
      formingBarsExcluded = parsed.formingBarsExcluded; unknownVolumeBars = parsed.unknownVolumeBars;
      if (!parsed.candles.length) throw new Error('no completed tvdatafeed candles returned');
      upsertSeries(o.out, request.source, request.asset, request.tf as HistTf, parsed.candles);
      candles = readSeries(file);
      saveJson(sidecar, { provider: 'tvdatafeed', request, sha256: sha(fs.readFileSync(file)), lastReceipt: rawFile,
        clientVersion: payload.clientVersion, clientSource: payload.clientSource, acquiredAt: report.acquiredAt });
    } catch (e) { error = String(e); }
    // A change at the first minute of the requested span needs TWO completed daily closes.
    const start = request.tf === '1m' ? from : Math.floor(from / DAY) * DAY - 2 * DAY;
    const end = request.tf === '1m' ? through : Math.floor(through / DAY) * DAY;
    report.series.push({ request, file, fetchedBars: result.rows?.length ?? 0, formingBarsExcluded, unknownVolumeBars,
      coverage: tvCoverage(candles, request.tf, start, end), error });
  }
  report.ready = report.series.every((s) => !s.error && s.coverage.ready);
  saveJson(rawFile.replace(/\.json$/, '.coverage.json'), report);
  saveJson(path.resolve(o.out, 'tvdatafeed-coverage.json'), report);
  return report;
}

async function main(): Promise<void> {
  const arg = (name: string, fallback: string) => { const i = process.argv.indexOf(`--${name}`); return i < 0 ? fallback : process.argv[i + 1] ?? ''; };
  const fromArg = arg('from', ''), throughArg = arg('through', '');
  const report = await acquireAtlasTv({ out: path.resolve(arg('out', 'data/opportunity-history')),
    assets: arg('assets', 'BTC,ETH').split(',').map((a) => a.trim().toUpperCase()), exchange: arg('exchange', 'COINBASE').toUpperCase(),
    quote: arg('quote', 'USD').toUpperCase(), bars: Number(arg('bars', '5000')), python: arg('python', process.env.TV_PYTHON ?? 'python3'),
    from: fromArg ? Date.parse(fromArg) : undefined, through: throughArg ? Date.parse(throughArg) : undefined });
  console.table(report.series.map((s) => ({ symbol: `${s.request.exchange}:${s.request.symbol}`, tf: s.request.tf,
    storedFrom: s.coverage.firstStored, storedThrough: s.coverage.lastStoredClose,
    missingBars: s.coverage.missingBars, formingExcluded: s.formingBarsExcluded, error: s.error })));
  console.log(`Coverage ${report.ready ? 'complete' : 'INCOMPLETE'}; see ${path.resolve(arg('out', 'data/opportunity-history'), 'tvdatafeed-coverage.json')}`);
  if (!report.ready) process.exitCode = 1;
}
if (process.argv[1] && /(^|[/\\])tvHistory\.(ts|js|cjs)$/.test(process.argv[1])) void main().catch((e) => { console.error(e); process.exitCode = 1; });
