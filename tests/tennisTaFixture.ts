// Synthetic Kalshi tennis history for the tennis TA harness tests.
import fs from 'fs';
import path from 'path';

const DAY0 = Date.parse('2026-03-02T00:00:00Z');
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

