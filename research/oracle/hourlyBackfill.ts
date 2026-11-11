// Oracle setups, hourly-ladder backfill (python/oracle/SPEC.md 2d; prereg python/oracle/prereg/OR-H1.md "Data", Price
// Prediction hourly: "KX{BTC,ETH,SOL}D settled markets backfilled from Kalshi's public API on a runner, Apr 13 - Nov 4
// 2026, the 4 strikes nearest spot at the window's open (the live catalog rule). No XRP hourly series exists.").
//
// Per series KX<A>D, A in BTC / ETH / SOL (DOGE is never used and XRP has no hourly series: both are refused):
//  1. List the settled markets closing in [from, to) from both of Kalshi's tiers (GET /markets?status=settled and
//     GET /historical/markets, cursor pages, public endpoints, no key). Every request of the run shares one pace
//     (research/history/kalshiHistory.ts getter: 10 a second, a 429 pauses every worker). The close-time range goes to
//     the API as min_close_ts / max_close_ts (live tier: then a settle-time range); if the API refuses a query form
//     (HTTP 400 on its first page), the next simpler form is used, down to the plain listing kalshiHistory.ts uses. Rows
//     are also filtered on their close time here. Listings are newest first. If a listing stops early (budget, page
//     cap, error), only events strictly newer than the oldest close it reached are complete and selected; the others
//     wait for the next run.
//  2. Group the markets by event and close time (one hourly close per event). Keep the greater-than ladder only:
//     strike_type 'greater' / 'greater_or_equal' with a floor_strike and no positive cap. A range bucket (-B<centre>,
//     'between') or a 'less' market is dropped. load_kalshi takes `strike` = floor_strike and settle = (result == 'yes'), which
//     reads as "YES = the index settles above the strike". That is only true of this ladder.
//  3. In each event, keep the n = 4 strikes nearest the Binance spot close at the window's open (close - 60 min). That is
//     the close of the 1-minute bar ENDING at that instant: perpta1 grid column 'sc', bar m opens at t0 + m min. This is
//     the live catalog's index rule, bot/marketdata/marketData.ts nearestStrikes called without Kalshi quotes, which
//     are not known before the candles are fetched.
//  4. Fetch the 1-minute candles of each kept market's last 70 minutes in one request to the market's tier, trying the
//     other tier on a 404. Append one kalshiHistory.ts line per market to <out>/<SERIES>/<UTC close day>.jsonl, with an
//     extra `pick: {spot, rank, strikes}` (the reference close, 0 = nearest, the ladder's size).
//     python/allpairs/data.py load_kalshi(<out>/.., [A], n=60, series_fmt='KX{asset}D') reads these lines.
// The run can resume. Markets already stored are skipped (kalshiHistory.ts storedMarkets / .index.json). A market that
// never traded is fetched like any other (counted as noVolume): its lifetime volume is known only after it settled, so
// skipping it would select strikes on future information (review fix, Nov 6; a line stored without candles as noVolume
// by an earlier run is fetched again). A market the API rejects for good (400, or 404 on both tiers) is stored
// with its error. --budget-min stops new requests and the rest waits for the next run. The series index's `listed`
// range is never set, because only 4 strikes per event are stored: a later full kalshiHistory download of the same
// folder still lists everything.
// Nothing at or after 2026-11-05T00:00Z is listed, fetched or read: --to is capped there, and a grid that runs past it
// is refused. Logs carry counts only. NEVER DOGE.
//
//   node --import tsx research/oracle/hourlyBackfill.ts --grid 'data/grids/{A}.bin' --out data/history/kalshi \
//     [--assets BTC,ETH,SOL] [--from 2026-04-13] [--to 2026-11-05] [--budget-min 300] [--concurrency 3] [--rate 10] \
//     [--strikes 4] [--candle-min 70] [--max-markets N] [--list-only] [--base-url URL]
// --grid takes a path with {A} or <A> in it, a directory that holds <A>.bin, or one file (one asset only).

import fs from 'fs';
import path from 'path';
import { getter, parseCandle, parseHistMarket, storedMarkets, type KalshiCandle, type KalshiHistMarket } from '../history/kalshiHistory';
import { readGrid } from '../perpTaSweep';
import { nearestStrikes } from '../../bot/marketdata/marketData';
import { contractKind, isRangeTicker } from '../../bot/model/fairValue';
import { progress } from '../progress';

const MIN = 60_000;
/** The only assets with an hourly ladder this study uses (prereg "Data"). */
export const HOURLY_ASSETS = ['BTC', 'ETH', 'SOL'] as const;
export const DEFAULT_FROM = Date.UTC(2026, 3, 13);
/** Exclusive end of everything this study may read: HO-1 ends Nov 4 23:59 UTC, Nov 5 is embargo, the lockbox follows. */
export const HARD_TO = Date.UTC(2026, 10, 5);

/** A listed market without its candles (research/history/kalshiHistory.ts parseHistMarket). */
type Listed = Omit<KalshiHistMarket, 'candles'>;
/** A stored line: kalshiHistory.ts's format plus how the strike was picked. */
export type HourlyMarket = Listed & { pick?: { spot: number; rank: number; strikes: number }; candles: KalshiCandle[]; noVolume?: boolean; error?: string };

export interface HourlyBackfillOpts {
  out: string;
  /** Grid per asset: a path with {A} or <A>, a directory holding <A>.bin, one file (one asset only), or a function. */
  grid: string | ((asset: string) => string);
  assets?: string[];
  /** Close times in [from, to) (UTC ms); to is capped at HARD_TO. */
  from?: number; to?: number;
  baseUrl?: string; fetchImpl?: typeof fetch; log?: (m: string) => void;
  /** Stop starting requests after this long (wall clock); the rest is fetched by the next run. */
  budgetMs?: number;
  concurrency?: number;
  /** Requests a second, shared by every request of the run (default 10). */
  ratePerSec?: number;
  clock?: () => number;
  /** Strikes kept per event (default 4). */
  strikes?: number;
  /** 1-minute candles for this many minutes before the close (default 70). */
  candleMinutes?: number;
  /** Candle requests at most, over the whole run (a probe). */
  maxMarkets?: number;
  /** List and select only: nothing is fetched or written. */
  listOnly?: boolean;
  /** Markets per listing page (default 200, as kalshiHistory.ts) and pages per tier at most. */
  pageLimit?: number; maxPages?: number;
}

export interface SeriesStats {
  /** Settled markets listed with a close in [from, to), both tiers, deduplicated. */
  listed: number;
  /** Rows on the pages read whose close falls outside [from, to) (discarded unread). */
  outside: number;
  events: number;
  /** Events at or before where an incomplete listing stopped: left for the next run. */
  deferred: number;
  /** Events without a spot close at the window's open (outside the grid). */
  noSpot: number;
  /** Markets that are not on the greater-than ladder (range buckets, 'less', no floor strike). */
  notLadder: number;
  /** Strikes picked (n nearest per event). */
  kept: number;
  skipped: number; noVolume: number; markets: number; rejected: number; failed: number; remaining: number;
  /** How each tier was listed: pages and the query form. */
  tiers: { live: string; historical: string };
}

export interface HourlyBackfillResult {
  series: Record<string, SeriesStats>;
  markets: number; skipped: number; noVolume: number; rejected: number; failed: number; remaining: number; deferred: number; budgetHit: boolean;
}

/** KX<A>D for each asset; DOGE and XRP refused (and anything else that has no hourly ladder in this study). */
export function hourlySeries(assets: readonly string[]): string[] {
  const out: string[] = [];
  for (const raw of assets) {
    const a = String(raw).trim().toUpperCase();
    if (!a) continue;
    if (a.includes('DOGE')) throw new Error('DOGE is never used (Steven, 2026-11-05)');
    if (a === 'XRP') throw new Error('no XRP hourly series exists (no KXXRPD ladder): XRP refused');
    if (!(HOURLY_ASSETS as readonly string[]).includes(a)) throw new Error(`${a}: not an hourly-ladder asset of this study (${HOURLY_ASSETS.join(', ')})`);
    if (!out.includes(`KX${a}D`)) out.push(`KX${a}D`);
  }
  if (!out.length) throw new Error('no assets');
  return out;
}

/** The greater-than ladder: YES iff the index settles above floor_strike (what load_kalshi assumes of `strike`). */
export function isLadder(m: Pick<Listed, 'ticker' | 'series' | 'strike' | 'cap' | 'strikeType'>): boolean {
  const st = (m.strikeType ?? 'greater').toLowerCase();
  return (st === 'greater' || st === 'greater_or_equal') && contractKind(m.series, m.strikeType, m.ticker) === 'greater' && !isRangeTicker(m.ticker)
    && !(typeof m.cap === 'number' && m.cap > 0) && typeof m.strike === 'number' && Number.isFinite(m.strike) && m.strike > 0;
}

/** The n ladder strikes nearest the spot price (the live catalog's index rule, nearestStrikes without quotes), nearest
 *  first; a tie goes to the lower strike. */
export function pickNearest<T extends { m: Listed }>(ladder: T[], series: string, spot: number, n: number): T[] {
  const byStrike = [...ladder].sort((a, b) => a.m.strike! - b.m.strike! || (a.m.ticker < b.m.ticker ? -1 : a.m.ticker > b.m.ticker ? 1 : 0));
  const cands = byStrike.map((x) => ({ ticker: x.m.ticker, eventTicker: 'event', strikeType: x.m.strikeType, floorStrike: x.m.strike!, x }));
  const kept = nearestStrikes(cands, (s, st) => contractKind(s, st), series, spot, n, new Set());
  return kept.map((c) => c.x).sort((a, b) => Math.abs(a.m.strike! - spot) - Math.abs(b.m.strike! - spot) || a.m.strike! - b.m.strike!);
}

/** Event of a market: its event ticker (else the ticker without its last part) and its close time. */
function eventKey(m: Listed): string {
  const parts = m.ticker.split('-');
  return `${m.event ?? (parts.length >= 3 ? parts.slice(0, -1).join('-') : m.series)}|${m.closeTime}`;
}

function gridFileOf(spec: HourlyBackfillOpts['grid'], asset: string, nAssets: number): string {
  if (typeof spec === 'function') return spec(asset);
  if (/\{A\}|<A>/.test(spec)) return spec.replace(/\{A\}|<A>/g, asset);
  if (fs.existsSync(spec) && fs.statSync(spec).isDirectory()) return path.join(spec, `${asset}.bin`);
  if (nAssets > 1) throw new Error(`--grid ${spec}: one file for ${nAssets} assets (use a path with {A}, or a directory)`);
  return spec;
}

/** The Binance spot close of the 1-minute bar ending at or before t, from a perpta1 grid (research/perpTaSweep.ts
 *  readGrid). A grid that runs past HARD_TO is refused unread (its header says so). */
export function spotCloser(file: string, asset: string): { at: (t: number) => number | undefined; t0: number; n: number } {
  checkGrid(file, asset);
  const g = readGrid(file);
  const sc = g.c.sc, t0 = g.t0, n = g.n;
  return {
    t0, n,
    at: (t: number) => {
      const m = Math.floor((t - t0) / MIN) - 1; // bar m closes at t0 + (m + 1) min <= t
      if (m < 0 || m >= n) return undefined;
      const v = sc[m];
      return Number.isFinite(v) && v > 0 ? v : undefined;
    },
  };
}

/** A grid's header: a perpta1 grid of this asset that ends by HARD_TO, or an error (nothing else is read). */
function checkGrid(file: string, asset: string): void {
  if (!fs.existsSync(file)) throw new Error(`${asset}: no grid at ${file}`);
  const fd = fs.openSync(file, 'r');
  const buf = Buffer.alloc(4096);
  const got = fs.readSync(fd, buf, 0, buf.length, 0);
  fs.closeSync(fd);
  const nl = buf.subarray(0, got).indexOf(10);
  const h = nl > 0 ? JSON.parse(buf.subarray(0, nl).toString('utf8')) as { schema?: string; asset?: string; t0: number; n: number } : undefined;
  if (h?.schema !== 'perpta1') throw new Error(`${file}: not a perpta1 grid`);
  if (h.asset !== asset) throw new Error(`${file}: a grid of ${h.asset}, not ${asset}`);
  if (h.t0 + h.n * MIN > HARD_TO) throw new Error(`${file}: the grid runs past 2026-11-05T00:00Z; refused (nothing at or after it is read)`);
}

/** A whole number >= 1, else the default (a NaN from a bad flag must not mean "all strikes" or "no workers"). */
const posInt = (v: number | undefined, d: number): number => (v !== undefined && Number.isFinite(v) && v >= 1 ? Math.floor(v) : d);
const statusOf = (e: unknown): number | undefined => { const s = (e as { status?: unknown } | null)?.status; return typeof s === 'number' ? s : undefined; };

interface TierListing { rows: Listed[]; outside: number; complete: boolean; oldest: number; pages: number; form: string }

/** Every settled market of one tier closing in [from, to): cursor pages, newest first. The query forms run from the
 *  most to the least filtered; a 400 on a form's first page moves to the next. */
async function listTier(get: (p: string) => Promise<any>, series: string, hist: boolean, from: number, to: number,
  o: { deadline: number; clock: () => number; pageLimit: number; maxPages: number; log: (m: string) => void }): Promise<TierListing> {
  // One second of slack at the start in case the API reads min_ as exclusive; rows are cut to [from, to) below anyway.
  const lo = Math.floor(from / 1000) - 1, hi = Math.ceil(to / 1000) - 1;
  const range = `&min_close_ts=${lo}&max_close_ts=${hi}`;
  // Kalshi documents close-time filters as compatible with status 'closed' or none, and settle-time filters with
  // 'settled': the forms below go from what we want to what is known to work (kalshiHistory.ts's plain listing).
  const forms = hist
    ? [{ q: range, name: 'close-range filter' }, { q: '', name: 'unfiltered' }]
    : [{ q: `&status=settled${range}`, name: 'settled + close-range filter' }, { q: range, name: 'close-range filter' },
      { q: `&status=settled&min_settled_ts=${lo}&max_settled_ts=${hi}`, name: 'settled + settle-range filter' }, { q: '&status=settled', name: 'settled, unfiltered' }];
  const base = `${hist ? '/historical/markets' : '/markets'}?series_ticker=${encodeURIComponent(series)}&limit=${o.pageLimit}`;
  const rows: Listed[] = [];
  let v = 0, cursor = '', pages = 0, outside = 0, oldest = Infinity, complete = false;
  while (pages < o.maxPages && o.clock() < o.deadline) {
    let d: any;
    try {
      d = await get(`${base}${forms[v].q}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`);
    } catch (e) {
      if (!pages && statusOf(e) === 400 && v + 1 < forms.length) { v++; continue; }
      o.log(`${series} ${hist ? 'historical' : 'live'} listing stopped after ${pages} page(s): ${statusOf(e) ? `HTTP ${statusOf(e)}` : 'network error'}`);
      break;
    }
    pages++;
    let older = false;
    for (const raw of d?.markets ?? []) {
      const m = parseHistMarket(raw, series);
      if (!m) continue;
      if (m.closeTime < oldest) oldest = m.closeTime;
      if (m.closeTime < from) { older = true; outside++; continue; }
      if (m.closeTime >= to) { outside++; continue; }
      rows.push(m);
    }
    cursor = d?.cursor ?? '';
    if (!cursor || older) { complete = true; break; }
  }
  return { rows, outside, complete, oldest, pages, form: forms[v].name };
}

export async function hourlyBackfill(o: HourlyBackfillOpts): Promise<HourlyBackfillResult> {
  const seriesList = hourlySeries(o.assets ?? [...HOURLY_ASSETS]);
  const from = o.from ?? DEFAULT_FROM, to = o.to ?? HARD_TO;
  if (!(Number.isFinite(from) && Number.isFinite(to) && from < to)) throw new Error('need from < to');
  if (to > HARD_TO) throw new Error('--to is at most 2026-11-05: nothing at or after 2026-11-05T00:00Z is read');
  const log = o.log ?? ((m: string) => console.log(`[hourly-backfill] ${m}`));
  const clock = o.clock ?? Date.now;
  const deadline = o.budgetMs && o.budgetMs > 0 ? clock() + o.budgetMs : Infinity;
  const concurrency = posInt(o.concurrency, 3), nStrikes = posInt(o.strikes, 4), candleMin = posInt(o.candleMinutes, 70);
  const listing = { deadline, clock, log, pageLimit: posInt(o.pageLimit, 200), maxPages: posInt(o.maxPages, 20_000) };
  // The grids are opened before any request, so a missing or wrong one costs nothing.
  const assetOf = (s: string) => s.slice(2, -1);
  const gridFiles = new Map(seriesList.map((s) => [s, gridFileOf(o.grid, assetOf(s), seriesList.length)] as const));
  for (const [s, f] of gridFiles) checkGrid(f, assetOf(s));
  const { get, limited } = getter(o.baseUrl, o.fetchImpl ?? fetch, o.ratePerSec && o.ratePerSec > 0 ? o.ratePerSec : 10);
  const cutoffRaw = await get('/historical/cutoff').catch(() => ({}));
  const cutoff = Date.parse(String(cutoffRaw?.market_settled_ts ?? '')) || 0;
  const day = (t: number) => new Date(t).toISOString().slice(0, 10);
  const res: HourlyBackfillResult = { series: {}, markets: 0, skipped: 0, noVolume: 0, rejected: 0, failed: 0, remaining: 0, deferred: 0, budgetHit: false };
  let fetched = 0;
  for (const series of seriesList) {
    if (clock() >= deadline) { res.budgetHit = true; log(`${series}: time budget used up; left for the next run`); continue; }
    const spot = spotCloser(gridFiles.get(series)!, assetOf(series));
    const dir = path.join(o.out, series);
    // A market stored without candles because it never traded (noVolume, before the review fix of Nov 6) is asked
    // again: whether a strike traded over its life is known only after it settled, so it must not decide the selection.
    const have = new Set(storedMarkets(dir).rows.filter((r) => r.error !== 'HTTP 404' && !r.noVolume).map((r) => r.ticker));
    const live = await listTier(get, series, false, from, to, listing);
    const hist = await listTier(get, series, true, from, to, listing);
    // Newest first: an incomplete listing has every market strictly newer than the oldest close it reached.
    const safeAfter = Math.max(live.complete ? -Infinity : live.oldest, hist.complete ? -Infinity : hist.oldest);
    const all = new Map<string, { m: Listed; hist: boolean }>();
    for (const m of live.rows) all.set(m.ticker, { m, hist: false });
    for (const m of hist.rows) all.set(m.ticker, { m: all.get(m.ticker)?.m ?? m, hist: true }); // the archive is its home
    const events = new Map<string, Array<{ m: Listed; hist: boolean }>>();
    for (const x of all.values()) { const k = eventKey(x.m); (events.get(k) ?? events.set(k, []).get(k)!).push(x); }
    const st: SeriesStats = {
      listed: all.size, outside: live.outside + hist.outside, events: events.size, deferred: 0, noSpot: 0, notLadder: 0, kept: 0,
      skipped: 0, noVolume: 0, markets: 0, rejected: 0, failed: 0, remaining: 0,
      tiers: { live: `${live.pages} page(s), ${live.form}${live.complete ? '' : ', incomplete'}`, historical: `${hist.pages} page(s), ${hist.form}${hist.complete ? '' : ', incomplete'}` },
    };
    res.series[series] = st;
    const store = (rec: HourlyMarket) => {
      fs.mkdirSync(dir, { recursive: true });
      fs.appendFileSync(path.join(dir, `${day(rec.closeTime)}.jsonl`), `${JSON.stringify(rec)}\n`);
      have.add(rec.ticker);
    };
    const todo: Array<{ rec: Omit<HourlyMarket, 'candles'>; hist: boolean }> = [];
    const ordered = [...events.values()].sort((a, b) => a[0].m.closeTime - b[0].m.closeTime || (eventKey(a[0].m) < eventKey(b[0].m) ? -1 : 1));
    for (const ms of ordered) {
      const close = ms[0].m.closeTime;
      if (close <= safeAfter) { st.deferred++; continue; }
      const ladder = ms.filter((x) => isLadder(x.m));
      st.notLadder += ms.length - ladder.length;
      if (!ladder.length) continue;
      const s0 = spot.at(close - 60 * MIN);
      if (s0 === undefined) { st.noSpot++; continue; }
      pickNearest(ladder, series, s0, nStrikes).forEach((x, rank) => {
        st.kept++;
        if (have.has(x.m.ticker)) { st.skipped++; return; }
        const rec = { ...x.m, pick: { spot: s0, rank, strikes: ladder.length } };
        // A strike that never traded is fetched like the others: its lifetime volume is known only after it settled
        // (kalshiHistory.ts skips such markets; here that would drop catalog strikes on future information). Its
        // candles still carry the book, and a minute without a two-sided book drops out causally in load_kalshi.
        if (x.m.volume === 0) st.noVolume++;
        todo.push({ rec, hist: x.hist });
      });
    }
    log(`${series}: ${st.listed} settled market(s) closing ${day(from)} .. ${day(to - 1)} (live: ${st.tiers.live}; historical: ${st.tiers.historical}; `
      + `historical cutoff ${cutoff ? day(cutoff) : 'unknown'}), ${st.events} event(s), ${st.deferred} deferred (listing incomplete), ${st.noSpot} without a spot close, `
      + `${st.notLadder} non-ladder market(s) dropped; ${st.kept} strike(s) kept (${nStrikes} nearest per event): ${st.skipped} already stored, ${todo.length} to fetch (${st.noVolume} of them never traded)`);
    const total = () => { for (const k of ['markets', 'skipped', 'noVolume', 'rejected', 'failed', 'remaining', 'deferred'] as const) res[k] += st[k]; };
    if (o.listOnly) { st.remaining = todo.length; total(); continue; }
    // Candles: the worker of kalshiHistory.ts downloadKalshiHistory (not exported), with the window cut to candleMin.
    const errors = new Map<string, number>();
    let next = 0;
    const worker = async () => {
      while (next < todo.length && clock() < deadline && !(o.maxMarkets && fetched >= o.maxMarkets)) {
        const { rec, hist: inHist } = todo[next++];
        fetched++;
        const start = Math.max(rec.openTime, rec.closeTime - candleMin * MIN);
        const q = `start_ts=${Math.floor(start / 1000)}&end_ts=${Math.ceil(rec.closeTime / 1000)}&period_interval=1`;
        const histPath = `/historical/markets/${encodeURIComponent(rec.ticker)}/candlesticks?${q}`;
        const livePath = `/series/${encodeURIComponent(series)}/markets/${encodeURIComponent(rec.ticker)}/candlesticks?${q}`;
        const first = inHist || (cutoff && rec.closeTime < cutoff) ? histPath : livePath;
        try {
          // A market near the cutoff can still sit in the other tier (the archive move lags it): a 404 tries the other.
          const d = await get(first).catch((e) => { if (statusOf(e) === 404) return get(first === histPath ? livePath : histPath); throw e; });
          const candles = (d?.candlesticks ?? []).map(parseCandle).filter((c: KalshiCandle | undefined): c is KalshiCandle => Boolean(c));
          store({ ...rec, candles });
          st.markets++;
        } catch (e) {
          const s = statusOf(e);
          // Rejected for good: remembered with its error, not asked again. Anything else is asked again next run.
          if (s === 400 || s === 404) { store({ ...rec, candles: [], error: s === 404 ? 'HTTP 404 (both tiers)' : `HTTP ${s}` }); st.rejected++; }
          else st.failed++;
          const k = s ? `HTTP ${s}` : 'network error';
          errors.set(k, (errors.get(k) ?? 0) + 1);
        }
        progress(`Kalshi ${series} hourly ladder`, next, todo.length);
      }
    };
    await Promise.all(Array.from({ length: concurrency }, worker));
    st.remaining = todo.length - next;
    if ((st.remaining > 0 || st.deferred > 0) && clock() >= deadline) res.budgetHit = true;
    if (fs.existsSync(dir)) storedMarkets(dir); // bring .index.json up to date (its `listed` range is left alone)
    log(`${series}: ${st.markets} fetched, ${st.rejected} rejected by the API, ${st.failed} failed${errors.size ? ` (${[...errors].map(([k, n]) => `${k} x${n}`).join(', ')})` : ''}`
      + `${st.remaining ? `, ${st.remaining} left for the next run${res.budgetHit ? ' (time budget used up)' : ''}` : ''}`);
    total();
  }
  log(`done: ${res.markets} new market(s) (${res.noVolume} never traded, fetched too), ${res.skipped} already stored, ${res.rejected} rejected, ${res.failed} failed`
    + `${res.remaining ? `, ${res.remaining} left for the next run` : ''}${res.deferred ? `, ${res.deferred} event(s) deferred` : ''}`
    + `${limited() ? `; Kalshi asked to slow down ${limited()} time(s) (paused and retried)` : ''}`);
  return res;
}

function arg(k: string, d?: string): string | undefined { const i = process.argv.indexOf(`--${k}`); return i >= 0 && process.argv[i + 1] !== undefined && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : d; }
const dayMs = (s: string): number => Date.parse(s.includes('T') ? (/[Zz]|[+-]\d\d:?\d\d$/.test(s) ? s : `${s}Z`) : `${s}T00:00:00Z`);

async function main(): Promise<void> {
  const r = await hourlyBackfill({
    assets: (arg('assets', HOURLY_ASSETS.join(',')) ?? '').split(',').map((s) => s.trim()).filter(Boolean),
    from: dayMs(arg('from', '2026-04-13')!), to: dayMs(arg('to', '2026-11-05')!),
    grid: arg('grid', 'data/grids/{A}.bin')!, out: arg('out', 'data/history/kalshi')!,
    baseUrl: arg('base-url'), // production public API by default; never a bot.env KALSHI_REST_URL (it may be the demo)
    budgetMs: Number(arg('budget-min', '0')) * 60_000 || undefined,
    concurrency: Number(arg('concurrency', '3')), ratePerSec: Number(arg('rate', '10')),
    strikes: Number(arg('strikes', '4')), candleMinutes: Number(arg('candle-min', '70')),
    maxMarkets: Number(arg('max-markets', '0')) || undefined, listOnly: process.argv.includes('--list-only'),
  });
  if (r.failed) console.log(`[hourly-backfill] ${r.failed} market(s) failed and are asked again by the next run`);
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) main().catch((e) => { console.error(`[hourly-backfill] ${e instanceof Error ? e.message : String(e)}`); process.exitCode = 1; });
