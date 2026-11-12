/** Public GET-only quote capture on GitHub. Fresh holdout evidence; no model fitting or orders. */
import fs from 'node:fs';
import path from 'node:path';
import { parseMarket, parseOrderbook } from '../../bot/kalshi/wire';
import type { MarketInfo } from '../../bot/kalshi/types';
import { atomicDirectory, codeHashes, unchanged } from './productCli';
import { digest, stamp } from './contractDataset';
import { sha256File } from './jointPathData';
import { studyPolicy } from './studyPolicy';

const BASE = 'https://external-api.kalshi.com/trade-api/v2';
const ASSETS = ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE'];
export async function collectContractBooks(o: { out: string; cycles: number; intervalMs?: number; assets?: string[];
  fetcher?: typeof fetch; now?: () => number; wait?: (ms: number) => Promise<void> }) {
  const now = o.now ?? Date.now, wait = o.wait ?? ((ms) => new Promise((r) => setTimeout(r, ms))), fetcher = o.fetcher ?? fetch;
  const intervalMs = o.intervalMs ?? 5000, assets = o.assets ?? ASSETS, policy = studyPolicy('prospective-2026-11-09-v1');
  if (!Number.isInteger(o.cycles) || o.cycles < 1 || o.cycles > 240 || !Number.isInteger(intervalMs) || intervalMs < 1000 || intervalMs > 10000 ||
      !assets.length || assets.some((a) => !ASSETS.includes(a)) || new Set(assets).size !== assets.length || !stamp(now()) || now() < policy.finalFrom) throw new Error('invalid public holdout capture policy');
  const code = await codeHashes();
  return atomicDirectory(o.out, async (dir) => {
    const startedAt = now(), registration = { schema: 'atlas-public-contract-books-v1', startedAt, cycles: o.cycles, intervalMs, assets, source: BASE,
      holdoutFrom: policy.finalFrom, finalHoldoutEvidence: true, labelsUsedForFitting: false, forecastsPublished: false,
      orderClientConstructed: false, accountCredentialsUsed: false, allowedMethod: 'GET', purpose: 'Quote-health and locked future evidence collection; no prediction evaluation or model selection', codeHashes: code };
    fs.writeFileSync(path.join(dir, 'registration.json'), JSON.stringify(registration, null, 2) + '\n');
    const fd = fs.openSync(path.join(dir, 'books.jsonl'), 'wx'), marketsFd = fs.openSync(path.join(dir, 'markets.jsonl'), 'wx');
    const counts = { requests: 0, failedRequests: 0, books: 0, nonemptyBooks: 0, bothSides: 0, crossed: 0 }, active = new Map<string, MarketInfo>();
    let refreshedAt = 0;
    async function get(route: string) {
      counts.requests++; const requestedAt = now();
      try {
        const res = await fetcher(BASE + route, { method: 'GET', redirect: 'error', signal: AbortSignal.timeout(15000), headers: { Accept: 'application/json' } });
        if (!res.ok) throw new Error(`public quote HTTP ${res.status}`);
        const raw = await res.text(); if (raw.length > 4 * 1024 * 1024) throw new Error('public response exceeds limit');
        return { requestedAt, knownAt: now(), data: JSON.parse(raw), rawSha256: digest(raw) };
      } catch { counts.failedRequests++; return null; }
    }
    try { for (let cycle = 0; cycle < o.cycles; cycle++) {
      const cycleAt = now();
      if (!refreshedAt || cycleAt - refreshedAt >= 60000) {
        for (const asset of assets) {
          const series = `KX${asset}15M`, reply = await get(`/markets?series_ticker=${series}&status=open&limit=100`);
          if (!reply) continue;
          const candidates = (reply.data.markets ?? []).map(parseMarket).filter((m: MarketInfo | undefined): m is MarketInfo =>
            !!m && m.seriesTicker === series && m.openTime <= reply.knownAt && m.closeTime > reply.knownAt && ['open', 'active'].includes(m.status));
          candidates.sort((a: MarketInfo, b: MarketInfo) => a.closeTime - b.closeTime || a.ticker.localeCompare(b.ticker));
          if (candidates[0]) { active.set(asset, candidates[0]); fs.writeSync(marketsFd, JSON.stringify({ asset, knownAt: reply.knownAt, market: candidates[0] }) + '\n'); }
          else active.delete(asset);
        }
        refreshedAt = now();
      }
      for (const [asset, market] of active) {
        if (market.closeTime <= now()) continue;
        const reply = await get(`/markets/${encodeURIComponent(market.ticker)}/orderbook?depth=50`); if (!reply) continue;
        const book = parseOrderbook(reply.data), bid = book.bids[0], ask = book.asks[0];
        counts.books++; counts.nonemptyBooks += Number(!!bid || !!ask); counts.bothSides += Number(!!bid && !!ask); counts.crossed += Number(!!bid && !!ask && bid.price >= ask.price);
        fs.writeSync(fd, JSON.stringify({ asset, ticker: market.ticker, requestedAt: reply.requestedAt, knownAt: reply.knownAt,
          rawSha256: reply.rawSha256, raw: reply.data, ...book }) + '\n');
      }
      if (cycle % 12 === 0) console.log(`Public capture ${cycle + 1}/${o.cycles}: ${counts.books} books, ${counts.nonemptyBooks} with depth`);
      if (cycle + 1 < o.cycles) await wait(Math.max(0, intervalMs - (now() - cycleAt)));
    } } finally { fs.closeSync(fd); fs.closeSync(marketsFd); }
    await unchanged({}, code);
    const report = { ...registration, endedAt: now(), counts, status: counts.nonemptyBooks ? 'observed-public-depth' : 'no-observed-depth',
      booksSha256: await sha256File(path.join(dir, 'books.jsonl')), marketsSha256: await sha256File(path.join(dir, 'markets.jsonl')),
      actualProfitVerified: false, liveEntryAllowed: false, limitations: ['Polled public books, not private fills or a sequenced websocket replay',
        'No forecasts or targets were scored; captured final-period data remains excluded from iterative fitting', 'No underlying OHLC history acquired; new historical OHLC acquisition remains tvdatafeed-only'] };
    fs.writeFileSync(path.join(dir, 'report.json'), JSON.stringify(report, null, 2) + '\n'); return report;
  });
}
const arg = (name: string, fallback: string) => { const i = process.argv.indexOf(`--${name}`); return i < 0 ? fallback : process.argv[i + 1]; };
if (process.argv[1] && /(^|[/\\])collectContractBooks\.(ts|js)$/.test(process.argv[1])) void collectContractBooks({
  out: arg('out', 'research/out/atlas-forward-contract-books'), cycles: Number(arg('cycles', '192')) })
  .then((r) => console.log(JSON.stringify(r.counts))).catch((e) => { console.error(e instanceof Error ? e.stack : e); process.exitCode = 1; });
