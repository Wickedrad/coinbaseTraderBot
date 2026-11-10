/** GitHub-only forward Oracle trial: tvdatafeed features, public books, native $200 paper accounts. */
import fs from 'node:fs';
import path from 'node:path';
import { parseMarket, parseOrderbook, parseSeriesFees } from '../../bot/kalshi/wire';
import { FeeBook, readPublishedSchedulePdf, FEE_SCHEDULE_URL, type PublishedSchedule } from '../../bot/kalshi/feeSchedule';
import publishedSnapshot from '../../bot/kalshi/feeScheduleSnapshot.json';
import type { MarketInfo } from '../../bot/kalshi/types';
import { readSeries, seriesPath } from '../../bot/marketdata/historyStore';
import { acquireAtlasTv } from './tvHistory';
import { CompletedDailyIndex } from './train';
import { OracleFeatures, ORACLE_HORIZONS } from './oracleMatrix';
import { EDGE_POLICY, edgeDirection, edgeEvidence, loadEdgeOracle, scoreEdgeForecast, type EdgeForecast } from './oracleEdge';
import { DirectionPaperAccount, type PaperFeeTerms, type DirectionPaperSignal } from './directionPaper';
import type { TimedPriceContract } from './contractTiming';
import type { ProfitPolicy } from './profitExit';
import { codeHashes, unchanged } from './productCli';
import { digest } from './contractDataset';
import { sha256File } from './jointPathData';

const BASE = 'https://external-api.kalshi.com/trade-api/v2', MIN = 60000;
const ARMS = ['weighted', 'uniform', 'prior', 'reversed', 'always-up', 'always-down', 'random'] as const;
type Arm = typeof ARMS[number];
const write = (file: string, value: unknown) => fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n');
export async function runOracleEdge(o: { models: string; weights: string; out: string; cycles: number; python?: string; assets?: string[] }) {
  if (!Number.isInteger(o.cycles) || o.cycles < 2 || o.cycles > 90) throw new Error('edge cycles must be 2..90 minutes');
  const assets = o.assets ?? [...EDGE_POLICY.assets];
  if (!assets.length || assets.some((a) => !EDGE_POLICY.assets.includes(a)) || new Set(assets).size !== assets.length) throw new Error('invalid edge assets');
  const root = path.resolve(o.out); if (fs.existsSync(root)) throw new Error('new forward output required'); fs.mkdirSync(root, { recursive: true });
  const models = new Map<string, Awaited<ReturnType<typeof loadEdgeOracle>>>();
  for (const asset of assets) models.set(asset, await loadEdgeOracle(path.join(o.models, `atlas-oracle-result-${asset}/walk/model.json`), path.join(o.weights, `atlas-oracle-importance-${asset}/importance.json`)));
  const startedAt = Date.now(), stopAt = startedAt + o.cycles * MIN, code = await codeHashes();
  const registration = { schema: 'atlas-oracle-forward-edge-v1', policy: EDGE_POLICY, startedAt, stopAt, assets, cycles: o.cycles,
    mode: o.cycles < 65 ? 'engineering-short-trial' : 'locked-forward-trial', models: [...models].map(([asset, m]) => ({ asset, id: m.modelId, model: m.modelHash, importance: m.importanceHash, learnedThrough: m.learnedThrough })),
    arms: ARMS, primary: 'weighted', paper: { startingCash: 200, maximumPositionCost: 20, maximumContracts: 40, maximumOpenPositions: 5,
      minimumNetTakeUsd: 0.01, targetContractRoi: 0, minimumSignalProbability: 0, maximumQuoteAgeMs: 2000, maximumSignalAgeMs: 90000, saleBufferMs: 30000 },
    publication: 'Fsynced forecast record and public Actions log before consuming any subsequent book or outcome',
    priceTarget: 'Return from the last completed minute close to its exact 15m/60m future close; actual publication lag and remaining lead recorded',
    contracts: 'Monotone hourly threshold contracts closing within the collection window; 15m Oracle horizon must fit before sale deadline',
    noFit: true, liveEntryAllowed: false, actualVenueProfitVerified: false, codeHashes: code };
  write(path.join(root, 'registration.json'), registration); console.log(`LOCKED_EDGE_REGISTRATION ${digest(registration)}`);
  const fds = Object.fromEntries(['forecasts', 'books', 'fees', 'acquisitions'].map((name) => [name, fs.openSync(path.join(root, `${name}.jsonl`), 'wx')]));
  const append = (name: string, value: unknown, sync = false) => { fs.writeSync(fds[name], JSON.stringify(value) + '\n'); if (sync) fs.fsyncSync(fds[name]); };
  const profit = JSON.parse(fs.readFileSync('research/opportunity/examples/profit-policy.json', 'utf8')) as ProfitPolicy;
  const accounts = new Map<Arm, DirectionPaperAccount>(ARMS.map((arm) => [arm, new DirectionPaperAccount(registration.paper, profit, startedAt)]));
  const features = new Map(assets.map((a) => [a, new OracleFeatures()])), closes = new Map(assets.map((a) => [a, new Map<number, number>()]));
  const barsSeen = new Map<string, Map<number, string>>(assets.map((a) => [a, new Map()])), rejectedAssets = new Set<string>();
  const forecasts: EdgeForecast[] = [], lastForecast = new Map<string, number>(), latest = new Map<string, EdgeForecast>();
  const markets = new Map<string, MarketInfo[]>(), terms = new Map<string, TimedPriceContract>(), feeInfo = new Map<string, PaperFeeTerms>();
  const feeBook = new FeeBook(0.01, undefined, publishedSnapshot as PublishedSchedule); let publicationFresh = false;
  const counts = { requests: 0, requestFailures: 0, acquisitions: 0, acquisitionFailures: 0, forecasts: 0, books: 0, depthBooks: 0, revisedAssets: 0, timingRejected: 0, missingFeatures: 0 };
  let failure: string | null = null;
  let eventFeesKnown = false, eventFeesSha = '';
  const seriesChangesKnown = new Set<string>();
  async function get(route: string) {
    counts.requests++; const requestedAt = Date.now();
    try { const r = await fetch(BASE + route, { method: 'GET', redirect: 'error', signal: AbortSignal.timeout(15000) }); if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const raw = await r.text(); if (raw.length > 4 * 1024 * 1024) throw new Error('oversized public response'); return { data: JSON.parse(raw), requestedAt, knownAt: Date.now(), sourceSha256: digest(raw) };
    } catch { counts.requestFailures++; return null; }
  }
  async function refreshFees(series: string) {
    const r = await get(`/series/${series}`); if (!r) return;
    const info = parseSeriesFees(r.data); feeBook.setSeries(series, info, r.knownAt);
    if (!info) return;
    const changes = await get(`/series/fee_changes?series_ticker=${series}`);
    if (changes) {
      feeBook.setSeriesChanges(series, (changes.data.series_fee_change_arr ?? []).map((c: any) => ({ feeType: c.fee_type ? String(c.fee_type) : undefined,
        multiplier: c.fee_multiplier === null ? undefined : Number(c.fee_multiplier), scheduledTs: Date.parse(String(c.scheduled_ts)) })).filter((c: { scheduledTs: number }) => Number.isFinite(c.scheduledTs)));
      append('fees', { series, changes }); seriesChangesKnown.add(series);
    }
    const schedule = feeBook.feesFor(series, undefined, r.knownAt);
    const receipt: PaperFeeTerms = { schedule, knownAt: r.knownAt, effectiveFrom: r.knownAt, sourceSha256: r.sourceSha256,
      basis: publicationFresh && eventFeesKnown && seriesChangesKnown.has(series) && schedule.source === 'api, matches the published schedule' ? 'observed-as-of' : 'assumed-schedule' };
    append('fees', { series, ...r, info, receipt }); feeInfo.set(series, receipt);
  }
  function signal(f: EdgeForecast, arm: Arm): DirectionPaperSignal | null {
    const p = arm === 'uniform' ? f.uniform : arm === 'prior' ? f.prior : f.p;
    let direction = edgeDirection(p);
    if (arm === 'reversed' && direction) direction = direction === 'up' ? 'down' : 'up';
    if (arm === 'always-up' || arm === 'always-down') direction = arm === 'always-up' ? 'up' : 'down';
    if (arm === 'random') direction = parseInt(digest([f.asset, f.featureAt, 1729]).slice(0, 8), 16) % 2 ? 'up' : 'down';
    return direction ? { id: f.id, modelId: f.modelId, asOf: f.publishedAt, producedAt: f.publishedAt, featuresKnownAt: f.featuresKnownAt,
      byAt: f.byAt, direction, probability: p[direction === 'up' ? 0 : 2] } : null;
  }
  try {
    try { const r = await fetch(FEE_SCHEDULE_URL, { signal: AbortSignal.timeout(20000), redirect: 'follow' });
      if (r.ok) { const pdf = Buffer.from(await r.arrayBuffer()); if (pdf.length > 8 * 1024 * 1024) throw new Error('oversized fee PDF');
        const parsed = readPublishedSchedulePdf(pdf, Date.now()); feeBook.setPublished(parsed, Date.now()); publicationFresh = !('error' in parsed);
        fs.writeFileSync(path.join(root, 'fee-schedule.pdf'), pdf); append('fees', { url: FEE_SCHEDULE_URL, sha256: digest(pdf.toString('base64')), parsed }); }
    } catch { /* Retain and identify the maintained built-in schedule, never claim a fresh read. */ }
    for (let cycle = 0; cycle < o.cycles; cycle++) {
      const cycleAt = Date.now(); let acquired = false;
      try {
        const report = await acquireAtlasTv({ out: path.join(root, 'tv-history'), assets, exchange: 'BINANCE', quote: 'USDT', bars: cycle === 0 ? 5000 : 5, python: o.python });
        const knownAt = Date.now(); counts.acquisitions++; acquired = true;
        append('acquisitions', { cycle, knownAt, report });
        const dominance = ['BTC.D', 'USDT.D'].map((a) => new CompletedDailyIndex(readSeries(seriesPath(path.join(root, 'tv-history'), 'tradingview', a, '1d'))));
        for (const asset of assets) {
          if (rejectedAssets.has(asset)) continue;
          const source = report.series.find((s) => s.request.asset === asset); if (!source || source.error) { counts.missingFeatures++; continue; }
          const rows = readSeries(source.file), seen = barsSeen.get(asset)!, feature = features.get(asset)!; let latestFeature: ReturnType<OracleFeatures['push']> | undefined;
          for (const b of rows) {
            const hash = digest([b.ts, b.o, b.h, b.l, b.c]), old = seen.get(b.ts);
            if (old && old !== hash) { rejectedAssets.add(asset); counts.revisedAssets++; break; }
            if (old) continue; seen.set(b.ts, hash);
            latestFeature = feature.push(b, dominance.map((d) => d.changeAt(b.ts + MIN - 86400000)) as [number, number]); closes.get(asset)!.set(b.ts + MIN, b.c);
          }
          if (!latestFeature || rejectedAssets.has(asset) || !(latestFeature.atrBps > 0) || knownAt - latestFeature.at > EDGE_POLICY.maximumBarAgeMs) { counts.missingFeatures++; continue; }
          if (lastForecast.get(asset) === latestFeature.at) continue; lastForecast.set(asset, latestFeature.at);
          for (const horizon of ORACLE_HORIZONS) {
            const f = models.get(asset)!.forecast({ raw: latestFeature.raw, featureAt: latestFeature.at, knownAt, publishedAt: Date.now(), anchor: rows.at(-1)!.c, atrBps: latestFeature.atrBps, horizon });
            append('forecasts', f, true); forecasts.push(f); counts.forecasts++; if (horizon === 15) latest.set(asset, f);
            console.log(`ORACLE_FORECAST ${JSON.stringify(f)}`);
          }
        }
      } catch (e) { counts.acquisitionFailures++; append('acquisitions', { cycle, failedAt: Date.now(), error: String(e) }); }
      if (cycle === 0 && (!acquired || !counts.forecasts)) throw new Error('tvdatafeed bootstrap produced no eligible features; no alternate history source is allowed');
      const eventChanges: Array<{ eventTicker: string; seriesTicker: string; type: string | null; multiplier: number | null; scheduledTs: number }> = [];
      let cursor = ''; eventFeesKnown = false;
      for (let page = 0; page < 5; page++) {
        const r = await get(`/events/fee_changes?limit=1000${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`); if (!r) break;
        append('fees', { events: r }); eventFeesSha = digest([eventFeesSha, r.sourceSha256]);
        for (const c of r.data.event_fee_changes ?? []) {
          const scheduledTs = Date.parse(String(c.scheduled_ts)); if (!c.event_ticker || !Number.isFinite(scheduledTs)) continue;
          eventChanges.push({ eventTicker: String(c.event_ticker), seriesTicker: String(c.series_ticker ?? String(c.event_ticker).split('-')[0]),
            type: c.fee_type_override ? String(c.fee_type_override) : null, multiplier: c.fee_multiplier_override == null ? null : Number(c.fee_multiplier_override), scheduledTs });
        }
        cursor = r.data.cursor ? String(r.data.cursor) : ''; if (!cursor) { eventFeesKnown = true; break; }
      }
      if (eventFeesKnown) feeBook.setEventChanges(eventChanges, (series) => assets.some((a) => series === `KX${a}D`), Date.now());
      seriesChangesKnown.clear();
      for (const asset of assets) {
        const series = `KX${asset}D`, r = await get(`/markets?series_ticker=${series}&status=open&limit=100`);
        if (r) {
          const anchor = [...closes.get(asset)!.values()].at(-1);
          const ms = (r.data.markets ?? []).map(parseMarket).filter((m: MarketInfo | undefined): m is MarketInfo => !!m && m.seriesTicker === series &&
            m.openTime <= r.knownAt && m.closeTime > r.knownAt && m.closeTime <= r.knownAt + 60 * MIN && m.floorStrike !== undefined && m.strikeType !== 'between' && /^.*-T/.test(m.ticker));
          ms.sort((a: MarketInfo, b: MarketInfo) => Math.abs((a.floorStrike ?? 0) - (anchor ?? 0)) - Math.abs((b.floorStrike ?? 0) - (anchor ?? 0)) || a.ticker.localeCompare(b.ticker));
          markets.set(asset, ms.slice(0, 1));
          for (const m of ms.slice(0, 1)) if (!terms.has(m.ticker)) terms.set(m.ticker, { ticker: m.ticker, asset, openTime: m.openTime, closeTime: m.closeTime,
            termsKnownAt: r.knownAt, terms: { kind: 'greater', strike: m.floorStrike! }, settlementReference: `CF-RTI:${asset}:kalshi` });
        }
        await refreshFees(series);
      }
      do {
        // Keep managing previously selected contracts even when ATM selection changes.
        const selected = new Map([...markets.values()].flat().map((m) => [m.ticker, m]));
        for (const [ticker, c] of terms) if (c.closeTime > Date.now()) selected.set(ticker, { ticker, seriesTicker: `KX${c.asset}D` } as MarketInfo);
        for (const m of selected.values()) {
          const c = terms.get(m.ticker)!, feeBase = feeInfo.get(m.seriesTicker); if (!feeBase || c.closeTime <= Date.now()) continue;
          const r = await get(`/markets/${encodeURIComponent(m.ticker)}/orderbook?depth=50`); if (!r) continue;
          const book = parseOrderbook(r.data), q = { ticker: m.ticker, at: r.requestedAt, knownAt: r.knownAt, sourceSha256: r.sourceSha256, ...book };
          const schedule = feeBook.feesFor(m.seriesTicker, m.eventTicker ?? m.ticker.slice(0, m.ticker.lastIndexOf('-')), r.knownAt);
          const fees = { ...feeBase, schedule, sourceSha256: digest([feeBase.sourceSha256, eventFeesSha, schedule]),
            basis: publicationFresh && eventFeesKnown && seriesChangesKnown.has(m.seriesTicker) && schedule.source === 'api, matches the published schedule'
              ? 'observed-as-of' as const : 'assumed-schedule' as const };
          counts.books++; counts.depthBooks += Number(!!book.bids.length || !!book.asks.length); append('books', { contract: c, quote: q, fees });
          const f = latest.get(c.asset), isSelected = markets.get(c.asset)?.some((x) => x.ticker === m.ticker);
          const timely = f && f.byAt <= c.closeTime - EDGE_POLICY.saleBufferMs && f.byAt > r.knownAt && c.closeTime <= stopAt - MIN;
          if (f && !timely) counts.timingRejected++;
          for (const [arm, account] of accounts) await account.observe(c, q, fees, f && timely && isSelected && !rejectedAssets.has(c.asset) ? signal(f, arm) : null);
        }
        if (Date.now() < cycleAt + MIN) await new Promise((r) => setTimeout(r, Math.min(EDGE_POLICY.quotePollMs, cycleAt + MIN - Date.now())));
      } while (Date.now() < cycleAt + MIN);
      console.log(`EDGE_PROGRESS ${JSON.stringify({ cycle: cycle + 1, counts, primary: accounts.get('weighted')!.report() })}`);
      write(path.join(root, 'progress.json'), { at: Date.now(), cycle: cycle + 1, counts });
    }
  } catch (e) { failure = e instanceof Error ? e.message : String(e); }
  finally { for (const fd of Object.values(fds)) fs.closeSync(fd); }
  const knownAt = Date.now(), scored = forecasts.map((f) => rejectedAssets.has(f.asset) ? { id: f.id, status: 'revised-source-unavailable' } : scoreEdgeForecast(f, closes.get(f.asset)!, knownAt));
  fs.writeFileSync(path.join(root, 'outcomes.jsonl'), scored.map((r) => JSON.stringify(r)).join('\n') + '\n');
  const paper = [...accounts].map(([arm, account]) => {
    fs.writeFileSync(path.join(root, `${arm}-fills.jsonl`), account.fills.map((r) => JSON.stringify(r)).join('\n') + '\n');
    fs.writeFileSync(path.join(root, `${arm}-sales.jsonl`), account.sales.map((r) => JSON.stringify(r)).join('\n') + '\n');
    const result = account.report(); return { arm, ...result, capitalLowerBoundNetUsd: result.endingCash - EDGE_POLICY.poolUsd };
  });
  await unchanged({}, code);
  const report = { ...registration, endedAt: knownAt, counts, failure, rejectedAssets: [...rejectedAssets],
    direction: edgeEvidence(scored.filter((r): r is ReturnType<typeof scoreEdgeForecast> => r.status !== 'revised-source-unavailable')),
    paper, forecastsSha256: await sha256File(path.join(root, 'forecasts.jsonl')), booksSha256: await sha256File(path.join(root, 'books.jsonl')),
    outcomesSha256: await sha256File(path.join(root, 'outcomes.jsonl')),
    edgeVerified: false, qualification: 'Research evidence only; no promotion. Require adequate non-overlapping time groups, calibration and fee-net performance beyond matched controls.',
    limitations: ['Explicit Binance archive to TradingView BINANCE transfer, with missing warmup axes reported', 'Minute-close targets do not establish intraminute reversal timing',
      'Only the saved Oracle relationships and learned importance produce the predictions; controls are predeclared', 'Polled public-book taker simulation, not private fills; unresolved exposure is not settlement profit',
      'Current PDF read and API fee type recorded; fallback published rates remain labeled assumptions', 'Short runs leave unexpired one-hour questions pending; no forced labels'] };
  write(path.join(root, 'report.json'), report); if (failure) throw new Error(failure); return report;
}
const arg = (name: string, fallback = '') => { const i = process.argv.indexOf(`--${name}`); return i < 0 ? fallback : process.argv[i + 1]; };
if (process.argv[1] && /(^|[/\\])oracleEdgeCli\.(ts|js)$/.test(process.argv[1])) void runOracleEdge({ models: arg('models'), weights: arg('weights'), out: arg('out'),
  cycles: Number(arg('cycles', '72')), python: arg('python', 'python3'), assets: arg('assets', 'BTC,ETH,SOL,XRP,DOGE').split(',') })
  .then((r) => console.log(JSON.stringify({ counts: r.counts, direction: r.direction, paper: r.paper }))).catch((e) => { console.error(e instanceof Error ? e.stack : e); process.exitCode = 1; });
