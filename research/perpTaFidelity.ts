// How well does Binance's USD-M perp history stand in for Kalshi's perps? (thread "Build a TA rulebook for
// perpetuals", Nov 5: history fidelity before deep history.) From the bot's recordings (real Kalshi perp quotes, k:'perp',
// and Coinbase spot, k:'spot'; never history-replay events) against Binance's 1-minute USD-M bars for the same minutes:
//
//   spread      Kalshi's quoted spread in bps of the mid (median, p75, p90): the half-spread the sweep charges per taker side
//   returns     correlation, slope and tracking error of Kalshi mid returns against Binance perp returns over 1, 5, 15
//               and 60 minutes: how much of a move measured on Binance a Kalshi position actually gets
//   units       Kalshi quotes perps per contract (BTC: 0.0001 BTC a contract): the mid per coin is the mid over the
//               contract size, checked against spot (a market that fits neither is reported as 'unknown', no premium)
//   premium     Kalshi's mid per coin against Coinbase spot and against the recorded settlement index (bps; median, p10, p90)
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

export interface FidelityTicker { ticker: string; quotes: number; medianMid: number; contractSize: number | null; firstDay: string; lastDay: string }

export interface FidelityAsset {
  asset: string; ticker: string; tickers: FidelityTicker[]; quotes: number; minutes: number; quoteEverySec: number;
  /** How Kalshi quotes this perp: per contract (price x contract size, as Kalshi documents), per coin, or unknown. */
  unit: { kind: 'per contract' | 'per coin' | 'unknown'; contractSize: number | null; observedScale: number };
  /** Minutes whose mid moved more than 10% from the minute before (bad prints): left out of returns and premium. */
  jumps: number;
  spot: { n: number; median: number; p01: number; p99: number };
  index: { n: number; src: string; median: number };
  spreadBps: { median: number; p75: number; p90: number; mean: number };
  returns: Record<string, { rho: number; beta: number; te: number; n: number }>;
  /** Kalshi mid per coin against Coinbase spot and against the recorded settlement index (bps; robust: median, p10, p90). */
  premiumBps: { median: number; p10: number; p90: number; n: number };
  premiumIndexBps: { median: number; p10: number; p90: number; n: number };
  funding: { kalshiSeen: number; kalshiZeroShare: number; kalshiZeroShareQuotes: number; kalshiMeanBps: number; pairs: number; modelMeanBps: number; modelZeroShare: number; corr: number; meanAbsDiffBps: number; noModel: number; verdict: string };
}

type Quote = [number, number, number, number]; // ts, bid, ask, funding rate
const day = (t: number) => new Date(t).toISOString().slice(0, 10);
const robust = (xs: number[]) => ({ median: +q(xs, 0.5).toFixed(2), p10: +q(xs, 0.1).toFixed(2), p90: +q(xs, 0.9).toFixed(2), n: xs.length });

export async function fidelity(o: { recordings: string; history: string; assets: string[]; from?: string; to?: string; log?: (m: string) => void }): Promise<{ days: string[]; assets: FidelityAsset[] }> {
  const log = o.log ?? console.log;
  const wanted = new Set(o.assets);
  // Per coin, per Kalshi ticker: quotes and the contract sizes they carried (a coin can list more than one market).
  const perp = new Map<string, Map<string, { qs: Quote[]; cs: number[] }>>();
  const spot = new Map<string, Array<[number, number]>>();
  const index = new Map<string, Map<string, Array<[number, number]>>>(); // coin -> src -> prints
  const days = new Set<string>();
  for await (const e of readRecordings(o.recordings, '', o.from, o.to, (k) => k === 'perp' || k === 'spot' || k === 'index')) {
    if (e.k === 'skip' || e.hist) continue;
    const a = e.asset as string | undefined;
    if (!a || !wanted.has(a)) continue;
    const ts = (e.ts ?? e.t) as number;
    if (e.k === 'perp' && e.bid > 0 && e.ask >= e.bid) {
      const byT = perp.get(a) ?? perp.set(a, new Map()).get(a)!;
      const tk = String(e.ticker ?? '?');
      const rec = byT.get(tk) ?? byT.set(tk, { qs: [], cs: [] }).get(tk)!;
      rec.qs.push([ts, e.bid, e.ask, fin(e.fundingRate) ? e.fundingRate : NaN]);
      if (fin(e.contractSize) && e.contractSize > 0) rec.cs.push(e.contractSize);
      days.add(day(ts));
    } else if (e.k === 'spot' && e.value > 0) (spot.get(a) ?? spot.set(a, []).get(a)!).push([ts, e.value]);
    else if (e.k === 'index' && e.value > 0) {
      const bySrc = index.get(a) ?? index.set(a, new Map()).get(a)!;
      const src = String(e.src ?? '?');
      (bySrc.get(src) ?? bySrc.set(src, []).get(src)!).push([ts, e.value]);
    }
  }
  const out: FidelityAsset[] = [];
  for (const a of o.assets) {
    const byT = perp.get(a);
    if (!byT || !byT.size) { log(`${a}: no Kalshi perp quotes in the recordings`); continue; }
    const tickers: FidelityTicker[] = [...byT].map(([ticker, r]) => {
      r.qs.sort((x, y) => x[0] - y[0]);
      return { ticker, quotes: r.qs.length, medianMid: +q(r.qs.map(([, b, k]) => (b + k) / 2), 0.5).toPrecision(6), contractSize: r.cs.length ? q(r.cs, 0.5) : null, firstDay: day(r.qs[0][0]), lastDay: day(r.qs[r.qs.length - 1][0]) };
    }).sort((x, y) => y.quotes - x.quotes);
    // The coin's main market (most quotes): mixing markets would put their price gap into the returns.
    const main = tickers[0], ps = byT.get(main.ticker)!.qs;
    const from = Math.floor(ps[0][0] / MIN) * MIN, to = Math.floor(ps[ps.length - 1][0] / MIN) * MIN;
    const spreads = ps.map(([, b, k]) => ((k - b) / ((k + b) / 2)) * 1e4);
    // Kalshi mid at each minute's end: the last quote inside the minute; minutes that jump > 10% are bad prints.
    const raw = new Map<number, number>();
    for (const [t, b, k] of ps) raw.set(Math.floor(t / MIN) * MIN, (b + k) / 2);
    const kMid = new Map<number, number>();
    let prev = NaN, jumps = 0;
    for (const [t, m] of raw) { if (fin(prev) && Math.abs(Math.log(m / prev)) > 0.1) { jumps++; continue; } kMid.set(t, m); prev = m; }
    // Spot and the settlement index by minute (the index source the bot used, the spot proxy only when nothing else).
    const sp = spot.get(a) ?? [];
    const sMin = new Map<number, number>();
    for (const [t, v] of sp) sMin.set(Math.floor(t / MIN) * MIN, v);
    const srcs = [...(index.get(a) ?? new Map<string, Array<[number, number]>>())].sort((x, y) => (x[0] === 'proxy' ? 1 : 0) - (y[0] === 'proxy' ? 1 : 0) || y[1].length - x[1].length);
    const [ixSrc, ixPrints] = srcs[0] ?? ['none', []];
    const iMin = new Map<number, number>();
    for (const [t, v] of ixPrints) iMin.set(Math.floor(t / MIN) * MIN, v);
    // Units: Kalshi documents prices per contract (BTC 0.0001 BTC per contract). Check against spot rather than assume.
    const ratios: number[] = [];
    for (const [t, m] of kMid) { const s2 = sMin.get(t) ?? iMin.get(t); if (s2) ratios.push(m / s2); }
    const scale = q(ratios, 0.5), cs = main.contractSize;
    const near = (x: number, y: number) => fin(x) && fin(y) && y > 0 && Math.abs(Math.log(x / y)) < Math.log(1.2);
    const kind: FidelityAsset['unit']['kind'] = cs !== null && near(scale, cs) ? 'per contract' : near(scale, 1) ? 'per coin' : 'unknown';
    const per = kind === 'per contract' ? cs! : kind === 'per coin' ? 1 : NaN;
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
    // Premium: the Kalshi mid per coin against Coinbase spot and against the settlement index, same minute.
    const prem: number[] = [], premIx: number[] = [];
    if (fin(per)) for (const [t, m] of kMid) {
      const s2 = sMin.get(t), ix = iMin.get(t);
      if (s2) prem.push(Math.log(m / per / s2) * 1e4);
      if (ix) premIx.push(Math.log(m / per / ix) * 1e4);
    }
    // Funding: the rate Kalshi quoted just before each funding instant against the model from Binance's settled rates.
    const fundFile = path.join(o.history, 'binance-funding', a, 'funding.csv');
    const binance: Array<[number, number]> = fs.existsSync(fundFile) ? fs.readFileSync(fundFile, 'utf8').split('\n').slice(1).filter(Boolean).map((l) => l.split(',').map(Number) as [number, number]) : [];
    const kRates = ps.filter((x) => fin(x[3])).map((x) => x[3]);
    const pairs: Array<[number, number]> = [];
    let pi = 0, noModel = 0;
    for (const tf of kalshiFundingTimes(from, to)) {
      while (pi + 1 < ps.length && ps[pi + 1][0] < tf) pi++;
      const kq = ps[pi];
      if (!kq || kq[0] > tf || tf - kq[0] > 10 * MIN || !fin(kq[3])) continue;
      const win = binance.filter(([t]) => t > tf - 8 * 3_600_000 && t <= tf);
      if (!win.length) { noModel++; continue; }
      pairs.push([kq[3], kalshiRateFromBinance(win.reduce((s, [, r]) => s + r, 0))]);
    }
    const kc = pairs.map((p) => p[0]), mc = pairs.map((p) => p[1]);
    const fc = corr(kc, mc);
    const quoteEvery = ps.length > 1 ? (ps[ps.length - 1][0] - ps[0][0]) / (ps.length - 1) / 1000 : NaN;
    const r: FidelityAsset = {
      asset: a, ticker: main.ticker, tickers, quotes: ps.length, minutes: kMid.size, quoteEverySec: +quoteEvery.toFixed(2),
      unit: { kind, contractSize: cs, observedScale: +scale.toPrecision(4) }, jumps,
      spot: { n: sp.length, median: +q(sp.map((x) => x[1]), 0.5).toPrecision(6), p01: +q(sp.map((x) => x[1]), 0.01).toPrecision(6), p99: +q(sp.map((x) => x[1]), 0.99).toPrecision(6) },
      index: { n: ixPrints.length, src: ixSrc, median: +q(ixPrints.map((x) => x[1]), 0.5).toPrecision(6) },
      spreadBps: { median: +q(spreads, 0.5).toFixed(2), p75: +q(spreads, 0.75).toFixed(2), p90: +q(spreads, 0.9).toFixed(2), mean: +mean(spreads).toFixed(2) },
      returns, premiumBps: robust(prem), premiumIndexBps: robust(premIx),
      funding: {
        // Zero shares at the funding instants on both sides (same denominator); the all-quotes share is kept apart.
        kalshiSeen: kRates.length, kalshiZeroShare: +(kc.filter((x) => Math.abs(x) < 1e-9).length / Math.max(1, kc.length)).toFixed(3), kalshiZeroShareQuotes: +(kRates.filter((x) => Math.abs(x) < 1e-9).length / Math.max(1, kRates.length)).toFixed(3), kalshiMeanBps: +(mean(kRates) * 1e4).toFixed(3),
        pairs: pairs.length, modelMeanBps: +(mean(mc) * 1e4).toFixed(3), modelZeroShare: +(mc.filter((x) => x === 0).length / Math.max(1, mc.length)).toFixed(3), corr: +fc.rho.toFixed(3),
        meanAbsDiffBps: +(mean(pairs.map(([x, y]) => Math.abs(x - y))) * 1e4).toFixed(3),
        // Binance publishes settled funding in monthly archives only: instants of the current month have no model rate.
        noModel: noModel, verdict: pairs.length < 30 ? 'insufficient (fewer than 30 instants with both rates)' : 'ok',
      },
    };
    log(`${a}: ${r.quotes} quotes (${r.quoteEverySec} s apart) over ${r.minutes} min; spread median ${r.spreadBps.median} bps (p90 ${r.spreadBps.p90}); 15m returns rho ${r.returns['15m'].rho} beta ${r.returns['15m'].beta} te ${r.returns['15m'].te} bps (n ${r.returns['15m'].n}); ${r.ticker} of ${tickers.length} market(s), quoted ${kind} (contract ${cs}, observed ${r.unit.observedScale}), ${jumps} jump minutes; premium vs spot median ${r.premiumBps.median} bps (p10 ${r.premiumBps.p10}, p90 ${r.premiumBps.p90}), vs index (${ixSrc}) ${r.premiumIndexBps.median}; funding Kalshi mean ${r.funding.kalshiMeanBps} bps (zero ${r.funding.kalshiZeroShare}) vs model ${r.funding.modelMeanBps} (zero ${r.funding.modelZeroShare}), ${r.funding.pairs} instants, |diff| ${r.funding.meanAbsDiffBps} bps`);
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
