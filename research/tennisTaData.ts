// Tennis TA rulebook trial (thread "Build a profitable tennis TA rulebook", Steven 2026-11-05 16:16 UTC): the tennis
// contract history the sweep runs on, built on a GitHub runner (the cloud sessions cannot reach Kalshi).
//
//   series     Kalshi's Sports series whose title or ticker says tennis (what can be downloaded at all)
//   download   settled match markets with 1-minute candles and their full trade tapes, as far back as Kalshi keeps them
//              (research/history/kalshiHistory.ts: public endpoints, no key, 10 requests a second, resumable)
//   inventory  matches by month and series (markets, two-sided events, volume, trades, quoted spread) and by unit week
//              (Monday 05:00 UTC, the sweep's unit edges): two-sided events and how many have a published start time, the
//              table START_ERA_FROM (research/tennisTaSweep.ts) is read off
//   recorded   one recorded day (the bot's own md-DAY file: real books, real tape, live scores) cut to its tennis lines,
//              with 'beat' and 'ws_beat' lines that keep the feed's and the Kalshi socket's liveness, every silence of
//              either over 6 s exactly as long as in the source (contract C8, see recordedTennis); its stats row labels a
//              day before the Nov 10 03:44 UTC book fix (FULL_BOOK_FROM) as practice data (Amendment 4 item 9)
//
// Contract prices come from Kalshi, not from the Live Tennis API: that API serves live scores only (free tier 100 calls a
// day), so scores exist only where the bot recorded them.
//
//   node --import tsx research/tennisTaData.ts series
//   node --import tsx research/tennisTaData.ts download --series KXATPMATCH --days 900 --out data/tennis/kalshi --budget-min 300
//   node --import tsx research/tennisTaData.ts inventory --hist data/tennis/kalshi --series KXATPMATCH,KXWTAMATCH --out inv.json
//   node --import tsx research/tennisTaData.ts recorded --in rec/md-2026-10-25.jsonl.gz --out tennis-rec/md-2026-10-25.jsonl.gz
//   node --import tsx research/tennisTaData.ts cut-version        (the cut's version: a day cut by an older one is cut again)

import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import { downloadKalshiHistory, downloadKalshiTrades, getter } from './history/kalshiHistory';
import { recordingLines } from '../bot/marketdata/recordingFiles';
import { contractKind } from '../bot/model/fairValue';

const BASE = process.env.KALSHI_REST_URL ?? 'https://external-api.kalshi.com/trade-api/v2';
const arg = (k: string, d: string) => { const i = process.argv.indexOf(`--${k}`); return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : d; };
const list = (s: string) => s.split(',').map((x) => x.trim()).filter(Boolean);

/** Every Sports series that is about tennis (ticker or title), with its fee type. */
export async function tennisSeries(): Promise<Array<{ ticker: string; title: string; feeType?: string; feeMultiplier?: number; tags?: string[] }>> {
  const { get } = getter(BASE, fetch, 5);
  const out: Array<{ ticker: string; title: string; feeType?: string; feeMultiplier?: number; tags?: string[] }> = [];
  let cursor = '';
  for (let page = 0; page < 50; page++) {
    const d = await get(`/series?category=Sports${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`);
    for (const s of d.series ?? []) {
      const t = String(s.ticker ?? ''), title = String(s.title ?? '');
      const tags: string[] = Array.isArray(s.tags) ? s.tags.map(String) : [];
      if (/tennis|ATP|WTA|ITF|wimbledon|roland|us open|australian open/i.test(`${t} ${title} ${tags.join(' ')}`)) {
        out.push({ ticker: t, title, feeType: s.fee_type, feeMultiplier: s.fee_multiplier, tags });
      }
    }
    cursor = d.cursor ?? '';
    if (!cursor) break;
  }
  return out.sort((a, b) => a.ticker.localeCompare(b.ticker));
}

export interface MonthRow { month: string; series: string; markets: number; events: number; twoSided: number; volume: number; withTape: number; trades: number; noStart: number; medSpreadC: number | null; medTradesPerMarket: number | null }

const median = (xs: number[]) => { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; };
/** The median of a histogram of whole cents (index = cents), as median() would give on the expanded list. */
const histMedian = (h: number[]) => { const n = h.reduce((a, x) => a + x, 0); if (!n) return null; let c = 0; for (let i = 0; i < h.length; i++) { c += h[i]; if (c > Math.floor(n / 2)) return i; } return null; };

/** Each line of a JSON-lines file, parsed (torn lines skipped), read one file at a time. */
function eachLine(file: string, f: (r: any) => void): void {
  if (!fs.existsSync(file)) return;
  const text = fs.readFileSync(file, 'utf8');
  let start = 0;
  while (start < text.length) {
    let end = text.indexOf('\n', start);
    if (end === -1) end = text.length;
    if (end > start) { let r: any; try { r = JSON.parse(text.slice(start, end)); } catch { r = undefined; } if (r) f(r); }
    start = end + 1;
  }
}

const DAY_MS = 86_400_000;
const MIN_MS = 60_000;

/** The Monday 05:00 UTC at or before t: the sweep's unit edge (research/tennisTaSweep.ts mondayEdge; 00:00 EST). */
export function weekEdge(t: number): number {
  const d = new Date(t - 5 * 3_600_000);
  const midnight = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  return midnight - ((d.getUTCDay() + 6) % 7) * DAY_MS + 5 * 3_600_000;
}
/** The unit week of t, named by its Monday (the date of the Monday 05:00 UTC at or before t, as the unit ids W-<date>). */
export const weekOf = (t: number): string => new Date(weekEdge(t)).toISOString().slice(0, 10);

/** A downloaded market's published start (Kalshi's occurrence_datetime), if it has one. */
const publishedStart = (m: { startTime?: unknown }): number | undefined => (typeof m.startTime === 'number' && Number.isFinite(m.startTime) ? m.startTime : undefined);

/** The time the sweep keys a downloaded market's match by: its published start, else the time the history replay lists
 *  it (research/history/historyReplay.ts: 1 s before max(open, first candle - 30 min)), which the sim takes as the start of
 *  a match without one (research/tennisTaSim.ts MatchInfo.start). */
export function matchTime(m: { openTime: number; startTime?: number; candles: Array<{ ts: number }> }): number {
  return publishedStart(m) ?? Math.max(m.openTime, m.candles[0].ts - 30 * MIN_MS) - 1000;
}

/** One unit week of one series. An event is keyed to the week of its earliest published start, else of its earliest
 *  market's listing time (matchTime); its markets count in that week. withStart: two-sided events whose markets all have a
 *  published start (the start era needs one); noStart: markets without. */
export interface WeekRow { series: string; week: string; markets: number; events: number; twoSided: number; withStart: number; noStart: number }

export interface SeriesTotals { markets: number; events: number; noStart: number; first?: string; last?: string; startEraWeek?: string }

/** The first week from which every week with two-sided events has at least `minShare` of them with a published start
 *  (rows of one series or several, summed per week); undefined when the last such week falls short or there is none. */
export function startEraWeek(rows: WeekRow[], minShare = 0.95): string | undefined {
  const by = new Map<string, { two: number; start: number }>();
  for (const r of rows) { const w = by.get(r.week) ?? { two: 0, start: 0 }; w.two += r.twoSided; w.start += r.withStart; by.set(r.week, w); }
  const weeks = [...by].filter(([, w]) => w.two > 0).sort((x, y) => x[0].localeCompare(y[0]));
  let from: string | undefined;
  for (let i = weeks.length - 1; i >= 0 && weeks[i][1].start >= minShare * weeks[i][1].two; i--) from = weeks[i][0];
  return from;
}

/** Matches by month (UTC month of the match start, else the close) and by unit week (weekOf; see WeekRow), per series.
 *  Streams one close-day file (markets, then that day's trade tapes) at a time: a whole series' candles and tapes
 *  (KXATPMATCH alone is 10.5k markets and 35.5M trades) do not fit a runner's heap at once; across files only counters
 *  per month and per event are kept. noStart counts markets Kalshi gave no start time. Markets without candles are left
 *  out of both (the replay cannot play them). */
export function inventory(hist: string, series: string[]): { months: MonthRow[]; weeks: WeekRow[]; totals: Record<string, SeriesTotals> } {
  const months: MonthRow[] = [];
  const weeks: WeekRow[] = [];
  const totals: Record<string, SeriesTotals> = {};
  for (const s of series) {
    const dir = path.join(hist, s);
    const files = fs.existsSync(dir) ? fs.readdirSync(dir).filter((x) => x.endsWith('.jsonl')).sort() : [];
    type Acc = { markets: number; volume: number; withTape: number; trades: number; noStart: number; spreads: number[]; perMarket: number[]; events: Map<string, number> };
    const by = new Map<string, Acc>();
    const eventMonth = new Map<string, string>();
    // Per event (any file): markets, those with a published start, the earliest published start and listing time.
    type Ev = { n: number; nStart: number; pub: number; listed: number };
    const evs = new Map<string, Ev>();
    let first = Infinity, last = -Infinity, markets = 0, noStart = 0;
    for (const file of files) {
      const rows: Array<{ ticker: string; month: string }> = [];
      eachLine(path.join(dir, file), (m) => {
        if (!m.candles?.length) return;
        const t = m.startTime ?? m.closeTime;
        const month = new Date(t).toISOString().slice(0, 7);
        let acc = by.get(month);
        if (!acc) { acc = { markets: 0, volume: 0, withTape: 0, trades: 0, noStart: 0, spreads: new Array(101).fill(0), perMarket: [], events: new Map() }; by.set(month, acc); }
        acc.markets++; markets++;
        acc.volume += m.volume ?? 0;
        if (m.startTime === undefined || m.startTime === null) { acc.noStart++; noStart++; }
        const e = m.event ?? m.ticker;
        const em = eventMonth.get(e) ?? month;
        eventMonth.set(e, em);
        const ea = by.get(em) ?? acc;
        ea.events.set(e, (ea.events.get(e) ?? 0) + 1);
        for (const c of m.candles) if (c.bidC !== null && c.askC !== null && c.askC > c.bidC) acc.spreads[Math.min(100, Math.round((c.askC - c.bidC) * 100))]++;
        first = Math.min(first, t); last = Math.max(last, t);
        rows.push({ ticker: m.ticker, month });
        // The unit week: the event as the sim keys it (m.event, else the ticker without its last segment).
        const ek = m.event ?? String(m.ticker).slice(0, Math.max(0, String(m.ticker).lastIndexOf('-')));
        const pub = publishedStart(m);
        const ev = evs.get(ek) ?? { n: 0, nStart: 0, pub: Infinity, listed: Infinity };
        ev.n++;
        if (pub !== undefined) { ev.nStart++; ev.pub = Math.min(ev.pub, pub); }
        ev.listed = Math.min(ev.listed, matchTime(m));
        evs.set(ek, ev);
      });
      const want = new Map(rows.map((r) => [r.ticker, r.month]));
      eachLine(path.join(dir, 'trades', file), (r) => {
        const month = want.get(r.ticker);
        if (!month || !r.trades?.length) return;
        const acc = by.get(month)!;
        acc.withTape++; acc.trades += r.trades.length; acc.perMarket.push(r.trades.length);
      });
    }
    for (const [month, acc] of [...by].sort((x, y) => x[0].localeCompare(y[0]))) {
      months.push({ month, series: s, markets: acc.markets, events: acc.events.size, twoSided: [...acc.events.values()].filter((n) => n >= 2).length, volume: Math.round(acc.volume), withTape: acc.withTape, trades: acc.trades, noStart: acc.noStart, medSpreadC: histMedian(acc.spreads), medTradesPerMarket: median(acc.perMarket) });
    }
    const wk = new Map<string, WeekRow>();
    for (const ev of evs.values()) {
      const week = weekOf(Number.isFinite(ev.pub) ? ev.pub : ev.listed);
      const w = wk.get(week) ?? { series: s, week, markets: 0, events: 0, twoSided: 0, withStart: 0, noStart: 0 };
      w.markets += ev.n; w.events++; w.noStart += ev.n - ev.nStart;
      if (ev.n >= 2) { w.twoSided++; if (ev.nStart === ev.n) w.withStart++; }
      wk.set(week, w);
    }
    const sw = [...wk.values()].sort((x, y) => x.week.localeCompare(y.week));
    weeks.push(...sw);
    const era = startEraWeek(sw);
    totals[s] = { markets, events: eventMonth.size, noStart, first: markets ? new Date(first).toISOString().slice(0, 10) : undefined, last: markets ? new Date(last).toISOString().slice(0, 10) : undefined, ...(era ? { startEraWeek: era } : {}) };
  }
  return { months, weeks, totals };
}

/** The tennis cut's version (recordedTennis): the workflow cuts a day again when its row names an older one. 2: lines kept
 *  by the ticker's series (not only after that day's market line) and 'beat' liveness lines. 3: 'ws_beat' lines for the
 *  Kalshi socket's lines the cut drops, and both kinds of beat also at the line before a pause (and at the file's last
 *  lines), so every silence over 6 s of the source, and of the socket, is in the cut exactly as long as in the source. */
export const CUT_VERSION = 'tennis-cut/3';
/** A beat comes due this long after the last one (research/tennisTaSim.ts HEARTBEAT_KIND and SOCKET_BEAT_KIND read them). */
export const BEAT_MS = 5000;
/** A beat that comes due after the source (or the socket) paused for longer than this also marks the line before the pause. */
export const BEAT_PAUSE_MS = 1000;
/** The beat kinds the sim reads (research/tennisTaSim.ts HEARTBEAT_KIND and SOCKET_BEAT_KIND; tests/tennisTaData.test.ts
 *  checks they agree; not imported, so the download job does not load the sim and the bot's config). */
export const BEAT_KIND = 'beat';
export const SOCKET_BEAT = 'ws_beat';
/** The Kalshi socket's lines, as feedTimeline (research/tennisTaSim.ts) counts them on a raw file: book, delta, trade and
 *  lifecycle lines of any market (bot/marketdata/marketData.ts writes them from the socket's messages). */
const SOCKET_KINDS: ReadonlySet<string> = new Set(['book', 'delta', 'trade', 'lifecycle', SOCKET_BEAT]);
/** Amendment 4 item 9 (Steven, Nov 11): the bot's recordings before Nov 10 03:44 UTC (Nov 9 10:44 PM EST) sat on empty
 *  order-book reads and are practice data: a recorded day whose every line is before it is pool 'practice' (CutStats
 *  .practice), never scored, never pooled with later days; on a later day the lines before it are counted (thinLines).
 *  A copy of research/tennisTaSweep.ts FULL_BOOK_FROM (the sweep's recordedPoolOf labels a recorded match by its start);
 *  not imported, so the download job does not load the sim and the bot's config (tests/tennisTaData.test.ts holds the
 *  two together). */
export const FULL_BOOK_FROM = Date.parse('2026-11-10T03:44:00Z');

const TICKER = /"ticker":"([^"]+)"/;
const HEAD = /^\{"t":(-?\d+(?:\.\d+)?),"k":"([^"]+)"/;

/** Is a ticker's series (the prefix before its first '-') a tennis match series (contractKind 'match'), cached per series. */
export function matchSeriesTest(): (ticker: string) => boolean {
  const kindOf = new Map<string, boolean>();
  return (t) => {
    const i = t.indexOf('-');
    if (i <= 0) return false;
    const s = t.slice(0, i);
    let k = kindOf.get(s);
    if (k === undefined) { k = contractKind(s) === 'match'; kindOf.set(s, k); }
    return k;
  };
}

export interface CutStats {
  cut: string;
  /** FULL_BOOK_FROM as an ISO time; practice: every source line of the day is stamped before it (pool 'practice': never
   *  scored); thinLines: tennis lines kept (beats aside) stamped before it, on a practice day every one of them. */
  fullBookFrom: string; practice: boolean; thinLines: number;
  /** Source lines read, lines written (beat and ws_beat lines included), beat lines and ws_beat lines written. */
  lines: number; kept: number; beats: number; sockBeats: number;
  /** Match tickers with any line kept; of them, those whose market line is not in this day's file (listed on an earlier day). */
  matches: number; carried: number;
  /** Market lines kept, live score lines kept. */
  markets: number; scores: number;
}

/** One recorded day cut to its tennis lines (contract C8):
 *  - every line whose ticker (its first "ticker" field) belongs to a tennis match series (the prefix before the first '-'
 *    has contractKind 'match'): the market line, books, deltas, trades, results and lifecycle lines, whether or not the
 *    match's market line is in this day's file (the bot writes it once, when it first lists the match, up to 36 h before
 *    the start, so a match running past midnight has its lines on a day without it);
 *  - the live scores (tennis_score) and any 'alive' line naming a tennis match ticker;
 *  - the feed's liveness: the recorder writes no 'alive' lines (bot/marketdata/marketData.ts:264-269 only marks the books
 *    alive in memory; Recorder.write, marketData.ts:93-104, writes the kinds its callers pass, and none passes 'alive'; the
 *    history replay, research/history/historyReplay.ts:747, and research/replayFidelity.ts:137 make them), so the cut
 *    writes two clocks of beat lines, each stamped with a source line's time:
 *      {"t":<ms>,"k":"beat"}     of every source line (crypto, Coinbase spot and REST polls included): the recorder alive;
 *      {"t":<ms>,"k":"ws_beat"}  of the Kalshi socket's lines the cut drops (book, delta, trade and lifecycle lines of
 *                                other markets): the socket alive, which beats from any source cannot show (a reconnect
 *                                while Coinbase goes on), so the sim judges socket silences as on the raw file.
 *    A beat comes due at the first line BEAT_MS after the clock's last mark (a beat, or for the socket clock also a kept
 *    tennis socket line). When the line before it came more than BEAT_PAUSE_MS earlier (a pause), that line is marked
 *    first. So any two consecutive marks are either under BEAT_MS + BEAT_PAUSE_MS apart or two consecutive source (socket)
 *    lines: every silence of over 6 s, and so every outage the sim's 12 s rule finds, is in the cut exactly as in the
 *    source, and no shorter silence grows into one (research/tennisTaSim.ts feedTimeline). The last source line and the
 *    last socket line of the file are marked too (the next day's file restarts both clocks; the sim reads across midnight).
 *    Lines kept after a socket line not marked yet are held back (at most BEAT_MS of source time) until it is settled,
 *    so the cut stays in time order.
 *  Crypto contracts, asset prices, the SNN and other lines are dropped, and so are beat lines in the source. A clock step
 *  back of more than BEAT_MS restarts a clock. A failed write (a full disk) rejects, so the CLI exits 1. */
export async function recordedTennis(inFile: string, outFile: string): Promise<CutStats> {
  const isMatch = matchSeriesTest();
  const tickers = new Set<string>(), listed = new Set<string>();
  const gz = zlib.createGzip({ level: 6 });
  fs.mkdirSync(path.dirname(outFile), { recursive: true });
  const ws = fs.createWriteStream(outFile);
  gz.pipe(ws);
  // Settles when the file is written, or at the first error of either stream: a write waiting for 'drain' must not wait
  // for ever (pipe() unpipes on a write error, so the drain never comes and node would exit 0 with a truncated file).
  const done = new Promise<void>((res, rej) => { ws.on('finish', () => res()); ws.on('error', rej); gz.on('error', rej); });
  done.catch(() => { /* awaited below */ });
  let lines = 0, kept = 0, beats = 0, sockBeats = 0, markets = 0, scores = 0, thinLines = 0, lastT = -Infinity;
  const write = async (l: string) => { kept++; if (!gz.write(`${l}\n`)) await Promise.race([new Promise<void>((r) => gz.once('drain', () => r())), done]); };
  const due = (t: number, last: number) => t >= last + BEAT_MS || t < last - BEAT_MS;
  // The source clock: its last beat and the previous source line.
  let lastBeat = -Infinity, prevT = -Infinity;
  // The socket clock: its last mark (a ws_beat, or a kept tennis socket line) and the socket line after it that is not
  // marked yet (`pend`, the socket's previous line), with the lines kept since then held back until it is settled.
  let lastMark = -Infinity, pend: number | undefined;
  const held: string[] = [];
  const emit = async (l: string) => { if (pend !== undefined) held.push(l); else await write(l); };
  const beat = async (t: number) => { lastBeat = t; beats++; await emit(JSON.stringify({ t, k: BEAT_KIND })); };
  /** Settles the pending socket line: a ws_beat at its time when `mark`, then the lines held back behind it. */
  const settle = async (mark: boolean) => {
    if (pend === undefined) return;
    const p = pend;
    pend = undefined;
    if (mark) { lastMark = p; sockBeats++; await write(JSON.stringify({ t: p, k: SOCKET_BEAT })); }
    for (const l of held) await write(l);
    held.length = 0;
  };
  try {
    for await (const line of recordingLines(inFile)) {
      if (!line) continue;
      lines++;
      const h = HEAD.exec(line);
      if (!h) continue;
      const t = Number(h[1]), k = h[2];
      const finite = Number.isFinite(t);
      // The socket is silent more than BEAT_MS after its pending line: its next line comes due after a pause, so the
      // pending line is marked now (as it would be then) and the held lines go out.
      if (finite && pend !== undefined && t - pend > BEAT_MS) await settle(true);
      if (finite) {
        lastT = Math.max(lastT, t);
        if (due(t, lastBeat)) {
          if (prevT > lastBeat && t - prevT > BEAT_PAUSE_MS) await beat(prevT);
          await beat(t);
        }
        prevT = t;
      }
      let keep = false;
      if (k === 'tennis_score') { keep = true; scores++; }
      else if (k === 'alive') keep = /"tickers":\[([^\]]*)\]/.exec(line)?.[1].split(',').some((x) => isMatch(x.trim().replace(/^"|"$/g, ''))) ?? false;
      else if (k !== BEAT_KIND && k !== SOCKET_BEAT) {
        const tk = TICKER.exec(line)?.[1];
        if (tk !== undefined && isMatch(tk)) {
          keep = true; tickers.add(tk);
          if (k === 'market') { markets++; listed.add(tk); }
        }
      }
      if (finite && SOCKET_KINDS.has(k)) {
        await settle(pend !== undefined && due(t, lastMark) && t - pend > BEAT_PAUSE_MS);
        if (keep) lastMark = t;
        else if (due(t, lastMark)) { lastMark = t; sockBeats++; await write(JSON.stringify({ t, k: SOCKET_BEAT })); }
        else pend = t;
      }
      if (keep) { if (finite && t < FULL_BOOK_FROM) thinLines++; await emit(line); }
    }
    // The file's last socket line and last source line (the next day's file starts its own clocks).
    await settle(true);
    if (prevT > lastBeat) await beat(prevT);
    gz.end();
    await done;
  } catch (e) {
    gz.destroy(); ws.destroy();
    throw e;
  }
  let carried = 0;
  for (const tk of tickers) if (!listed.has(tk)) carried++;
  return { cut: CUT_VERSION, fullBookFrom: new Date(FULL_BOOK_FROM).toISOString(), practice: Number.isFinite(lastT) && lastT < FULL_BOOK_FROM, thinLines, lines, kept, beats, sockBeats, matches: tickers.size, carried, markets, scores };
}

async function main() {
  const cmd = process.argv[2];
  if (cmd === 'series') {
    const s = await tennisSeries();
    console.log(JSON.stringify(s, null, 1));
    return;
  }
  if (cmd === 'download') {
    const series = list(arg('series', 'KXATPMATCH'));
    const out = arg('out', 'data/tennis/kalshi');
    const budgetMs = Number(arg('budget-min', '300')) * 60_000;
    const t0 = Date.now();
    const log = (m: string) => console.log(`[tennis-data] ${m}`);
    // 2 days of 1-minute candles before the close cover the match (the download starts an hour before a known start).
    const r = await downloadKalshiHistory({ baseUrl: BASE, series, days: Number(arg('days', '900')), out, budgetMs: Math.round(budgetMs * 0.4), concurrency: 4, log });
    const left = Math.max(10 * 60_000, budgetMs - (Date.now() - t0));
    const tr = await downloadKalshiTrades({ baseUrl: BASE, series, out, budgetMs: left, concurrency: 4, log });
    console.log(JSON.stringify({ markets: r, trades: tr }));
    return;
  }
  if (cmd === 'inventory') {
    const inv = inventory(arg('hist', 'data/tennis/kalshi'), list(arg('series', 'KXATPMATCH,KXWTAMATCH')));
    fs.writeFileSync(arg('out', 'inventory.json'), JSON.stringify(inv, null, 1));
    console.log(JSON.stringify(inv.totals));
    return;
  }
  if (cmd === 'cut-version') {
    console.log(CUT_VERSION);
    return;
  }
  if (cmd === 'recorded') {
    const r = await recordedTennis(arg('in', ''), arg('out', ''));
    console.log(JSON.stringify(r));
    return;
  }
  console.error('usage: tennisTaData.ts series | download | inventory | recorded | cut-version');
  process.exitCode = 1;
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) void main().catch((e) => { console.error(e); process.exitCode = 1; });
