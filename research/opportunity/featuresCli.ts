/** Data/feature validation only: never reads future labels or fits/evaluates a model. */
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import type { Candle } from '../../bot/ta/indicators';
import { TANET_SCHEMA } from '../../bot/ta/taNet';
import { taEngine } from '../../bot/ta/talib';
import { ATLAS_FEATURE_SCHEMA, ATLAS_FEATURE_WINDOWS, AsOfDailyFeatures, CausalAtlasFeatures, type AtlasFeatureFrame } from './features';
import { parseMinuteCsv } from './minuteCsv';

const DAY = 86400000;
interface AuditFile { path: string; sha256: string; ready: boolean; rows: number; source: string }
export interface FeatureRunOptions {
  archiveDir: string; assets: string[]; everyMinutes?: number; maxMinutes?: number;
  dailyLagMs?: number; dailyMaxAgeMs?: number;
  onFrame?: (frame: AtlasFeatureFrame) => void | Promise<void>;
  onProgress?: (message: string) => void;
}
export async function hashFile(file: string): Promise<string> {
  const digest = createHash('sha256');
  for await (const chunk of fs.createReadStream(file)) digest.update(chunk);
  return digest.digest('hex');
}
async function* candles(file: string): AsyncGenerator<Candle> {
  const input = fs.createReadStream(file), reader = readline.createInterface({ input, crlfDelay: Infinity });
  let lineNo = 0;
  try {
    for await (const line of reader) {
      lineNo++;
      if (lineNo === 1 && (line === 'ts,o,h,l,c,v' || line === 'ts,o,h,l,c,v,tb')) continue;
      const bar = parseMinuteCsv(line);
      if (!bar) throw new Error(`Invalid canonical candle at ${file}:${lineNo}`);
      yield bar;
    }
  } finally { reader.close(); input.destroy(); }
}
export async function buildFeatureReport(o: FeatureRunOptions) {
  const every = o.everyMinutes ?? 15, max = o.maxMinutes ?? Infinity;
  if (!Number.isSafeInteger(every) || every < 1 || !(max === Infinity || (Number.isSafeInteger(max) && max > 0)) ||
      !o.assets.length || o.assets.some((a) => !['BTC', 'ETH', 'SOL', 'XRP', 'DOGE'].includes(a))) throw new Error('invalid feature run options');
  const base = path.resolve(o.archiveDir), history = path.join(base, 'history');
  const root = fileURLToPath(new URL('../../', import.meta.url));
  const codeHashes: Record<string, string> = {};
  const codeFiles = ['research/opportunity/features.ts', 'research/opportunity/minuteCsv.ts', 'research/opportunity/featuresCli.ts', 'bot/model/sessions.ts',
    ...fs.readdirSync(path.join(root, 'bot/ta')).filter((name) => name.endsWith('.ts')).map((name) => `bot/ta/${name}`)];
  for (const name of codeFiles) codeHashes[name] = await hashFile(path.join(root, name));
  const auditPath = path.join(base, 'archive-validation.json'), auditSha256 = await hashFile(auditPath);
  const manifest = JSON.parse(fs.readFileSync(auditPath, 'utf8'));
  if (manifest.schema !== 'atlas-archive-audit-v1') throw new Error('unrecognized archive audit');
  const files: AuditFile[] = manifest.files;
  const verified = new Map<string, AuditFile>();
  const verify = async (name: string, required: boolean): Promise<AuditFile | undefined> => {
    const record = files.find((r) => r.path === name);
    if (!record) { if (required) throw new Error(`Missing audited input ${name}`); return undefined; }
    const file = path.join(history, name);
    if (!record.ready || !/^[a-f0-9]{64}$/.test(record.sha256) ||
        !fs.realpathSync(file).startsWith(fs.realpathSync(history) + path.sep) || await hashFile(file) !== record.sha256) throw new Error(`Input audit/hash mismatch: ${name}`);
    verified.set(name, record); return record;
  };
  const context: Record<string, AsOfDailyFeatures> = {};
  const daily = async (name: string, key: string, volume: boolean) => {
    const record = await verify(name, false);
    if (!record) {
      context[key] = new AsOfDailyFeatures([], { source: name, sha256: null }, o.dailyLagMs, o.dailyMaxAgeMs, volume);
      return;
    }
    const bars: Candle[] = [];
    for await (const c of candles(path.join(history, name))) bars.push(c);
    context[key] = new AsOfDailyFeatures(bars, { source: name, sha256: record.sha256 }, o.dailyLagMs, o.dailyMaxAgeMs, volume);
  };
  for (const symbol of ['BTC.D', 'USDT.D']) await daily(`tradingview/${symbol}/1d.csv`, `dominance_${symbol === 'BTC.D' ? 'btcd' : 'usdtd'}`, false);
  const reports = [];
  for (const asset of o.assets) {
    const name = `binance-1m/${asset}/1m.csv`, record = (await verify(name, true))!;
    await daily(`yahoo/${asset}/1d.csv`, 'yahoo_daily', true);
    const provider = new CausalAtlasFeatures(asset, { source: name, sha256: record.sha256 }, { ...context });
    const groups: Record<string, { ready: number; warming: number; missing: number; stale: number; features: number; nullValues: number }> = {};
    let minutes = 0, frames = 0, first: number | null = null, last: number | null = null;
    for await (const bar of candles(path.join(history, name))) {
      provider.push(bar); minutes++; first ??= bar.ts; last = bar.ts;
      if ((bar.ts / 60000 + 1) % every === 0) {
        const frame = provider.snapshot(); frames++;
        for (const [key, group] of Object.entries(frame.groups)) {
          if (group.knownAt !== null && group.knownAt > frame.decisionAt) throw new Error(`future feature: ${key}`);
          const counts = groups[key] ??= { ready: 0, warming: 0, missing: 0, stale: 0, features: Object.keys(group.values).length, nullValues: 0 };
          counts[group.status]++;
          counts.nullValues += Object.values(group.values).filter((v) => v === null).length;
        }
        await o.onFrame?.(frame);
      }
      if (minutes % 50000 === 0) o.onProgress?.(`${asset}: ${minutes} observed minutes, ${frames} feature frames`);
      if (minutes >= max) break;
    }
    reports.push({ asset, minutes, frames, firstOpen: first, lastOpen: last, gaps: provider.gaps, groups });
    delete context.yahoo_daily;
  }
  // Detect changes during the replay, too; do not publish a report for mixed input versions.
  for (const [name, record] of verified) if (await hashFile(path.join(history, name)) !== record.sha256) throw new Error(`Input changed during feature run: ${name}`);
  for (const [name, digest] of Object.entries(codeHashes)) if (await hashFile(path.join(root, name)) !== digest) throw new Error(`Code changed during feature run: ${name}`);
  if (await hashFile(auditPath) !== auditSha256) throw new Error('Archive audit changed during feature run');
  return { schema: ATLAS_FEATURE_SCHEMA, createdAt: new Date().toISOString(), researchOnly: true, autoPromote: false,
    purpose: 'causal feature/data validation only; no outcome scoring, model fitting or holdout reuse',
    taSchema: TANET_SCHEMA, engine: taEngine(), windows: ATLAS_FEATURE_WINDOWS, everyMinutes: every,
    dailyPolicy: { lagMs: o.dailyLagMs ?? DAY, maxAgeMs: o.dailyMaxAgeMs ?? 2 * DAY, publicationTimesVerified: false },
    sourceIdentity: 'archive-path declarations; not independently provider authenticated',
    codeHashes, auditSha256, inputs: [...verified.values()], assets: reports };
}
function arg(name: string, fallback: string) { const i = process.argv.indexOf(`--${name}`); return i < 0 ? fallback : process.argv[i + 1] ?? fallback; }
async function main() {
  const archiveDir = path.resolve(arg('archive', 'data/opportunity-archive'));
  const out = path.resolve(arg('out', 'research/out/opportunity-features.json'));
  const framesArg = arg('frames', ''), framesFile = framesArg ? path.resolve(framesArg) : undefined;
  for (const file of [out, framesFile].filter((x): x is string => !!x)) {
    const rel = path.relative(archiveDir, file);
    if (rel === '' || (!rel.startsWith(`..${path.sep}`) && rel !== '..' && !path.isAbsolute(rel))) throw new Error('feature outputs must be outside the input archive');
  }
  if (framesFile === out) throw new Error('frames and report paths must differ');
  const tempFrames = framesFile ? `${framesFile}.${process.pid}.tmp` : undefined;
  if (framesFile) fs.mkdirSync(path.dirname(framesFile), { recursive: true });
  const writer = tempFrames ? await fs.promises.open(tempFrames, 'wx') : undefined;
  try {
    const maxArg = arg('max-minutes', '');
    const report = await buildFeatureReport({ archiveDir, assets: arg('assets', 'BTC,ETH').split(',').map((s) => s.trim().toUpperCase()),
      maxMinutes: maxArg ? Number(maxArg) : undefined, everyMinutes: Number(arg('every-minutes', '15')),
      onProgress: console.log,
      onFrame: writer ? async (frame) => { await writer.writeFile(JSON.stringify(frame) + '\n'); } : undefined });
    await writer?.close();
    fs.mkdirSync(path.dirname(out), { recursive: true });
    const temp = `${out}.${process.pid}.tmp`;
    fs.writeFileSync(temp, JSON.stringify(report, null, 2) + '\n');
    if (tempFrames) fs.renameSync(tempFrames, framesFile!);
    fs.renameSync(temp, out);
    console.log(`Feature validation report: ${out}; no fitting, outcome evaluation or live changes`);
  } catch (error) { await writer?.close(); if (tempFrames) fs.rmSync(tempFrames, { force: true }); throw error; }
}
if (process.argv[1] && /(^|[/\\])featuresCli\.(ts|js)$/.test(process.argv[1])) void main().catch((e) => { console.error(e); process.exitCode = 1; });
