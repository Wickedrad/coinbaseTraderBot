// How well does Binance's USD-M perp history stand in for Kalshi's perps? (thread "Build a TA rulebook for
// perpetuals", Nov 5: history fidelity before deep history.) From the bot's recordings (real Kalshi perp quotes, k:'perp',
// and Coinbase spot, k:'spot'; never history-replay events) against Binance's 1-minute USD-M bars for the same minutes:
//
//   spread      Kalshi's quoted spread in bps of the mid (median, p75, p90): the half-spread the sweep charges per taker side
//   returns     correlation, slope and tracking error of Kalshi mid returns against Binance perp returns over 1, 5, 15
//               and 60 minutes: how much of a move measured on Binance a Kalshi position actually gets
//   premium     Kalshi's mid against Coinbase spot (bps): the basis the funding pays for
//   funding     the funding rates Kalshi quoted against the sweep's model of them from Binance's settled rates
//               (research/perpTaSweep.ts kalshiRateFromBinance), at the same Kalshi funding instants
//
//   node --import tsx research/perpTaFidelity.ts --recordings data/recordings --history data/history --assets BTC,ETH,SOL,XRP --out fidelity.json

import fs from 'fs';
import path from 'path';
import { readRecordings } from './replay';
import { kalshiFundingTimes, kalshiRateFromBinance } from './perpTaSweep';

const MIN = 60_000;
const fin = Number.isFinite;
const q = (xs: number[], p: number) => { if (!xs.length) return NaN; const s = [...xs].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };
const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN);

function corr(a: number[], b: number[]): { rho: number; beta: number; te: number; n: number } {
  const n = a.length; if (n < 10) return { rho: NaN, beta: NaN, te: NaN, n };
  const ma = mean(a), mb = mean(b);
  let sab = 0, saa = 0, sbb = 0, d2 = 0;
  for (let i = 0; i < n; i++) { const x = a[i] - ma, y = b[i] - mb; sab += x * y; saa += x * x; sbb += y * y; d2 += (a[i] - b[i]) ** 2; }
  return { rho: sab / Math.sqrt(saa * sbb), beta: sab / sbb, te: Math.sqrt(d2 / n), n };
}

async function readUm(file: string, from: number, to: number): Promise<Map<number, number>> {
  const out = new Map<number, number>();
  if (!fs.existsSync(file)) return out;
  const readline = await import('readline');
  const rl = readline.createInterface({ input: fs.createReadStream(file), crlfDelay: Infinity });
  for await (const l of rl) { const f = l.split(','); const t = Number(f[0]); if (t >= from && t <= to) out.set(t, Number(f[4])); }
  return out;
}

export interface FidelityAsset {
  asset: string; quotes: number; minutes: number; quoteEverySec: number;
  spreadBps: { median: number; p75: number; p90: number; mean: number };
  returns: Record<string, { rho: number; beta: number; te: number; n: number }>;
  premiumBps: { mean: number; sd: number; n: number };
  funding: { kalshiSeen: number; kalshiZeroShare: number; kalshiMeanBps: number; pairs: number; modelMeanBps: number; modelZeroShare: number; corr: number; meanAbsDiffBps: number };
}

export async function fidelity(o: { recordings: string; history: string; assets: string[]; from?: string; to?: string; log?: (m: string) => void }): Promise<{ days: string[]; assets: FidelityAsset[] }> {
  const log = o.log ?? console.log;
  const wanted = new Set(o.assets);
  const perp = new Map<string, Array<[number, number, number, number]>>(); // ts, bid, ask, funding rate
  const spot = new Map<string, Array<[number, number]>>();
  const days = new Set<string>();
  for await (const e of readRecordings(o.recordings, '', o.from, o.to, (k) => k === 'perp' || k === 'spot')) {
    if (e.k === 'skip' || e.hist) continue;
    const a = e.asset as string | undefined;
    if (!a || !wanted.has(a)) continue;
    const ts = (e.ts ?? e.t) as number;
    if (e.k === 'perp' && e.bid > 0 && e.ask >= e.bid) { (perp.get(a) ?? perp.set(a, []).get(a)!).push([ts, e.bid, e.ask, fin(e.fundingRate) ? e.fundingRate : NaN]); days.add(new Date(ts).toISOString().slice(0, 10)); }
    else if (e.k === 'spot' && e.value > 0) (spot.get(a) ?? spot.set(a, []).get(a)!).push([ts, e.value]);
  }
  const out: FidelityAsset[] = [];
  for (const a of o.assets) {
    const ps = (perp.get(a) ?? []).sort((x, y) => x[0] - y[0]);
    if (!ps.length) { log(`${a}: no Kalshi perp quotes in the recordings`); continue; }
    const from = Math.floor(ps[0][0] / MIN) * MIN, to = Math.floor(ps[ps.length - 1][0] / MIN) * MIN;
    const spreads = ps.map(([, b, k]) => ((k - b) / ((k + b) / 2)) * 1e4);
    // Kalshi mid at each minute's end: the last quote inside the minute (fresh: within the minute itself).
    const kMid = new Map<number, number>();
    for (const [t, b, k] of ps) kMid.set(Math.floor(t / MIN) * MIN, (b + k) / 2);
    // Binance bar t closes at t + 1 min: the Kalshi mid of minute t is its last quote before t + 1 min.
    const um = await readUm(path.join(o.history, 'binance-um', a, '1m.csv'), from, to);
    const returns: FidelityAsset['returns'] = {};
    for (const h of [1, 5, 15, 60]) {
      const ka: number[] = [], ba: number[] = [];
      for (const [t, m] of kMid) {
        if (t % (h * MIN) !== 0) continue; // non-overlapping windows
        const m2 = kMid.get(t + h * MIN), b1 = um.get(t), b2 = um.get(t + h * MIN);
        if (!(m2 && b1 && b2)) continue;
        ka.push(Math.log(m2 / m) * 1e4); ba.push(Math.log(b2 / b1) * 1e4);
      }
      const c = corr(ka, ba);
      returns[`${h}m`] = { rho: +c.rho.toFixed(4), beta: +c.beta.toFixed(3), te: +c.te.toFixed(2), n: c.n };
    }
    // Premium against Coinbase spot: Kalshi mid vs the last spot print in the same minute.
    const sMin = new Map<number, number>();
    for (const [t, v] of spot.get(a) ?? []) sMin.set(Math.floor(t / MIN) * MIN, v);
    const prem: number[] = [];
    for (const [t, m] of kMid) { const s = sMin.get(t); if (s) prem.push((m / s - 1) * 1e4); }
    const pm = mean(prem), psd = Math.sqrt(mean(prem.map((x) => (x - pm) ** 2)));
    // Funding: the rate Kalshi quoted just before each funding instant against the model from Binance's settled rates.
    const fundFile = path.join(o.history, 'binance-funding', a, 'funding.csv');
    const binance: Array<[number, number]> = fs.existsSync(fundFile) ? fs.readFileSync(fundFile, 'utf8').split('\n').slice(1).filter(Boolean).map((l) => l.split(',').map(Number) as [number, number]) : [];
    const kRates = ps.filter((x) => fin(x[3])).map((x) => x[3]);
    const pairs: Array<[number, number]> = [];
    let pi = 0;
    for (const tf of kalshiFundingTimes(from, to)) {
      while (pi + 1 < ps.length && ps[pi + 1][0] < tf) pi++;
      const kq = ps[pi];
      if (!kq || kq[0] > tf || tf - kq[0] > 10 * MIN || !fin(kq[3])) continue;
      const win = binance.filter(([t]) => t > tf - 8 * 3_600_000 && t <= tf);
      if (!win.length) continue;
      pairs.push([kq[3], kalshiRateFromBinance(win.reduce((s, [, r]) => s + r, 0))]);
    }
    const kc = pairs.map((p) => p[0]), mc = pairs.map((p) => p[1]);
    const fc = corr(kc, mc);
    const quoteEvery = ps.length > 1 ? (ps[ps.length - 1][0] - ps[0][0]) / (ps.length - 1) / 1000 : NaN;
    const r: FidelityAsset = {
      asset: a, quotes: ps.length, minutes: kMid.size, quoteEverySec: +quoteEvery.toFixed(2),
      spreadBps: { median: +q(spreads, 0.5).toFixed(2), p75: +q(spreads, 0.75).toFixed(2), p90: +q(spreads, 0.9).toFixed(2), mean: +mean(spreads).toFixed(2) },
      returns, premiumBps: { mean: +pm.toFixed(2), sd: +psd.toFixed(2), n: prem.length },
      funding: {
        kalshiSeen: kRates.length, kalshiZeroShare: +(kRates.filter((x) => Math.abs(x) < 1e-9).length / Math.max(1, kRates.length)).toFixed(3), kalshiMeanBps: +(mean(kRates) * 1e4).toFixed(3),
        pairs: pairs.length, modelMeanBps: +(mean(mc) * 1e4).toFixed(3), modelZeroShare: +(mc.filter((x) => x === 0).length / Math.max(1, mc.length)).toFixed(3), corr: +fc.rho.toFixed(3),
        meanAbsDiffBps: +(mean(pairs.map(([x, y]) => Math.abs(x - y))) * 1e4).toFixed(3),
      },
    };
    log(`${a}: ${r.quotes} quotes (${r.quoteEverySec} s apart) over ${r.minutes} min; spread median ${r.spreadBps.median} bps (p90 ${r.spreadBps.p90}); 15m returns rho ${r.returns['15m'].rho} beta ${r.returns['15m'].beta} te ${r.returns['15m'].te} bps (n ${r.returns['15m'].n}); premium ${r.premiumBps.mean} +/- ${r.premiumBps.sd} bps; funding Kalshi mean ${r.funding.kalshiMeanBps} bps (zero ${r.funding.kalshiZeroShare}) vs model ${r.funding.modelMeanBps} (zero ${r.funding.modelZeroShare}), ${r.funding.pairs} instants, |diff| ${r.funding.meanAbsDiffBps} bps`);
    out.push(r);
  }
  return { days: [...days].sort(), assets: out };
}

async function main(): Promise<void> {
  const arg = (k: string, d?: string) => { const i = process.argv.indexOf(`--${k}`); return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : d; };
  const hist = arg('history', 'data/history')!, assets = arg('assets', 'BTC,ETH,SOL,XRP')!.split(',');
  const dl = arg('download-from'); // YYYY-MM: fetch Binance USD-M 1m bars and funding from that month first
  if (dl) {
    const { downloadBinance, downloadBinanceFunding } = await import('./history/binanceVision');
    const quiet = () => undefined;
    await downloadBinance({ out: hist, assets, intervals: ['1m'], markets: ['um'], fromMonth: dl, log: quiet, concurrency: 8 });
    await downloadBinanceFunding({ out: hist, assets, fromMonth: dl, log: quiet });
  }
  const res = await fidelity({ recordings: arg('recordings', 'data/recordings')!, history: hist, assets, from: arg('from'), to: arg('to'), log: (m) => console.log(`[perp-fidelity] ${m}`) });
  const out = arg('out');
  if (out) { fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true }); fs.writeFileSync(out, JSON.stringify(res, null, 1)); }
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) main().catch((e) => { console.error(e); process.exitCode = 1; });
