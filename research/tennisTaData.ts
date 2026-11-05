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
import { downloadKalshiHistory, downloadKalshiTrades, getter, loadKalshiHistory, loadKalshiTrades } from './history/kalshiHistory';
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

export interface MonthRow { month: string; series: string; markets: number; events: number; twoSided: number; volume: number; withTape: number; trades: number; medSpreadC: number | null; medTradesPerMarket: number | null }

const median = (xs: number[]) => { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; };

/** Matches by month (UTC month of the match start, else the close) and series. */
export function inventory(hist: string, series: string[]): { months: MonthRow[]; totals: Record<string, { markets: number; events: number; first?: string; last?: string }> } {
  const months: MonthRow[] = [];
  const totals: Record<string, { markets: number; events: number; first?: string; last?: string }> = {};
  for (const s of series) {
    const ms = loadKalshiHistory(hist, s);
    const days = [...new Set(ms.map((m) => new Date(m.closeTime).toISOString().slice(0, 10)))];
    const tapes = loadKalshiTrades(hist, s, days);
    const by = new Map<string, typeof ms>();
    for (const m of ms) { const k = new Date(m.startTime ?? m.closeTime).toISOString().slice(0, 7); by.set(k, [...(by.get(k) ?? []), m]); }
    const ev = new Set<string>();
    for (const [month, rows] of [...by].sort()) {
      const events = new Map<string, number>();
      for (const m of rows) events.set(m.event ?? m.ticker, (events.get(m.event ?? m.ticker) ?? 0) + 1);
      for (const e of events.keys()) ev.add(e);
      const spreads: number[] = [], perMarket: number[] = [];
      let trades = 0, withTape = 0;
      for (const m of rows) {
        for (const c of m.candles ?? []) if (c.bidC !== null && c.askC !== null && c.askC > c.bidC) spreads.push(Math.round((c.askC - c.bidC) * 100));
        const t = tapes.get(m.ticker);
        if (t?.length) { withTape++; trades += t.length; perMarket.push(t.length); }
      }
      months.push({ month, series: s, markets: rows.length, events: events.size, twoSided: [...events.values()].filter((n) => n >= 2).length, volume: Math.round(rows.reduce((a, m) => a + (m.volume ?? 0), 0)), withTape, trades, medSpreadC: median(spreads), medTradesPerMarket: median(perMarket) });
    }
    const sorted = ms.map((m) => m.startTime ?? m.closeTime).sort((a, b) => a - b);
    totals[s] = { markets: ms.length, events: ev.size, first: sorted.length ? new Date(sorted[0]).toISOString().slice(0, 10) : undefined, last: sorted.length ? new Date(sorted[sorted.length - 1]).toISOString().slice(0, 10) : undefined };
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
