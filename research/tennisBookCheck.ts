// Tennis Part A: are the bot's recorded tennis books a sound reference for the tennis simulators? (Steven, Nov 5:
// recorded-book checks alone are the simulator gate; the tennis TA thread's G1 "recorded books only".)
//
// Reads recorded days (md-DAY files, whole or cut to tennis by research/tennisTaData.ts recorded) and, on the match
// markets only (kind 'match'), measures with the receipt clock (t):
//   crossed    share of book time (gaps capped at 60 s) with best bid >= best ask, and one-sided time
//   receipt    trade receipt minus the exchange's stamp (ts): a stale tape fills orders that never existed
//   matched    taker volume printing at a level the book showed (present at receipt, or taken out by a delta or snapshot
//              within MATCH_MS either side); the rest printed where the recorded book never showed liquidity
//   depletion  for a taker print at the top, when the recorded book shows that level reduced (a delta or snapshot);
//              a replay taker can retake the same contracts until it does (ghost liquidity)
//   through    taker volume at the touch vs strictly through it: F1 maker fills (strictly through only) only see the
//              second kind, PaperExchange also lets prints at the price eat the queue
//   tick       share of book levels and prints off the whole-cent grid
//   candles    with --history (Kalshi's 1-minute candles, research/history/kalshiHistory.ts), each candle's closing bid and
//              ask against the recorded book at the candle's stamp: agreement, the first candle of each market (minute 0)
//              on its own, and carried candles (the close repeats the one before while the recorded top moved)
// Pass rules (fixed before the first run): crossed time < 1%; matched volume >= 98%; depletion shown within 5 s for
// >= 95% of top-of-book taker volume; receipt lag p99 < 5 s. Every verdict is labelled "recorded books only".
//
//   node --import tsx research/tennisBookCheck.ts --recordings DIR [--history DIR --series KXATPMATCH] [--from 2026-10-21T00:00Z]
//       [--to 2026-11-05T02:00Z] [--out check.json]

import fs from 'fs';
import path from 'path';
import { recordingFiles, recordingLines } from '../bot/marketdata/recordingFiles';
import { OrderBook } from '../bot/marketdata/orderBook';
import { contractKind } from '../bot/model/fairValue';
import { loadKalshiHistory, type KalshiCandle } from './history/kalshiHistory';

const MATCH_MS = 2_000, DEPLETE_WAIT_MS = 10_000, GAP_CAP_MS = 60_000;
const k4 = (p: number) => Math.round(p * 10000);

interface Neg { t: number; side: 'bid' | 'ask'; k: number }
interface Pending { t: number; side: 'bid' | 'ask'; k: number; count: number }
interface Mk { book: OrderBook; last: number; crossed: boolean; oneSided: boolean; negs: Neg[]; pending: Pending[]; trades: number; candles: Array<KalshiCandle & { first: boolean }>; ci: number; prevTop?: string; prevCandle?: string }
const TENNIS = /^KX(ATP|WTA)[A-Z]*MATCH-/;

function quantiles(xs: number[], qs: number[]): number[] {
  if (!xs.length) return qs.map(() => NaN);
  const s = Float64Array.from(xs).sort();
  return qs.map((q) => s[Math.min(s.length - 1, Math.floor(q * s.length))]);
}

export async function tennisBookCheck(dir: string, from: number, to: number, hist?: { dir: string; series: string[] }) {
  const mk = new Map<string, Mk>();
  const isMatch = new Set<string>();
  const days: string[] = [];
  let bookMs = 0, crossedMs = 0, oneSidedMs = 0, updates = 0;
  let trades = 0, vol = 0, matchedVol = 0, topVol = 0, depletedVol = 0, neverVol = 0, atTouch = 0, through = 0, inside = 0;
  let levels = 0, offGridLevels = 0, offGridPrints = 0, depletedIn5 = 0;
  const cand = { n: 0, both: 0, within1: 0, first: 0, firstBoth: 0, carried: 0, carriedWrong: 0, noBook: 0 };
  const lagRecv: number[] = [], lagDeplete: number[] = [], gaps: number[] = [];
  const histCandles = new Map<string, Array<KalshiCandle & { first: boolean }>>();
  if (hist) for (const sr of hist.series) for (const m of loadKalshiHistory(hist.dir, sr)) {
    if (m.closeTime < from || m.openTime >= to || !m.candles?.length) continue;
    histCandles.set(m.ticker, m.candles.filter((c) => c.ts >= from && c.ts < to).map((c, i) => ({ ...c, first: i === 0 && c.ts === m.candles[0].ts })));
  }
  const tickers = new Set<string>(), events = new Set<string>();

  const state = (ticker: string): Mk => {
    let s = mk.get(ticker);
    if (!s) { s = { book: new OrderBook(ticker), last: 0, crossed: false, oneSided: false, negs: [], pending: [], trades: 0, candles: histCandles.get(ticker) ?? [], ci: 0 }; mk.set(ticker, s); }
    return s;
  };
  // Candles due by receipt time t are scored against the book as it stood (before the event at t is applied).
  const scoreCandles = (s: Mk, t: number) => {
    while (s.ci < s.candles.length && s.candles[s.ci].ts <= t) {
      const c = s.candles[s.ci++];
      if (c.bidC === null || c.askC === null || !(c.askC > c.bidC)) continue;
      const b = s.book.bestBid(), a = s.book.bestAsk();
      const top = b && a ? `${k4(b.price)}/${k4(a.price)}` : undefined;
      const key = `${k4(c.bidC)}/${k4(c.askC)}`;
      if (!top) { cand.noBook++; s.prevCandle = key; continue; }
      cand.n++;
      const both = top === key;
      if (both) cand.both++;
      if (Math.abs(k4(b!.price) - k4(c.bidC)) <= 100 && Math.abs(k4(a!.price) - k4(c.askC)) <= 100) cand.within1++;
      if (c.first) { cand.first++; if (both) cand.firstBoth++; }
      if (s.prevCandle === key && s.prevTop !== undefined && s.prevTop !== top) { cand.carried++; if (!both) cand.carriedWrong++; }
      s.prevCandle = key; s.prevTop = top;
    }
  };
  const advance = (s: Mk, t: number) => {
    if (s.last) { const g = Math.min(GAP_CAP_MS, Math.max(0, t - s.last)); bookMs += g; if (s.crossed) crossedMs += g; if (s.oneSided) oneSidedMs += g; gaps.push(t - s.last); }
    s.last = t;
  };
  const after = (s: Mk) => {
    const b = s.book.bestBid(), a = s.book.bestAsk();
    s.crossed = !!(b && a && b.price >= a.price);
    s.oneSided = !b || !a;
    updates++;
  };
  // A level reduced at receipt t: settle the oldest pending print at that level, else remember it for a later print.
  const reduced = (s: Mk, side: 'bid' | 'ask', k: number, t: number) => {
    const i = s.pending.findIndex((p) => p.side === side && p.k === k);
    if (i >= 0) { const p = s.pending[i]; lagDeplete.push(t - p.t); depletedVol += p.count; if (t - p.t <= 5000) depletedIn5 += p.count; s.pending.splice(i, 1); return; }
    s.negs.push({ t, side, k });
  };
  const expire = (s: Mk, t: number) => {
    s.negs = s.negs.filter((n) => t - n.t <= MATCH_MS);
    s.pending = s.pending.filter((p) => { if (t - p.t > DEPLETE_WAIT_MS) { neverVol += p.count; return false; } return true; });
  };

  for (const d of recordingFiles(dir)) {
    const d0 = Date.parse(`${d.day}T00:00:00Z`);
    if (d0 + 86_400_000 <= from || d0 >= to) continue;
    days.push(d.day);
    for await (const line of recordingLines(d.file)) {
      if (!line) continue;
      let e: any;
      try { e = JSON.parse(line); } catch { continue; }
      if (e.k === 'market') { if ((e.kind ?? contractKind(e.series ?? '', e.strikeType, e.ticker)) === 'match') { isMatch.add(e.ticker); if (e.event) events.add(e.event); } continue; }
      if (!e.ticker || !(isMatch.has(e.ticker) || TENNIS.test(e.ticker))) continue;
      const t = e.t;
      if (!(t >= from && t < to)) continue;
      const s = state(e.ticker);
      expire(s, t);
      scoreCandles(s, t);
      if (e.k === 'book') {
        advance(s, t);
        const old = { bid: s.book.bestBid(), ask: s.book.bestAsk() };
        // A snapshot that shows the top smaller (or gone) counts as the level reduced.
        const bids = new Map<number, number>(), asks = new Map<number, number>();
        for (const l of e.bids ?? []) bids.set(k4(l.price), l.size);
        for (const l of e.asks ?? []) asks.set(k4(l.price), l.size);
        if (old.bid && (bids.get(k4(old.bid.price)) ?? 0) < old.bid.size) reduced(s, 'bid', k4(old.bid.price), t);
        if (old.ask && (asks.get(k4(old.ask.price)) ?? 0) < old.ask.size) reduced(s, 'ask', k4(old.ask.price), t);
        s.book.applySnapshot(e, t);
        for (const l of [...(e.bids ?? []), ...(e.asks ?? [])]) { levels++; if (k4(l.price) % 100 !== 0) offGridLevels++; }
        after(s);
      } else if (e.k === 'delta') {
        advance(s, t);
        if (e.delta < 0) reduced(s, e.side, k4(e.price), t);
        s.book.applyDelta(e.side, e.price, e.delta, t);
        levels++; if (k4(e.price) % 100 !== 0) offGridLevels++;
        after(s);
      } else if (e.k === 'trade') {
        tickers.add(e.ticker);
        trades++; s.trades++;
        const c = Number(e.count) || 0, p = k4(e.price);
        vol += c;
        if (p % 100 !== 0) offGridPrints += c;
        if (Number.isFinite(e.ts)) lagRecv.push(t - e.ts);
        // A YES taker lifts YES asks; a NO taker hits YES bids.
        const side: 'bid' | 'ask' = e.takerSide === 'yes' ? 'ask' : 'bid';
        const shown = s.book.sizeAt(side, e.price) > 0;
        const negI = s.negs.findIndex((n) => n.side === side && n.k === p);
        if (shown || negI >= 0) matchedVol += c;
        const top = side === 'ask' ? s.book.bestAsk() : s.book.bestBid();
        if (top) {
          const tk = k4(top.price);
          if (tk === p) atTouch += c;
          else if (side === 'ask' ? p > tk : p < tk) through += c;
          else inside += c;
        }
        // Depletion: a reduction already seen within MATCH_MS before, else wait for one.
        if (negI >= 0) { lagDeplete.push(s.negs[negI].t - t); depletedVol += c; depletedIn5 += c; topVol += c; s.negs.splice(negI, 1); }
        else if (shown) { topVol += c; s.pending.push({ t, side, k: p, count: c }); }
      }
    }
  }
  for (const s of mk.values()) for (const p of s.pending) neverVol += p.count;

  const [r50, r90, r99] = quantiles(lagRecv, [0.5, 0.9, 0.99]);
  const [d50, d90, d99] = quantiles(lagDeplete, [0.5, 0.9, 0.99]);
  const [g50, g90, g99] = quantiles(gaps, [0.5, 0.9, 0.99]);
  const depletedIn5Vol = topVol ? depletedIn5 / topVol : NaN;
  const out = {
    label: 'recorded books only',
    span: { from: new Date(from).toISOString(), to: new Date(to).toISOString(), days },
    coverage: { matchMarkets: isMatch.size, tradedMarkets: tickers.size, events: events.size, bookUpdates: updates, trades, contracts: +vol.toFixed(2), bookHours: +(bookMs / 3.6e6).toFixed(1) },
    crossed: { crossedShare: crossedMs / Math.max(1, bookMs), oneSidedShare: oneSidedMs / Math.max(1, bookMs) },
    updateGapMs: { p50: g50, p90: g90, p99: g99 },
    receiptLagMs: { p50: r50, p90: r90, p99: r99, over5s: lagRecv.filter((x) => x > 5000).length / Math.max(1, lagRecv.length) },
    matchedVolShare: matchedVol / Math.max(1, vol),
    depletion: { topVolShare: topVol / Math.max(1, vol), lagMs: { p50: d50, p90: d90, p99: d99 }, shownWithin5sShare: depletedIn5Vol, neverShownVolShare: neverVol / Math.max(1, topVol) },
    touch: { atTouchShare: atTouch / Math.max(1, vol), throughShare: through / Math.max(1, vol), insideShare: inside / Math.max(1, vol) },
    ...(hist ? { candles: { scored: cand.n, noRecordedBook: cand.noBook, exactShare: cand.both / Math.max(1, cand.n), within1cShare: cand.within1 / Math.max(1, cand.n), minute0: { n: cand.first, exactShare: cand.firstBoth / Math.max(1, cand.first) }, carried: { n: cand.carried, wrongShare: cand.carriedWrong / Math.max(1, cand.carried) } } } : {}),
    tick: { offGridLevelShare: offGridLevels / Math.max(1, levels), offGridPrintShare: offGridPrints / Math.max(1, vol) },
  };
  const pass = {
    crossed: out.crossed.crossedShare < 0.01,
    matched: out.matchedVolShare >= 0.98,
    depletion: out.depletion.shownWithin5sShare >= 0.95,
    receipt: (r99 ?? Infinity) < 5000,
  };
  return { ...out, pass, verdict: Object.values(pass).every(Boolean) ? 'PASS (recorded books only)' : 'FAIL (recorded books only)' };
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) {
  const arg = (k: string, d: string) => { const i = process.argv.indexOf(`--${k}`); return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d; };
  const h = arg('history', '');
  const r = await tennisBookCheck(arg('recordings', 'data/recordings'), Date.parse(arg('from', '2026-10-21T00:00:00Z')), Date.parse(arg('to', '2026-11-05T02:00:00Z')),
    h ? { dir: h, series: arg('series', 'KXATPMATCH').split(',') } : undefined);
  const outFile = arg('out', '');
  if (outFile) fs.writeFileSync(outFile, JSON.stringify(r, null, 2));
  console.log(JSON.stringify(r, null, 2));
}
