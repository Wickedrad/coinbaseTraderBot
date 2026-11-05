// Synthetic tennis data for the tennis TA harness tests: Kalshi history (stratum H, built into a replay by
// research/history/historyReplay.ts) and bot recordings (stratum R, read by the sweep as they are).
import fs from 'fs';
import path from 'path';

export const MIN = 60_000;

/** Kalshi history of three settled matches on 2026-03-02 with an underdog near 20c: the tape's taker side follows the move,
 *  so the flow and momentum signals fire together. */
export function writeTaHistory(dir: string, n = 3, days: string[] = ['2026-03-02']) {
  let seed = 11;
  const rnd = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
  const kal = path.join(dir, 'kalshi', 'KXATPMATCH');
  fs.mkdirSync(path.join(kal, 'trades'), { recursive: true });
  for (const day of days) {
  const D0 = Date.parse(`${day}T00:00:00Z`);
  const lines: string[] = [], tapes: string[] = [];
  for (let i = 1; i <= n; i++) {
    const winA = i % 2 === 1;
    const start = D0 + (8 + 3 * i) * 3_600_000, close = start + 150 * MIN;
    let p = 0.8; // P(A wins): A is the favourite, B the underdog near 20c
    const pts: Array<[number, number]> = [];
    for (let t = start - 60 * MIN; t <= close; t += 10_000) {
      const left = (close - t) / (close - start);
      const pull = t > start ? (left < 0.2 ? 0.03 : 0.002) : 0;
      p += ((winA ? 0.99 : 0.01) - p) * pull + (rnd() - 0.5) * (t > start ? 0.03 : 0.012);
      p = Math.min(0.98, Math.max(0.02, p));
      pts.push([t, p]);
    }
    for (const side of ['A', 'B'] as const) {
      const pa = (x: number) => (side === 'A' ? x : 1 - x);
      const candles = pts.filter(([t]) => t % MIN === 0).map(([t, x]) => ({ ts: t, bidC: +Math.max(0.01, pa(x) - 0.01).toFixed(2), askC: +Math.min(0.99, pa(x) + 0.01).toFixed(2), last: +pa(x).toFixed(2), volume: 40 }));
      const ticker = day === '2026-03-02' ? `KXATPMATCH-M${i}-${side}` : `KXATPMATCH-${day.replace(/-/g, '')}M${i}-${side}`;
      lines.push(JSON.stringify({ ticker, series: 'KXATPMATCH', event: day === '2026-03-02' ? `KXATPMATCH-M${i}` : `KXATPMATCH-${day.replace(/-/g, '')}M${i}`, openTime: start - 2 * 86_400_000, closeTime: close, strike: null, cap: null, title: `Will Player ${side}${i} win the match ${i} at Indian Wells?`, startTime: start, result: (side === 'A') === winA ? 'yes' : 'no', candles }));
      const tr: Array<[number, number, number, number]> = [];
      for (let j = 1; j < pts.length; j++) {
        const [t, x] = pts[j];
        if (t <= start - 45 * MIN) continue;
        const up = pa(x) >= pa(pts[j - 1][1]);
        // A print at the side the price moved to, sometimes through the old quote.
        tr.push([t + 3000, +pa(x).toFixed(2), 10 + Math.floor(rnd() * 30), up ? 1 : 0]);
      }
      tapes.push(JSON.stringify({ ticker, trades: tr }));
    }
  }
  fs.writeFileSync(path.join(kal, `${day}.jsonl`), lines.join('\n') + '\n');
  fs.writeFileSync(path.join(kal, 'trades', `${day}.jsonl`), tapes.join('\n') + '\n');
  }
}

/** A match whose P(A wins) follows a script: `p(min)` at each minute from the start (negative before it). */
export interface ScriptedMatch { id: string; winA: boolean; startHour: number; p: (min: number) => number; lengthMin?: number; noStart?: boolean; closeLaterB?: number }

/** The comeback: B at 30c before the start (too dear for the underdog leg), A climbs to 85c by the hour, holds there through
 *  the middle of the match (a favorite entry on A), then collapses in the last third and loses. */
export const comeback = (min: number): number => (min < 30 ? 0.7 : min < 60 ? 0.7 + ((min - 30) / 30) * 0.15 : min < 100 ? 0.85 : min < 130 ? 0.85 - ((min - 100) / 30) * 0.82 : 0.02);

/** Kalshi history of scripted matches on `day` (KXATPMATCH-<id>-A/-B): one-cent quotes around P every minute and a print
 *  every 10 s that wobbles a cent around it, its taker side following the wobble. `noStart`: no published start;
 *  `closeLaterB`: market B closes this many minutes after A. */
export function writeScriptedHistory(dir: string, day: string, matches: ScriptedMatch[]) {
  const kal = path.join(dir, 'kalshi', 'KXATPMATCH');
  fs.mkdirSync(path.join(kal, 'trades'), { recursive: true });
  const D0 = Date.parse(`${day}T00:00:00Z`);
  const lines: string[] = [], tapes: string[] = [];
  for (const m of matches) {
    const start = D0 + m.startHour * 3_600_000;
    const q = (x: number) => Math.min(0.97, Math.max(0.03, x));
    for (const side of ['A', 'B'] as const) {
      const pa = (x: number) => (side === 'A' ? q(x) : 1 - q(x));
      const close = start + ((m.lengthMin ?? 150) + (side === 'B' ? m.closeLaterB ?? 0 : 0)) * MIN;
      const candles: Array<Record<string, number>> = [];
      for (let t = start - 60 * MIN; t <= close; t += MIN) {
        const x = pa(m.p((t - start) / MIN));
        candles.push({ ts: t, bidC: +(x - 0.01).toFixed(2), askC: +(x + 0.01).toFixed(2), last: +x.toFixed(2), volume: 40 });
      }
      const ticker = `KXATPMATCH-${m.id}-${side}`;
      lines.push(JSON.stringify({ ticker, series: 'KXATPMATCH', event: `KXATPMATCH-${m.id}`, openTime: start - 2 * 86_400_000, closeTime: close, strike: null, cap: null, title: `Will Player ${side} win the ${m.id} match at Indian Wells?`, ...(m.noStart ? {} : { startTime: start }), result: (side === 'A') === m.winA ? 'yes' : 'no', candles }));
      const tr: Array<[number, number, number, number]> = [];
      let k = 0;
      for (let t = start - 45 * MIN + 3000; t <= close; t += 10_000, k++) {
        const wob = [0, -0.01, 0, 0.01][k % 4];
        const x = +Math.min(0.99, Math.max(0.01, pa(m.p((t - start) / MIN)) + wob)).toFixed(2);
        tr.push([t, x, 20, wob >= 0 ? 1 : 0]);
      }
      tapes.push(JSON.stringify({ ticker, trades: tr }));
    }
  }
  fs.writeFileSync(path.join(kal, `${day}.jsonl`), lines.join('\n') + '\n');
  fs.writeFileSync(path.join(kal, 'trades', `${day}.jsonl`), tapes.join('\n') + '\n');
}

/** The R fixture's timeline (ms). */
export interface RecordingPlan { listed: number; start: number; end: number; gapFrom: number; gapTo: number; snapAgain: number; determined: number; settled: number; event: string; tickers: [string, string] }

/** Recorded lines ({t, k, ...}) written as the bot's day files (md-YYYY-MM-DD.jsonl), in time order (stable for ties). */
export function writeRecordingLines(dir: string, lines: Array<{ t: number; k: string; [key: string]: unknown }>): void {
  fs.mkdirSync(dir, { recursive: true });
  const byDay = new Map<string, string[]>();
  for (const x of [...lines].sort((a, b) => a.t - b.t)) {
    const d = new Date(x.t).toISOString().slice(0, 10);
    const l = byDay.get(d) ?? [];
    l.push(JSON.stringify(x));
    byDay.set(d, l);
  }
  for (const [d, l] of byDay) fs.writeFileSync(path.join(dir, `md-${d}.jsonl`), l.join('\n') + '\n');
}

/** What shows the feed's liveness in a recording: 'none' = tennis lines only (the tennis cut research/tennisTaData.ts
 *  writes today; production writes no heartbeat kind), 'hb' = a heartbeat line every 5 s (what a cut that keeps the feed's
 *  liveness would add), 'raw' = a delta of a crypto contract every 5 s (the raw file, the socket's other markets). */
export type RecordedFeed = 'none' | 'hb' | 'raw';

/** The bot's recordings of one match: the market lines when the bot first lists it (two days before its start), one book
 *  snapshot each then deltas, the tape, a 10-minute silence in the match (no line at all) and the settlement only as
 *  Kalshi's lifecycle lines (determined, then settled; no result line; a 'deactivated' line with a wrong result mid-match
 *  must be ignored). After the silence the deltas come back and the next snapshots follow 2 minutes later, or with
 *  `resync` it ends with fresh snapshots of both books first (a reconnect: Kalshi re-snapshots on resubscribe). A wins
 *  from 75c. */
export function writeTaRecording(dir: string, startDay = '2026-03-04', o: { feed?: RecordedFeed; resync?: boolean } = {}): RecordingPlan {
  const feed = o.feed ?? 'none';
  const start = Date.parse(`${startDay}T10:00:00Z`);
  const plan: RecordingPlan = { listed: start - 46 * 3_600_000, start, end: start + 120 * MIN, gapFrom: start + 40 * MIN, gapTo: start + 50 * MIN, snapAgain: start + 52 * MIN,
    determined: start + 120 * MIN + 5000, settled: start + 130 * MIN, event: 'KXATPMATCH-R1', tickers: ['KXATPMATCH-R1-A', 'KXATPMATCH-R1-B'] };
  const out: Array<{ t: number; k: string; [key: string]: unknown }> = [];
  const put = (t: number, k: string, data: Record<string, unknown>) => out.push({ t, k, ...data });
  const close = start + 7 * 86_400_000; // Kalshi's scheduled close: days after the match is decided
  for (const [i, ticker] of plan.tickers.entries()) {
    put(plan.listed, 'market', { ticker, series: 'KXATPMATCH', asset: 'TENNIS', openTime: plan.listed - 3_600_000, closeTime: close, kind: 'match', event: plan.event, tickSize: 0.01, title: `Will Player ${i ? 'B' : 'A'} win the R1 match at Indian Wells?`, startTime: start });
  }
  const pA = (t: number) => (t < start ? 0.75 : Math.min(0.97, 0.75 + ((t - start) / (plan.end - start)) * 0.22));
  const quote = (t: number, side: number) => { const x = Math.round((side ? 1 - pA(t) : pA(t)) * 100) / 100; return { bid: +(x - 0.01).toFixed(2), ask: +(x + 0.01).toFixed(2) }; };
  const last: Array<{ bid: number; ask: number }> = [];
  const snap = (t: number) => plan.tickers.forEach((ticker, i) => { const qq = quote(t, i); last[i] = qq; put(t, 'book', { ticker, bids: [{ price: qq.bid, size: 100 }], asks: [{ price: qq.ask, size: 100 }], ts: t }); });
  const move = (t: number) => plan.tickers.forEach((ticker, i) => {
    const qq = quote(t, i), was = last[i];
    if (qq.bid !== was.bid) { put(t, 'delta', { ticker, side: 'bid', price: was.bid, delta: -100, ts: t }); put(t, 'delta', { ticker, side: 'bid', price: qq.bid, delta: 100, ts: t }); }
    if (qq.ask !== was.ask) { put(t, 'delta', { ticker, side: 'ask', price: was.ask, delta: -100, ts: t }); put(t, 'delta', { ticker, side: 'ask', price: qq.ask, delta: 100, ts: t }); }
    last[i] = qq;
  });
  snap(plan.listed + 1000);
  for (let t = plan.listed + 5000; t <= plan.settled + 10 * MIN; t += 5000) {
    if (t >= plan.gapFrom && t < plan.gapTo) continue;
    if (feed === 'hb') put(t, 'hb', {});
    if (feed === 'raw') put(t, 'delta', { ticker: 'KXBTCD-26MAR0417-T90000', side: 'bid', price: 0.5, delta: t % 10_000 ? 1 : -1, ts: t });
    if (t >= start - 60 * MIN && t <= plan.end) {
      if (o.resync && t === plan.gapTo) snap(t);
      if (t % 10_000 === 0) move(t);
      if (t === plan.snapAgain) snap(t);
      if (t % 10_000 === 5000) plan.tickers.forEach((ticker, i) => { const qq = quote(t, i); const down = Math.floor(t / 10_000) % 2 === 1; put(t + 1, 'trade', { ticker, price: down ? qq.bid : qq.ask, count: 15, takerSide: down ? 'no' : 'yes', ts: t + 1 }); });
    }
  }
  // A lifecycle line that is not a settlement (production settles only on determined / settled) even if it carries a result.
  put(start + 60 * MIN + 2500, 'lifecycle', { ticker: plan.tickers[0], event: 'deactivated', result: 'no', ts: start + 60 * MIN + 2500 });
  plan.tickers.forEach((ticker, i) => {
    put(plan.determined, 'lifecycle', { ticker, event: 'determined', result: i ? 'no' : 'yes', ts: plan.determined });
    put(plan.settled, 'lifecycle', { ticker, event: 'settled', result: i ? 'no' : 'yes', ts: plan.settled });
  });
  writeRecordingLines(dir, out);
  return plan;
}
