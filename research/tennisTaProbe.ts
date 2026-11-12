/**
 * Tennis TA: a read-only probe of the stored Kalshi tennis history (no sweep, no score, nothing counted). It answers how
 * long a match market runs from the replay's begin (research/history/historyReplay.ts tennisEvents: the published start
 * minus 30 min, else the first stored candle) to its close, why a stored market could not be replayed, and how a match
 * that closes days after its begin traded, so the replay's close-day scan and the sim's read span are sized from the
 * data rather than guessed. Run by .github/workflows/tennis-ta-probe.yml on a commit to research/tennis-ta/probe-request.json.
 *
 *   node --import tsx research/tennisTaProbe.ts --hist data/tennis/kalshi --series KXATPMATCH,KXWTAMATCH --from 2026-04-19 --to 2026-11-06 --out probe.json
 */
import fs from 'fs';
import path from 'path';
import type { KalshiHistMarket } from './history/kalshiHistory';

const MIN = 60_000, HOUR = 3_600_000, DAY = 86_400_000;
const dayOf = (t: number) => new Date(t).toISOString().slice(0, 10);
/** The unit week a time falls in (Monday 05:00 UTC edges, research/tennisTaSweep.ts units). */
const weekOf = (t: number) => { const d = new Date(t - 5 * HOUR); const dow = (d.getUTCDay() + 6) % 7; return `W-${dayOf(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) - dow * DAY)}`; };
const bucket = (x: number, edges: number[]) => { for (const e of edges) if (x < e) return `<${e}`; return `>=${edges[edges.length - 1]}`; };
const inc = (o: Record<string, number>, k: string, n = 1) => { o[k] = (o[k] ?? 0) + n; };

interface Sample { ticker: string; open: string; start?: string; close: string; firstCandle?: string; candles: number; volume: number | null; tradedDays: Record<string, number>; firstVol?: string; lastVol?: string }

function args(argv: string[]): Record<string, string> {
  const a: Record<string, string> = {};
  for (let i = 0; i < argv.length; i++) if (argv[i].startsWith('--')) a[argv[i].slice(2)] = argv[i + 1] ?? '';
  return a;
}

export function probeSeries(dir: string, from: number, to: number) {
  const s = {
    lines: 0, torn: 0, untraded: 0, tradedNoCandles: 0, resultOther: 0, replayable: 0, noStart: 0, startAfterClose: 0,
    /** Close day minus begin day (the replay reads close days [begin day, begin day + 1] today). */
    lagDays: {} as Record<string, number>,
    /** Begin to close, hours (the time the sim keeps the market live). */
    spanH: {} as Record<string, number>,
    /** Published start to close, hours (start < close only). */
    startToCloseH: {} as Record<string, number>,
    /** First stored candle to close, hours (the downloader keeps at most the last 48 h). */
    candleSpanH: {} as Record<string, number>,
    /** Published start minus close, hours (start >= close only). */
    startAfterCloseH: {} as Record<string, number>,
    /** Replayable markets whose close day is 2+ days after the begin day, by unit week of the begin, and by cause. */
    lateByWeek: {} as Record<string, number>, replayableByWeek: {} as Record<string, number>,
    lateCause: {} as Record<string, number>,
    /** Late markets: minutes with volume by day offset from the begin day (do they trade while they wait?). */
    lateVolMinutesByOffset: {} as Record<string, number>,
    samples: { late: [] as Sample[], startAfterClose: [] as Sample[], tradedNoCandles: [] as Sample[] },
  };
  const files = fs.existsSync(dir) ? fs.readdirSync(dir).filter((f) => /^\d{4}-\d{2}-\d{2}\.jsonl$/.test(f)).sort() : [];
  for (const f of files) {
    const t = Date.parse(f.slice(0, 10));
    if (t < from || t >= to) continue;
    for (const line of fs.readFileSync(path.join(dir, f), 'utf8').split('\n')) {
      if (!line) continue;
      let m: KalshiHistMarket;
      try { m = JSON.parse(line); } catch { s.torn++; continue; }
      s.lines++;
      const sample = (): Sample => {
        const tradedDays: Record<string, number> = {};
        const vol = (m.candles ?? []).filter((c) => (c.volume ?? 0) > 0);
        for (const c of vol) inc(tradedDays, dayOf(c.ts));
        return {
          ticker: m.ticker, open: new Date(m.openTime).toISOString(), ...(m.startTime ? { start: new Date(m.startTime).toISOString() } : {}), close: new Date(m.closeTime).toISOString(),
          ...(m.candles?.length ? { firstCandle: new Date(m.candles[0].ts).toISOString() } : {}), candles: m.candles?.length ?? 0, volume: m.volume ?? null, tradedDays,
          ...(vol.length ? { firstVol: new Date(vol[0].ts).toISOString(), lastVol: new Date(vol[vol.length - 1].ts).toISOString() } : {}),
        };
      };
      if (m.noVolume || m.error) { s.untraded++; continue; }
      if (!m.candles?.length) { s.tradedNoCandles++; if (s.samples.tradedNoCandles.length < 8) s.samples.tradedNoCandles.push(sample()); continue; }
      if (m.result !== 'yes' && m.result !== 'no') { s.resultOther++; continue; }
      s.replayable++;
      const first = m.candles[0].ts;
      inc(s.candleSpanH, bucket((m.closeTime - first) / HOUR, [1, 3, 6, 12, 24, 47, 49]));
      if (!m.startTime) s.noStart++;
      else if (m.startTime >= m.closeTime) { s.startAfterClose++; inc(s.startAfterCloseH, bucket((m.startTime - m.closeTime) / HOUR, [0.5, 1, 3, 6, 12, 24, 48, 168])); if (s.samples.startAfterClose.length < 8) s.samples.startAfterClose.push(sample()); }
      else inc(s.startToCloseH, bucket((m.closeTime - m.startTime) / HOUR, [1, 2, 3, 4, 6, 12, 24, 48, 72, 168]));
      const begin = Math.max(m.openTime, (m.startTime && m.startTime < m.closeTime ? m.startTime : first) - 30 * MIN);
      const lag = Math.round((Date.parse(dayOf(m.closeTime)) - Date.parse(dayOf(begin))) / DAY);
      inc(s.lagDays, lag > 8 ? '>8' : String(lag));
      inc(s.spanH, bucket((m.closeTime - begin) / HOUR, [2, 3, 4, 6, 12, 24, 36, 48, 72, 168]));
      const wk = weekOf(m.startTime && m.startTime < m.closeTime ? m.startTime : begin);
      inc(s.replayableByWeek, wk);
      if (lag >= 2) {
        inc(s.lateByWeek, wk);
        inc(s.lateCause, !m.startTime ? 'noStart' : m.startTime >= m.closeTime ? 'startAfterClose' : 'startLongBeforeClose');
        for (const c of m.candles) if ((c.volume ?? 0) > 0) inc(s.lateVolMinutesByOffset, String(Math.round((Date.parse(dayOf(c.ts)) - Date.parse(dayOf(begin))) / DAY)));
        if (s.samples.late.length < 12) s.samples.late.push(sample());
      }
    }
  }
  return s;
}

function main(): void {
  const a = args(process.argv.slice(2));
  const hist = a.hist ?? 'data/tennis/kalshi';
  const series = (a.series ?? 'KXATPMATCH,KXWTAMATCH').split(',').filter(Boolean);
  const from = Date.parse(a.from ?? '2026-04-19'), to = Date.parse(a.to ?? '2026-11-06');
  const out: Record<string, ReturnType<typeof probeSeries>> = {};
  for (const s of series) out[s] = probeSeries(path.join(hist, s), from, to);
  const text = JSON.stringify({ from: dayOf(from), to: dayOf(to), series: out }, null, 1);
  if (a.out) fs.writeFileSync(a.out, text);
  for (const [s, x] of Object.entries(out)) {
    console.log(`${s}: ${x.lines} lines (${x.torn} torn), ${x.untraded} untraded, ${x.tradedNoCandles} traded without candles, ${x.resultOther} without a yes/no result, ${x.replayable} replayable (${x.noStart} no start, ${x.startAfterClose} start at or after close)`);
    console.log(`  close day - begin day: ${JSON.stringify(x.lagDays)}`);
    console.log(`  begin to close (h): ${JSON.stringify(x.spanH)}`);
    console.log(`  late (2+ days) by cause: ${JSON.stringify(x.lateCause)}`);
  }
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) main();
