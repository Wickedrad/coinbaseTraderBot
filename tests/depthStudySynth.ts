// A synthetic recorded day for the depth study's tests (no real recordings in the test container; nothing random: every number is
// a formula of the contract's asset, class and the clock). Not a test file itself (the runner only picks up *.test.ts).
//
// Contracts of three classes per asset, all 15 minutes, all in the 40-60c mid bucket so one stress bucket is one class:
//   calm    the quote never moves                      (stress 0 c)     deep books, few trades
//   normal  the minute mid alternates 50 / 51          (stress 1 c)
//   active  the minute mid alternates 50 / 54          (stress 4 c)     thin books, many trades
// An asset's `size` and `trades` scale every book level and every trade rate (BTC deep and busy, ETH not).
import fs from 'fs';
import zlib from 'zlib';

export const MINUTE = 60_000;
export const SYNTH_OPEN = Date.UTC(2026, 10, 11, 12, 0, 0);
export const CLASSES = ['calm', 'normal', 'active'] as const;
export type SynthClass = (typeof CLASSES)[number];
const MID_OF: Record<SynthClass, (m: number) => number> = { calm: () => 50, normal: (m) => 50 + (m % 2), active: (m) => 50 + 4 * (m % 2) };
/** What each class does to the book and the flow (the active contract is thinner and busier). */
const SIZE_OF: Record<SynthClass, number> = { calm: 1, normal: 0.6, active: 0.3 };
const TRADES_OF: Record<SynthClass, number> = { calm: 1, normal: 2, active: 5 };

export interface SynthAsset { name: string; /** every level's size, in contracts, of a calm contract's best level */ size: number; /** trades a quarter-minute of a calm contract */ trades: number }

export interface SynthRecording { events: Array<Record<string, any>>; tickers: Array<{ ticker: string; asset: string; cls: SynthClass }> }

/** A recorded day's records: `perClass` contracts of each class for each asset, in time order. `open`: when they all open (ms). */
export function synthRecording(assets: readonly SynthAsset[], o: { perClass?: number; open?: number } = {}): SynthRecording {
  const perClass = o.perClass ?? 8, open = o.open ?? SYNTH_OPEN, close = open + 15 * MINUTE;
  const events: Array<Record<string, any>> = [], tickers: SynthRecording['tickers'] = [];
  for (const a of assets) for (const cls of CLASSES) for (let i = 0; i < perClass; i++) {
    const ticker = `KX${a.name}15M-26NOV111200-${cls[0].toUpperCase()}${i}`;
    tickers.push({ ticker, asset: a.name, cls });
    events.push({ t: open - MINUTE, k: 'market', ticker, series: `KX${a.name}15M`, kind: 'updown', openTime: open, closeTime: close, asset: a.name });
    for (let q = 0; q < 60; q++) {
      const T = open + q * 15_000, m = Math.floor(q / 4), mid = MID_OF[cls](m);
      const size = Math.max(1, Math.round(a.size * SIZE_OF[cls]));
      const lv = (j: number) => Math.max(1, Math.round(size * (1 + 0.1 * j)));
      events.push({ t: T, k: 'book', ticker,
        bids: Array.from({ length: 10 }, (_, j) => ({ price: (mid - 1 - j) / 100, size: lv(j) })),
        asks: Array.from({ length: 10 }, (_, j) => ({ price: (mid + 1 + j) / 100, size: lv(j) })) });
      events.push({ t: T + 3000, k: 'delta', ticker, side: 'bid', price: (mid - 1) / 100, delta: 5 });
      events.push({ t: T + 6000, k: 'delta', ticker, side: 'bid', price: (mid - 1) / 100, delta: -3 });
      events.push({ t: T + 9000, k: 'delta', ticker, side: 'ask', price: (mid + 1) / 100, delta: 4 });
      const n = Math.max(1, Math.round(a.trades * TRADES_OF[cls]));
      for (let k = 0; k < n; k++) events.push({ t: T + 1000 + Math.floor((k * 9000) / n), k: 'trade', ticker, price: (mid + (k % 2 ? 1 : -1)) / 100, count: 2 + (k % 3), takerSide: k % 2 ? 'yes' : 'no', ts: T + 1000 + Math.floor((k * 9000) / n) });
    }
    events.push({ t: close + 1, k: 'result', ticker, result: 'yes' });
  }
  events.sort((x, y) => x.t - y.t);
  return { events, tickers };
}

export function writeRecording(file: string, events: readonly object[]): void {
  fs.writeFileSync(file, zlib.gzipSync(events.map((e) => JSON.stringify(e)).join('\n') + '\n'));
}
