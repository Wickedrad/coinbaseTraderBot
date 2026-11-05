// Tennis TA rulebook trial (thread "Build a profitable tennis TA rulebook", Steven 2026-11-05 16:16 UTC): the tennis
// contract history the sweep runs on, built on a GitHub runner (the cloud sessions cannot reach Kalshi).
//
//   series     Kalshi's Sports series whose title or ticker says tennis (what can be downloaded at all)
//   download   settled match markets with 1-minute candles and their full trade tapes, as far back as Kalshi keeps them
//              (research/history/kalshiHistory.ts: public endpoints, no key, 10 requests a second, resumable)
//   inventory  matches by month and series: markets, two-sided events, volume, trades, quoted spread
//   recorded   one recorded day (the bot's own md-DAY file: real books, real tape, live scores) cut to its tennis lines
//
// Contract prices come from Kalshi, not from the Live Tennis API: that API serves live scores only (free tier 100 calls a
// day), so scores exist only where the bot recorded them.
//
//   node --import tsx research/tennisTaData.ts series
//   node --import tsx research/tennisTaData.ts download --series KXATPMATCH --days 900 --out data/tennis/kalshi --budget-min 300
//   node --import tsx research/tennisTaData.ts inventory --hist data/tennis/kalshi --series KXATPMATCH,KXWTAMATCH --out inv.json
//   node --import tsx research/tennisTaData.ts recorded --in rec/md-2026-10-25.jsonl.gz --out tennis-rec/md-2026-10-25.jsonl.gz

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

/** Matches by month (UTC month of the match start, else the close) and series. Streams one close-day file (markets, then
 *  that day's trade tapes) at a time: a whole series' candles and tapes (KXATPMATCH alone is 10.5k markets and 35.5M
 *  trades) do not fit a runner's heap at once. noStart counts markets Kalshi gave no start time. */
export function inventory(hist: string, series: string[]): { months: MonthRow[]; totals: Record<string, { markets: number; events: number; noStart: number; first?: string; last?: string }> } {
  const months: MonthRow[] = [];
  const totals: Record<string, { markets: number; events: number; noStart: number; first?: string; last?: string }> = {};
  for (const s of series) {
    const dir = path.join(hist, s);
    const files = fs.existsSync(dir) ? fs.readdirSync(dir).filter((x) => x.endsWith('.jsonl')).sort() : [];
    type Acc = { markets: number; volume: number; withTape: number; trades: number; noStart: number; spreads: number[]; perMarket: number[]; events: Map<string, number> };
    const by = new Map<string, Acc>();
    const eventMonth = new Map<string, string>();
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
    totals[s] = { markets, events: eventMonth.size, noStart, first: markets ? new Date(first).toISOString().slice(0, 10) : undefined, last: markets ? new Date(last).toISOString().slice(0, 10) : undefined };
  }
  return { months, totals };
}

const TICKER = /"ticker":"([^"]+)"/;

/** One recorded day cut to its tennis lines: the match markets (kind 'match'), their books, deltas, trades and results,
 *  the live scores, the alive marks and lifecycle lines. Crypto contracts, asset prices and the SNN lines are dropped. */
export async function recordedTennis(inFile: string, outFile: string): Promise<{ lines: number; kept: number; matches: number; scores: number }> {
  const matches = new Set<string>();
  const gz = zlib.createGzip({ level: 6 });
  fs.mkdirSync(path.dirname(outFile), { recursive: true });
  const ws = fs.createWriteStream(outFile);
  gz.pipe(ws);
  let lines = 0, kept = 0, scores = 0;
  const head = /^\{"t":(-?\d+(?:\.\d+)?),"k":"([a-z_]+)"/;
  for await (const line of recordingLines(inFile)) {
    if (!line) continue;
    lines++;
    const k = head.exec(line)?.[2];
    let keep = false;
    switch (k) {
      case 'market': {
        try { const m = JSON.parse(line); if ((m.kind ?? contractKind(m.series ?? '')) === 'match') { matches.add(m.ticker); keep = true; } } catch { /* torn line */ }
        break;
      }
      case 'book': case 'delta': case 'trade': case 'result': case 'lifecycle':
        keep = matches.has(TICKER.exec(line)?.[1] ?? '');
        break;
      case 'tennis_score':
        keep = true; scores++;
        break;
      case 'alive':
        keep = [...matches].some((t) => line.includes(`"${t}"`));
        break;
      default:
        keep = false;
    }
    if (keep) { kept++; if (!gz.write(`${line}\n`)) await new Promise<void>((r) => gz.once('drain', () => r())); }
  }
  gz.end();
  await new Promise<void>((r) => ws.on('finish', () => r()));
  return { lines, kept, matches: matches.size, scores };
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
  if (cmd === 'recorded') {
    const r = await recordedTennis(arg('in', ''), arg('out', ''));
    console.log(JSON.stringify(r));
    return;
  }
  console.error('usage: tennisTaData.ts series | download | inventory | recorded');
  process.exitCode = 1;
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) void main().catch((e) => { console.error(e); process.exitCode = 1; });
