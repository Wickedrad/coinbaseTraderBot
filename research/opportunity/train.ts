/** Research-only CLI. Reads the existing history store; NEVER touches live models. */
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { createReadStream } from 'node:fs';
import { readSeries, seriesPath } from '../../bot/marketdata/historyStore';
import { marketClockFeatures, sessionAt } from '../../bot/model/sessions';
import { defaultPathConfig, PATH_LABEL_SCHEMA, PathLabeler, type PathLabel, type PathLabelConfig } from './pathLabels';
import { verifyTvSeries } from './tvHistory';
import { ATLAS_SCHEMA, ConditionalOpportunityAtlas, FifteenMinuteIndicators, OpportunityLabeler,
  type AtlasFeatures, type AtlasReport, type MinuteCandle, type OpportunityEntry } from './atlas';

const MIN = 60_000, DAY = 86_400_000;
function arg(name: string, fallback: string): string {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}
function csvBar(line: string): MinuteCandle | undefined {
  if (!line || line.startsWith('ts')) return undefined;
  const z = line.split(',');
  if (z.length < 6) return undefined;
  const [ts, o, h, l, c, v] = z.slice(0, 6).map(Number);
  if (z.slice(0, 6).some((value) => !value.trim()) || ![ts, o, h, l, c, v].every(Number.isFinite) || !(ts >= 0 && ts % MIN === 0 && o > 0 && h >= Math.max(o, c) && l <= Math.min(o, c) && l > 0 && v >= 0)) return undefined;
  return { ts, o, h, l, c, v };
}
interface IndexPoint { knownAt: number; close: number; change: number }
/** Daily dominance updates enter only at the daily candle's closing timestamp, not opening timestamp. */
export class CompletedDailyIndex {
  private readonly points: IndexPoint[];

  constructor(candles: MinuteCandle[]) {
    if (candles.some((c, i) => !Number.isFinite(c.ts) || (i > 0 && c.ts <= candles[i - 1].ts))) {
      throw new Error('daily index timestamps must be finite and strictly increasing');
    }
    this.points = candles.map((c, i) => ({
      knownAt: c.ts + DAY, close: c.c,
      change: i > 0 && c.ts - candles[i - 1].ts === DAY && candles[i - 1].c > 0 && c.c > 0 ? Math.log(c.c / candles[i - 1].c) : NaN,
    }));
  }
  changeAt(t: number): number {
    if (!Number.isFinite(t)) return NaN;
    let lo = 0, hi = this.points.length;
    while (lo < hi) {
      const mid = Math.floor((lo + hi) / 2);
      if (this.points[mid].knownAt <= t) lo = mid + 1; else hi = mid;
    }
    const point = this.points[lo - 1];
    if (!point || t - point.knownAt > 2.5 * DAY) return NaN;
    return point.change;
  }
}
export interface RunOptions {
  historyDir: string; assets: string[]; source?: string; trainBefore: number; finalFrom: number;
  maxMinutes?: number; onProgress?: (message: string) => void;
  pathLabels?: { config?: Partial<Omit<PathLabelConfig, 'source' | 'trainBefore' | 'finalFrom'>>;
    onLabels: (rows: PathLabel[]) => void | Promise<void> };
}
export async function buildAtlas(o: RunOptions): Promise<AtlasReport[]> {
  const log = o.onProgress ?? (() => undefined);
  const daily = (symbol: string) => {
    // Use only raw TradingView daily history here. The general-purpose index splicer
    // can estimate a source-level scale from an entire future overlap, which is
    // acceptable for display but would leak future data into this training study.
    const file = seriesPath(o.historyDir, 'tradingview', symbol, '1d');
    return new CompletedDailyIndex(readSeries(file));
  };
  const reports: AtlasReport[] = [];
  for (const asset of o.assets) {
    const file = seriesPath(o.historyDir, o.source ?? 'binance-1m', asset, '1m');
    if (!fs.existsSync(file)) throw new Error(`Missing ${file}; acquire the requested one-minute history source first`);
    let provenance: NonNullable<AtlasReport['data']>['provenance'];
    if (o.source?.startsWith('tvdatafeed-')) {
      const spot = await verifyTvSeries(file, { asset, source: o.source, tf: '1m' });
      const daily: Record<string, { sha256: string; receipt: string } | null> = {};
      for (const symbol of ['BTC.D', 'USDT.D']) {
        const indexFile = seriesPath(o.historyDir, 'tradingview', symbol, '1d');
        daily[symbol] = fs.existsSync(indexFile) ? await verifyTvSeries(indexFile, { asset: symbol, source: 'tradingview', tf: '1d' }) : null;
      }
      provenance = { provider: 'tvdatafeed', spot, daily };
    }
    const btcd = daily('BTC.D'), usdtd = daily('USDT.D');
    const ta = new FifteenMinuteIndicators(), labeler = new OpportunityLabeler();
    const atlas = new ConditionalOpportunityAtlas(asset, { trainBefore: o.trainBefore, finalFrom: o.finalFrom });
    const paths = o.pathLabels ? new PathLabeler({
      ...defaultPathConfig(o.source ?? 'binance-1m', o.trainBefore, o.finalFrom), ...o.pathLabels.config,
    }) : undefined;
    let limited = false;
    let last = -Infinity, minutes = 0, entries = 0, malformed = 0, first: number | null = null, latest: number | null = null;
    const input = createReadStream(file);
    const reader = readline.createInterface({ input, crlfDelay: Infinity });
    try {
      for await (const line of reader) {
        const b = csvBar(line);
        if (!b) { if (line && !line.startsWith('ts')) malformed++; continue; }
        if (Number.isFinite(last) && b.ts !== last + MIN) ta.reset();
        last = b.ts;
        first ??= b.ts; latest = b.ts;
        const indicator = ta.push(b);
        let sample: OpportunityEntry | undefined;
        if (indicator && Object.values(indicator).every(Number.isFinite)) {
          const decisionTs = b.ts + MIN;
          const clock = marketClockFeatures(decisionTs);
          const hourAngle = Math.atan2(clock.et_hour_sin, clock.et_hour_cos);
          const etHour = ((hourAngle < 0 ? hourAngle + 2 * Math.PI : hourAngle) / (2 * Math.PI)) * 24;
          const f: AtlasFeatures = { ...indicator, session: sessionAt(decisionTs), etHour,
            btcdDailyChange: btcd.changeAt(decisionTs), usdtdDailyChange: usdtd.changeAt(decisionTs), knownAt: decisionTs };
          // Same clock/indicator calculations available to both future and current consumers.
          // Clock values are not trading filters; their interactions are learned in the atlas.
          if (Number.isFinite(clock.et_hour_sin)) { sample = { ts: decisionTs, asset, price: b.c, f }; entries++; }
        }
        for (const outcome of labeler.push(b, sample)) atlas.accept(outcome);
        if (paths) { const rows = paths.push(b, sample); if (rows.length) await o.pathLabels!.onLabels(rows); }
        if (++minutes % 1_000_000 === 0) log(`${asset}: processed ${minutes.toLocaleString()} one-minute bars`);
        if (o.maxMinutes && minutes >= o.maxMinutes) { limited = true; break; }
      }
    } finally { reader.close(); input.destroy(); }
    if (paths) await o.pathLabels!.onLabels(paths.finish(limited ? 'processing-limit' : 'end-of-input'));
    log(`${asset}: ${minutes} candles, ${entries} feature observations, ${labeler.gaps} time gaps, ${malformed} malformed rows`);
    const report = atlas.report(labeler.gaps);
    // Explicit provenance: input data is historical spot, not a Kalshi/perp execution replay.
    reports.push({ ...report, data: { source: o.source ?? 'binance-1m', firstMinute: first === null ? null : new Date(first).toISOString(),
      lastMinute: latest === null ? null : new Date(latest).toISOString(), oneMinuteBars: minutes, candidates: entries,
      malformedRows: malformed, ...(provenance ? { provenance } : {}) } });
  }
  return reports;
}

async function main(): Promise<void> {
  const hist = path.resolve(arg('history', 'data/opportunity-history'));
  const source = arg('source', 'tvdatafeed-coinbase');
  if (!/^[a-zA-Z0-9_-]+$/.test(source)) throw new Error('invalid history source');
  const out = path.resolve(arg('out', 'research/out/opportunity-atlas.json'));
  const trainBefore = Date.parse(arg('train-before', '2025-01-01'));
  const finalFrom = Date.parse(arg('final-from', '2026-01-01'));
  if (!(Number.isFinite(trainBefore) && Number.isFinite(finalFrom) && trainBefore < finalFrom)) throw new Error('invalid chronological partitions');
  const assets = arg('assets', 'BTC,ETH,SOL,XRP,DOGE').split(',').map((x) => x.trim().toUpperCase()).filter((x) => /^[A-Z0-9]+$/.test(x));
  if (!assets.length) throw new Error('at least one --assets value required');
  const maxMinutes = Number(arg('max-minutes', '0'));
  const labelsArg = arg('path-labels', '');
  const labelsFile = labelsArg ? path.resolve(labelsArg) : undefined;
  if (labelsFile) {
    const relative = path.relative(hist, labelsFile);
    if (labelsFile === out || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative))) {
      throw new Error('--path-labels must differ from --out and be outside the input history directory');
    }
  }
  const pathConfig = defaultPathConfig(source, trainBefore, finalFrom);
  pathConfig.targetsAtr = arg('path-targets-atr', '0.5,1,2').split(',').map(Number);
  pathConfig.stopsAtr = arg('path-stops-atr', '0.5,1,2').split(',').map(Number);
  pathConfig.costs = { feePerSideBps: Number(arg('path-fee-bps', '0')),
    halfSpreadBps: Number(arg('path-half-spread-bps', '0')), slippagePerSideBps: Number(arg('path-slippage-bps', '0')) };
  if (labelsFile) new PathLabeler(pathConfig); // validate before opening any output
  const labelsTemp = labelsFile ? `${labelsFile}.${process.pid}.tmp` : undefined;
  if (labelsFile) fs.mkdirSync(path.dirname(labelsFile), { recursive: true });
  const writer = labelsTemp ? await fs.promises.open(labelsTemp, 'wx') : undefined;
  let buffer = '', labelRows = 0, censoredRows = 0, purgedRows = 0;
  let reports: AtlasReport[];
  try {
    if (writer) buffer = JSON.stringify({ type: 'metadata', schema: PATH_LABEL_SCHEMA,
      researchOnly: true, executable: false, autoPromote: false, historicalSource: hist, config: pathConfig }) + '\n';
    reports = await buildAtlas({ historyDir: hist, assets, source, trainBefore, finalFrom,
      maxMinutes: maxMinutes > 0 ? maxMinutes : undefined, onProgress: console.log,
      pathLabels: writer ? { config: pathConfig, onLabels: async (rows) => {
        for (const row of rows) {
          labelRows++; if (row.censorReason) censoredRows++; if (row.partition === 'purged') purgedRows++;
          buffer += JSON.stringify(row) + '\n';
          if (buffer.length >= 1_048_576) { await writer.writeFile(buffer); buffer = ''; }
        }
      } } : undefined });
    if (writer && buffer) await writer.writeFile(buffer);
  } catch (error) {
    await writer?.close();
    if (labelsTemp) fs.rmSync(labelsTemp, { force: true });
    throw error;
  }
  await writer?.close();
  if (labelsTemp) fs.renameSync(labelsTemp, labelsFile!);
  const result = { schema: ATLAS_SCHEMA, createdAt: new Date().toISOString(),
    researchOnly: true, executable: false, autoPromote: false,
    historicalSource: hist, trainingSource: 'one-minute observed OHLCV; session clock; closed daily BTC.D and USDT.D',
    caution: 'V1 forecasts close-to-close direction and excursion/touch rates, not reversal onset, first-touch order, net returns, or fillable trading edges.',
    assets: reports, ...(labelsFile ? { pathLabels: { schema: PATH_LABEL_SCHEMA, file: labelsFile, rows: labelRows, censoredRows, purgedRows } } : {}) };
  fs.mkdirSync(path.dirname(out), { recursive: true });
  const temp = `${out}.${process.pid}.tmp`;
  fs.writeFileSync(temp, JSON.stringify(result, null, 2) + '\n');
  fs.renameSync(temp, out);
  console.log(`Research report written to ${out}; NO live model or trading configuration changed`);
}
if (process.argv[1] && /(^|[/\\])train\.(ts|js|cjs)$/.test(process.argv[1])) void main().catch((e) => { console.error(e); process.exitCode = 1; });
