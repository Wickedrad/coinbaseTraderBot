/** Heat-map live shadow capture. Research only: a GitHub runner, public data, no orders, no account, no server.
 *
 *  Every closed Binance minute the frozen Atlas tables (the weighted heat maps) give each coin a 15-minute and a
 *  60-minute call. Alongside, the public Kalshi books of the coin's current 15-minute contract and of the hourly
 *  strikes nearest the money are sampled about every 10 seconds. Only the calls and the books are written here;
 *  shadow entries and their scores are derived afterwards by the scorer, under the rules fixed in PREREG.md. */
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { parseMarket, parseOrderbook } from '../../bot/kalshi/wire';
import type { MarketInfo } from '../../bot/kalshi/types';
import { readSeries, seriesPath } from '../../bot/marketdata/historyStore';
import { acquireAtlasTv } from '../opportunity/tvHistory';
import { CompletedDailyIndex } from '../opportunity/train';
import { OracleFeatures, ORACLE_HORIZONS } from '../opportunity/oracleMatrix';
import { loadEdgeOracle } from '../opportunity/oracleEdge';
import type { MinuteCandle } from '../opportunity/atlas';

export const MIN = 60_000, DAY = 86_400_000;
export const CAPTURE = Object.freeze({
  assets: ['BTC', 'ETH', 'SOL', 'XRP'], warmDays: 100, maxFillMinutes: 180, pollMs: 10_000, hourlyStrikes: 4,
  /** Segments end a few minutes before these UTC boundaries so one is always uploaded before 14:30 UTC (9:30 AM EST). */
  segmentHours: 3, segmentAnchorMinute: 14 * 60 + 25, minSegmentMinutes: 20, kalshiSpacingMs: 125,
  kalshi: ['https://api.elections.kalshi.com/trade-api/v2', 'https://external-api.kalshi.com/trade-api/v2'],
  binance: 'https://data-api.binance.vision/api/v3',
});

/** The next segment end: the next UTC time-of-day on the 3-hour grid through 14:25 that is at least 20 minutes away. */
export function segmentEnd(now: number, hours: number = CAPTURE.segmentHours, anchorMinute: number = CAPTURE.segmentAnchorMinute, minMinutes: number = CAPTURE.minSegmentMinutes): number {
  const step = hours * 60 * MIN, anchor = anchorMinute * MIN;
  let end = Math.floor((now - anchor) / step) * step + anchor;
  while (end - now < minMinutes * MIN) end += step;
  return end;
}

/** Feed minutes in order, filling a short hole with flat zero-volume bars so one missing minute does not wipe
 *  the long indicators; a longer hole passes through and resets them (as in training). */
export class MinuteStream {
  last?: MinuteCandle; filled = 0; breaks = 0;
  constructor(private readonly maxFill: number = CAPTURE.maxFillMinutes) {}
  /** Returns the bars to push for one new bar (the fills, then the bar), or [] when it is not newer. */
  next(b: MinuteCandle): MinuteCandle[] {
    if (this.last && b.ts <= this.last.ts) return [];
    const out: MinuteCandle[] = [];
    if (this.last && b.ts > this.last.ts + MIN) {
      const missing = (b.ts - this.last.ts) / MIN - 1;
      if (Number.isInteger(missing) && missing <= this.maxFill) {
        for (let t = this.last.ts + MIN; t < b.ts; t += MIN) out.push({ ts: t, o: this.last.c, h: this.last.c, l: this.last.c, c: this.last.c, v: 0 });
        this.filled += missing;
      } else this.breaks++;
    }
    out.push(b); this.last = b; return out;
  }
}

/** The hourly strikes to watch: nearest a 50c YES mid when the listing is two-sided, else nearest the coin price. */
export function pickHourly(markets: MarketInfo[], anchor: number | undefined, n: number = CAPTURE.hourlyStrikes): MarketInfo[] {
  const mid = (m: MarketInfo) => m.yesBid !== undefined && m.yesAsk !== undefined && m.yesBid > 0 && m.yesAsk < 1 && m.yesAsk > m.yesBid ? (m.yesBid + m.yesAsk) / 2 : undefined;
  const rows = markets.filter((m) => m.floorStrike !== undefined && m.strikeType !== 'between' && /-T/.test(m.ticker));
  const key = (m: MarketInfo): [number, number] => { const x = mid(m); return x !== undefined ? [0, Math.abs(x - 0.5)] : [1, anchor ? Math.abs(m.floorStrike! - anchor) / anchor : Infinity]; };
  return rows.map((m) => ({ m, k: key(m) })).sort((a, b) => a.k[0] - b.k[0] || a.k[1] - b.k[1] || a.m.ticker.localeCompare(b.m.ticker)).slice(0, n).map((r) => r.m);
}

type Level = [number, number];
/** Top levels on the YES book: bids high to low, asks low to high (an ask is 1 minus a NO bid). */
export function compactBook(book: { bids: Array<{ price: number; size: number }>; asks: Array<{ price: number; size: number }> }, depth = 3): { yb: Level[]; ya: Level[] } {
  const row = (l: { price: number; size: number }): Level => [Math.round(l.price * 10000) / 10000, Math.round(l.size * 100) / 100];
  return { yb: book.bids.slice(0, depth).map(row), ya: book.asks.slice(0, depth).map(row) };
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, Math.max(0, ms)));
const sha = (s: string | Buffer) => createHash('sha256').update(s).digest('hex');

interface Tracked { ticker: string; asset: string; kind: '15m' | 'hourly'; series: string; openTime: number; closeTime: number; floorStrike?: number }

export async function runCapture(o: { models: string; weights: string; out: string; segment: string; python?: string; untilMs?: number; assets?: string[] }) {
  const assets = o.assets ?? [...CAPTURE.assets], root = path.resolve(o.out);
  fs.mkdirSync(root, { recursive: true });
  const startedAt = Date.now(), stopAt = o.untilMs ?? segmentEnd(startedAt);
  const fds = Object.fromEntries(['forecasts', 'books', 'markets', 'events'].map((n) => [n, fs.openSync(path.join(root, `${n}.jsonl`), 'a')]));
  const append = (name: string, v: unknown, sync = false) => { fs.writeSync(fds[name], JSON.stringify(v) + '\n'); if (sync) fs.fsyncSync(fds[name]); };
  const counts = { forecasts: 0, minutes: 0, minutesNoBar: 0, staleSkips: 0, books: 0, twoSided: 0, emptyBooks: 0, requests: 0, failures: 0, limited: 0, listings: 0, listingFailures: 0,
    klineFailures: 0, forecastErrors: 0, pollErrors: 0, dominanceOk: 0, dominanceFailures: 0, tickers: 0, pollRounds: 0, slowRounds: 0 };
  const event = (kind: string, data: Record<string, unknown> = {}) => { append('events', { at: Date.now(), kind, ...data }); console.log(`CAPTURE_${kind.toUpperCase()} ${JSON.stringify(data)}`); };

  // ---- frozen tables (identity and hashes are checked by the loader) ----
  const models = new Map<string, Awaited<ReturnType<typeof loadEdgeOracle>>>();
  for (const a of assets) models.set(a, await loadEdgeOracle(path.join(o.models, `atlas-oracle-result-${a}/walk/model.json`), path.join(o.weights, `atlas-oracle-importance-${a}/importance.json`)));

  // ---- public GETs ----
  let pause = 0, kalshiHost = 0;
  async function getJson(url: string, timeout = 12_000): Promise<{ status: number; data?: any }> {
    counts.requests++;
    try {
      const r = await fetch(url, { headers: { Accept: 'application/json', 'User-Agent': 'research-capture' }, redirect: 'error', signal: AbortSignal.timeout(timeout) });
      if (r.status === 429) { counts.limited++; const ra = Number(r.headers.get('retry-after')); pause = Date.now() + Math.min(30_000, Number.isFinite(ra) && ra > 0 ? ra * 1000 : 2000); return { status: 429 }; }
      if (!r.ok) { counts.failures++; return { status: r.status }; }
      return { status: 200, data: await r.json() };
    } catch { counts.failures++; return { status: -1 }; }
  }
  let slot = 0;
  async function kalshi(route: string) {
    // At most 8 public requests a second, whatever the number of workers (the 6-minute trial drew a few 429s without this).
    slot = Math.max(Date.now(), slot, pause) + CAPTURE.kalshiSpacingMs; await sleep(slot - CAPTURE.kalshiSpacingMs - Date.now());
    const r = await getJson(CAPTURE.kalshi[kalshiHost] + route);
    if (r.status === 200 || r.status === 429 || r.status === 404) return r;
    kalshiHost = (kalshiHost + 1) % CAPTURE.kalshi.length; // one retry on the other public host
    return getJson(CAPTURE.kalshi[kalshiHost] + route);
  }

  // ---- Binance minutes (the training source), clock offset measured once ----
  let clockOffset = 0;
  { const t0 = Date.now(), r = await getJson(`${CAPTURE.binance}/time`); if (r.data?.serverTime) clockOffset = Number(r.data.serverTime) - (t0 + Date.now()) / 2; }
  async function klines(asset: string, from: number): Promise<MinuteCandle[] | null> {
    const r = await getJson(`${CAPTURE.binance}/klines?symbol=${asset}USDT&interval=1m&limit=1000&startTime=${from}`, 20_000);
    if (r.status !== 200 || !Array.isArray(r.data)) { counts.klineFailures++; return null; }
    const now = Date.now() + clockOffset - 500;
    return r.data.map((k: any[]) => ({ ts: Number(k[0]), o: Number(k[1]), h: Number(k[2]), l: Number(k[3]), c: Number(k[4]), v: Number(k[5]) }))
      .filter((b: MinuteCandle) => Number.isFinite(b.ts) && b.ts % MIN === 0 && b.c > 0 && b.ts + MIN <= now);
  }
  const features = new Map(assets.map((a) => [a, new OracleFeatures()])), streams = new Map(assets.map((a) => [a, new MinuteStream()]));
  const latest = new Map<string, { at: number; raw: number[]; atrBps: number; close: number }>();
  let dominance: [CompletedDailyIndex, CompletedDailyIndex] | undefined, dominanceTriedAt = 0;
  const dom = (t: number): [number, number] => dominance ? [dominance[0].changeAt(t - DAY), dominance[1].changeAt(t - DAY)] : [NaN, NaN];
  function push(asset: string, bars: MinuteCandle[]) {
    const f = features.get(asset)!, s = streams.get(asset)!;
    for (const raw of bars) for (const b of s.next(raw)) {
      const u = f.push(b, dom(b.ts + MIN));
      latest.set(asset, { at: u.at, raw: u.raw, atrBps: u.atrBps, close: b.c });
    }
  }
  async function refreshDominance() {
    dominanceTriedAt = Date.now();
    try {
      const dir = path.join(root, 'tv-history');
      await acquireAtlasTv({ out: dir, assets: [assets[0]], exchange: 'BINANCE', quote: 'USDT', bars: 40, python: o.python });
      const idx = ['BTC.D', 'USDT.D'].map((a) => new CompletedDailyIndex(readSeries(seriesPath(dir, 'tradingview', a, '1d')))) as [CompletedDailyIndex, CompletedDailyIndex];
      if (!idx.every((d) => Number.isFinite(d.changeAt(Date.now() - DAY)))) throw new Error('dominance change not available');
      dominance = idx; counts.dominanceOk++;
    } catch (e) { counts.dominanceFailures++; event('dominance_failed', { error: String(e).slice(0, 200) }); }
  }

  await refreshDominance();
  // Warm-up: 100 days of minutes per coin, so every reading (through the daily bars) is defined as in training.
  const warmFrom = Math.floor(startedAt / DAY) * DAY - CAPTURE.warmDays * DAY;
  await Promise.all(assets.map(async (a) => {
    let from = warmFrom, tries = 0;
    while (from + 2 * MIN <= Date.now()) {
      const rows = await klines(a, from);
      if (!rows) { if (++tries > 8) break; await sleep(1500 * tries); continue; }
      tries = 0; if (!rows.length) break;
      push(a, rows); from = rows.at(-1)!.ts + MIN;
    }
  }));
  event('warm', { ms: Date.now() - startedAt, clockOffset: Math.round(clockOffset), stopAt, dominance: !!dominance,
    coins: assets.map((a) => ({ a, last: streams.get(a)!.last?.ts, filled: streams.get(a)!.filled, breaks: streams.get(a)!.breaks, axes: latest.get(a)?.raw.filter(Number.isFinite).length })) });

  // ---- Kalshi listings ----
  const tracked = new Map<string, Tracked>();
  async function listing(series: string, horizonMs: number): Promise<MarketInfo[] | null> {
    const now = Date.now(), rows = new Map<string, MarketInfo>(); let cursor = '';
    for (let page = 0; page < 10; page++) {
      const r = await kalshi(`/markets?series_ticker=${series}&status=open&limit=200&min_close_ts=${Math.floor(now / 1000)}&max_close_ts=${Math.floor((now + horizonMs) / 1000)}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`);
      if (r.status !== 200 || !Array.isArray(r.data?.markets)) return null;
      for (const raw of r.data.markets) { const m = parseMarket(raw); if (m && m.closeTime > now && m.openTime <= now) rows.set(m.ticker, m); }
      cursor = r.data.cursor ? String(r.data.cursor) : ''; if (!cursor) return [...rows.values()];
    }
    return null;
  }
  function track(m: MarketInfo, asset: string, kind: '15m' | 'hourly', series: string) {
    if (tracked.has(m.ticker)) return;
    const t: Tracked = { ticker: m.ticker, asset, kind, series, openTime: m.openTime, closeTime: m.closeTime, floorStrike: m.floorStrike };
    tracked.set(m.ticker, t); counts.tickers++;
    append('markets', { at: Date.now(), ...t, strikeType: m.strikeType, tickSize: m.tickSize, priceRanges: m.priceRanges });
  }
  async function refreshListings() {
    await Promise.all(assets.map(async (a) => {
      const s15 = `KX${a}15M`, sh = `KX${a}D`;
      const [m15, mh] = await Promise.all([listing(s15, 16 * MIN), listing(sh, 61 * MIN)]);
      counts.listings += 2; counts.listingFailures += Number(!m15) + Number(!mh);
      // The 15-minute market: the one closing soonest.
      for (const m of (m15 ?? []).sort((x, y) => x.closeTime - y.closeTime).slice(0, 1)) track(m, a, '15m', s15);
      // The hourly event closing soonest; its strikes nearest the money. A strike once chosen is kept to its close.
      const close = Math.min(...(mh ?? []).map((m) => m.closeTime));
      for (const m of pickHourly((mh ?? []).filter((m) => m.closeTime === close), latest.get(a)?.close)) track(m, a, 'hourly', sh);
    }));
  }

  // ---- fees as published (recorded once per segment for the scorer) ----
  const fees: Record<string, unknown> = {};
  for (const a of assets) for (const s of [`KX${a}15M`, `KX${a}D`]) { const r = await kalshi(`/series/${s}`); fees[s] = r.data?.series ? { fee_type: r.data.series.fee_type, fee_multiplier: r.data.series.fee_multiplier } : null; }
  const meta = { schema: 'heat-shadow-capture-v1', segment: o.segment, startedAt, stopAt, assets, capture: CAPTURE, clockOffset,
    models: [...models].map(([asset, m]) => ({ asset, id: m.modelId, model: m.modelHash, importance: m.importanceHash, learnedThrough: m.learnedThrough })),
    minuteSource: 'binance-data-api-klines-1m (the tables were built on Binance minutes)', dominanceSource: 'tradingview CRYPTOCAP daily via tvdatafeed',
    fees, commit: process.env.GITHUB_SHA ?? null, run: process.env.GITHUB_RUN_ID ?? null,
    code: fs.existsSync('research/heatmap_live/captureCli.ts') ? sha(fs.readFileSync('research/heatmap_live/captureCli.ts')) : null };
  fs.writeFileSync(path.join(root, 'meta.json'), JSON.stringify(meta, null, 2) + '\n');

  // ---- the minute: new bars, calls, listings ----
  async function minuteWork(minute: number) {
    counts.minutes++;
    if (!dominance && Date.now() - dominanceTriedAt > 30 * MIN) await refreshDominance();
    await Promise.all(assets.map(async (a) => { try {
      for (let attempt = 0; attempt < 4; attempt++) {
        const rows = await klines(a, (streams.get(a)!.last?.ts ?? minute - 10 * MIN) + MIN);
        if (rows?.length) push(a, rows);
        if (streams.get(a)!.last?.ts === minute - MIN) break;
        await sleep(800);
      }
      const l = latest.get(a), publishedAt = Date.now();
      if (!l || l.at !== minute) { counts.minutesNoBar++; return; }
      if (!(l.atrBps > 0) || publishedAt - l.at > 110_000) { counts.staleSkips++; return; }
      for (const horizon of ORACLE_HORIZONS) {
        const f = models.get(a)!.forecast({ raw: l.raw, featureAt: l.at, knownAt: publishedAt, publishedAt, anchor: l.close, atrBps: l.atrBps, horizon });
        append('forecasts', { id: f.id, asset: a, horizon, featureAt: f.featureAt, publishedAt, anchor: f.anchor, atrBps: f.atrBps, p: f.p, uniform: f.uniform, prior: f.prior,
          axes: f.availableAxes.length, curves: f.activeCurves, filled: streams.get(a)!.filled, breaks: streams.get(a)!.breaks }, true);
        counts.forecasts++;
      }
    } catch (e) { counts.forecastErrors++; event('forecast_error', { a, error: String(e).slice(0, 200) }); } }));
    try { await refreshListings(); } catch (e) { counts.listingFailures++; event('listing_error', { error: String(e).slice(0, 200) }); }
  }

  // ---- books ----
  async function pollBooks() {
    const now = Date.now(), live = [...tracked.values()].filter((t) => t.closeTime > now);
    for (const t of tracked.values()) if (t.closeTime <= now - MIN) tracked.delete(t.ticker);
    let i = 0;
    await Promise.all(Array.from({ length: Math.min(4, live.length) }, async () => {
      while (i < live.length) {
        const t = live[i++], at = Date.now();
        const r = await kalshi(`/markets/${encodeURIComponent(t.ticker)}/orderbook?depth=10`);
        if (r.status !== 200) continue;
        const b = compactBook(parseOrderbook(r.data));
        counts.books++; counts.twoSided += Number(b.yb.length > 0 && b.ya.length > 0); counts.emptyBooks += Number(!b.yb.length && !b.ya.length);
        append('books', { t: at, k: Date.now(), x: t.ticker, yb: b.yb, ya: b.ya });
      }
    }));
    counts.pollRounds++;
  }

  let lastMinute = 0, nextPoll = Date.now(), lastProgress = Date.now();
  try {
    try { await refreshListings(); } catch (e) { counts.listingFailures++; }
    while (Date.now() < stopAt) {
      const now = Date.now(), minute = Math.floor(now / MIN) * MIN;
      if (minute > lastMinute && now - minute >= 2500) { lastMinute = minute; await minuteWork(minute); }
      try { await pollBooks(); } catch (e) { counts.pollErrors++; event('poll_error', { error: String(e).slice(0, 200) }); }
      nextPoll += CAPTURE.pollMs;
      if (nextPoll < Date.now()) { counts.slowRounds++; nextPoll = Date.now(); }
      if (Date.now() - lastProgress > 15 * MIN) { lastProgress = Date.now(); event('progress', { counts, tracked: tracked.size }); fs.writeFileSync(path.join(root, 'summary.json'), JSON.stringify({ at: Date.now(), counts }, null, 2) + '\n'); }
      await sleep(Math.min(nextPoll, stopAt) - Date.now());
    }
  } finally {
    const summary = { ...meta, endedAt: Date.now(), counts, coins: assets.map((a) => ({ a, filled: streams.get(a)!.filled, breaks: streams.get(a)!.breaks })) };
    fs.writeFileSync(path.join(root, 'summary.json'), JSON.stringify(summary, null, 2) + '\n');
    for (const fd of Object.values(fds)) fs.closeSync(fd);
    console.log(`CAPTURE_DONE ${JSON.stringify(counts)}`);
  }
  return counts;
}

const arg = (name: string, fallback = '') => { const i = process.argv.indexOf(`--${name}`); return i < 0 ? fallback : process.argv[i + 1]; };
if (process.argv[1] && /(^|[/\\])captureCli\.(ts|js)$/.test(process.argv[1])) {
  void runCapture({ models: arg('models'), weights: arg('weights'), out: arg('out'), segment: arg('segment', '0'), python: arg('python', 'python3'),
    untilMs: arg('minutes') ? Date.now() + Number(arg('minutes')) * MIN : undefined })
    .catch((e) => { console.error(e instanceof Error ? e.stack : e); process.exitCode = 1; });
}
