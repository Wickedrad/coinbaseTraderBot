// Perp TA rulebook sweep (thread "Build a TA rulebook for perpetuals", Steven 2026-11-05 13:31 UTC): which spot TA
// patterns, and which confluences of them, predict what a Kalshi perpetual does next, after the perps fees AND
// funding, by market condition, judged against placebos and on days the search never saw.
//
//   prep    node --import tsx research/perpTaSweep.ts prep --asset BTC --history data/history --out data/perp-ta
//           downloads what is missing (Binance spot 1m, USD-M 1m, funding, open interest) and writes one aligned
//           1-minute grid per coin (data/perp-ta/BTC.bin): spot o/h/l/c/v/taker-buy (the TA reads spot, as the live
//           setups trader does), the perp's o/h/l/c (trades are filled on the perp), the Kalshi funding model and OI.
//   sweep   node --import tsx research/perpTaSweep.ts sweep --data data/perp-ta/BTC.bin --out out/BTC.jsonl.gz
//           [--history data/history (the other coins' Binance hourly bars)] [--forecasts <server history> (.tanet-oos,
//           .librarian, .xgraph)] [--module-cache dir] [--modules false] [--pairs ctx|all]
//   report  node --import tsx research/perpTaSweep.ts report --in out --out report
//
// The sweep (sterile: textbook parameters, nothing fitted, every cell counted as a trial):
//   modules      the bot's own TA library on top (research/perpTaModules.ts): the analyzer's rules, rule book, 13
//                confluences and net vote, TA-Lib candlestick patterns and indicators, the TA Net / Librarian / cross-graph
//                walk-forward forecasts, and the character classifier, Librarian strategy, TA Net volatility and HT trend
//                mode as market conditions
//   primitives   ~120 TA readings (trend, mean reversion, volume / taker flow, candle patterns, squeeze and range
//                breakouts, and four perp readings: funding, premium, open interest) on 1m / 5m / 15m / 1h / 4h spot
//                bars, each -1 / 0 / +1 at the close of a bar of its own timeframe (closed bars only)
//   rules        trigger = a primitive turning to +1 or -1 at its bar's close; confluence = the trigger AND a context
//                filter (FILTERS: higher-timeframe trend, the analyzer's confluences, the forecasts...) agreeing then;
//                mode follow (trade the signal) or fade (trade against it: the TA veto found the crowd's side losing
//                on Kalshi)
//   execution    decided at the close of a 1-minute bar, entered at the next perp bar's open (taker 12 bps + half the
//                spread), one position per rule at a time; 12 exit policies in units of the 15-minute ATR: time stops
//                (5, 15, 60, 240 min, with a catastrophe stop), stop / target pairs (target = a resting maker sell,
//                5 bps), a trailing stop. Stops fill at the stop or a worse open, a bar touching both counts as the
//                stop. Funding: Kalshi's 00:00 / 08:00 / 16:00 New York times, modelled from Binance's settled rates
//                (Binance's rate less its 0.01% interest leg, Kalshi's |rate| < 0.01% => 0, cap 2%), signed (longs
//                pay a positive rate).
//   round 2      (ROUND, POLICIES_R2) entries as the live executor places them (bot/perps/hedger.ts: post-only maker, never
//                taker): pegged at the touch for 5 or 15 minutes, or resting 0.25 ATR off the decision close for 15, filled
//                at their price when the perp trades 1 bp through it, maker 5 bps, unfilled = no trade (the rule waits while
//                the order rests); x the 12 exits = 36 policies. Per-coin half-spreads and Kalshi's measured funding premium
//                over the model (--half-spread, --funding-offset; the workflow passes the fidelity medians), and a funding
//                stress in the report (paid x1.5, received x0.5). The bot's directional conviction (conv:*, perpTaModules.ts)
//                joins as trigger and filter.
//   round 3      (ROUND, POLICIES_R3) exits sized in 1-hour (H) and 4-hour (D) ATRs, holds of 4 hours to 7 days, no
//                trailing stop: 12 exits x MP15 / ML15 / ML60 (ML60: 0.25 x the 1-hour ATR off, resting 60 minutes) = 36
//                policies. Everything else as round 2. The round 2 report: the moves a 15-minute ATR exit tries to catch
//                (20-40 bps) are barely bigger than the round trip (10-17 bps), and random entries lose about that.
//   conditions   every trade also counts in its market condition at entry: trend / range (1h ADX 25), volatility
//                low / mid / high (24 h realised vs its 30-day mean), session (Asia 0-7, Europe 7-13, US 13-20, late
//                20-24 UTC), funding positive / zero / negative, weekday / weekend
//   folds        half-years; a trade whose exit falls in a later half-year than its entry is dropped (purge). The
//                discovery folds (before 2024) choose; the validation folds (2024-01 .. 2025-06) only confirm; the
//                bars from --seal (2025-07-01) on are never read by the sweep (the blind test's days)
//   stored       every tested cell (>= 30 discovery trades) is counted; cells with a discovery t >= 2.5 are written
//                with their per-fold sums, the reversed cell (other mode) and, for the strongest, a placebo: the
//                rule's own entries moved by whole days (60 shifts, time of day kept) through the same exits
// The report applies Benjamini-Hochberg over every tested cell of every coin, then the adversaries (placebo,
// reversed, stress costs, fold stability) and the validation folds, and a CSCV probability of overfitting.

import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import readline from 'readline';
import { modulePrims, MODULE_CONDS, NONE, type ModuleOut } from './perpTaModules';
import { regRow, controlArm, runRef } from './perpTaRegistry';
import { adx, atr, bollinger, cmf, donchian, ema, ichimoku, keltner, macd, mfi, obv, rsi, sma, stochastic, type Candle } from '../bot/ta/indicators';

const MIN = 60_000;
const DAY = 86_400_000;
const fin = Number.isFinite;

// ---------------------------------------------------------------------------------------------------------------
// Data: one aligned 1-minute grid per coin.

export const COLS = ['so', 'sh', 'sl', 'sc', 'sv', 'stb', 'po', 'ph', 'pl', 'pc', 'fund', 'oi', 'valid'] as const;
export type Col = (typeof COLS)[number];
export interface Grid { asset: string; t0: number; n: number; c: Record<Col, Float32Array>; fundRaw: Float32Array }

async function readCsv(file: string, onRow: (f: string[]) => void): Promise<void> {
  if (!fs.existsSync(file)) return;
  const rl = readline.createInterface({ input: fs.createReadStream(file), crlfDelay: Infinity });
  for await (const line of rl) { if (!line || line.startsWith('ts')) continue; onRow(line.split(',')); }
}

function firstTs(file: string): number | undefined {
  if (!fs.existsSync(file)) return undefined;
  const fd = fs.openSync(file, 'r'), buf = Buffer.alloc(4096);
  const n = fs.readSync(fd, buf, 0, 4096, 0); fs.closeSync(fd);
  for (const l of buf.subarray(0, n).toString('utf8').split('\n')) { const t = Number(l.split(',')[0]); if (fin(t) && t > 1e12) return t; }
  return undefined;
}
function lastTs(file: string): number | undefined {
  if (!fs.existsSync(file)) return undefined;
  const size = fs.statSync(file).size, fd = fs.openSync(file, 'r'), len = Math.min(size, 8192), buf = Buffer.alloc(len);
  fs.readSync(fd, buf, 0, len, size - len); fs.closeSync(fd);
  const ls = buf.toString('utf8').split('\n').filter(Boolean);
  for (let k = ls.length - 1; k >= 0; k--) { const t = Number(ls[k].split(',')[0]); if (fin(t) && t > 1e12) return t; }
  return undefined;
}

/** Kalshi's funding instants (00:00, 08:00, 16:00 America/New_York) between two times. */
export function kalshiFundingTimes(from: number, to: number): number[] {
  const hourNy = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: 'numeric', hourCycle: 'h23' });
  const out: number[] = [];
  for (let t = Math.ceil(from / 3_600_000) * 3_600_000; t <= to; t += 3_600_000) {
    const h = Number(hourNy.format(new Date(t)));
    if (h === 0 || h === 8 || h === 16) out.push(t);
  }
  return out;
}

/** Kalshi's rate at a funding instant from Binance's settled rates over the 8 hours before it: Binance's rate is the
 *  premium plus a 0.01%-per-8h interest leg Kalshi does not have; Kalshi zeroes |rate| < 0.01% and caps at 2%. */
export function kalshiRateFromBinance(binanceSum8h: number): number {
  const r = binanceSum8h - 0.0001;
  if (!(Math.abs(r) >= 0.0001)) return 0;
  return Math.max(-0.02, Math.min(0.02, r));
}

export async function buildGrid(hist: string, asset: string, log: (m: string) => void = console.log): Promise<Grid> {
  const fSpot = path.join(hist, 'binance-1m', asset, '1m.csv'), fPerp = path.join(hist, 'binance-um', asset, '1m.csv');
  const fFund = path.join(hist, 'binance-funding', asset, 'funding.csv'), fOi = path.join(hist, 'binance-oi', asset, 'oi.csv');
  const s0 = firstTs(fSpot), p0 = firstTs(fPerp), s1 = lastTs(fSpot), p1 = lastTs(fPerp);
  if (!s0 || !p0 || !s1 || !p1) throw new Error(`${asset}: missing ${!s0 || !s1 ? fSpot : fPerp}`);
  const t0 = Math.ceil(Math.max(s0, p0, Date.UTC(2020, 0, 1)) / DAY) * DAY, t1 = Math.min(s1, p1);
  const n = Math.floor((t1 - t0) / MIN) + 1;
  const c = Object.fromEntries(COLS.map((k) => [k, new Float32Array(n)])) as Record<Col, Float32Array>;
  const seenS = new Uint8Array(n), seenP = new Uint8Array(n);
  await readCsv(fSpot, (f) => {
    const i = (Number(f[0]) - t0) / MIN; if (!(i >= 0 && i < n && Number.isInteger(i))) return;
    c.so[i] = +f[1]; c.sh[i] = +f[2]; c.sl[i] = +f[3]; c.sc[i] = +f[4]; c.sv[i] = +f[5] || 0; c.stb[i] = f[6] !== undefined && f[6] !== '' ? +f[6] : NaN; seenS[i] = 1;
  });
  await readCsv(fPerp, (f) => {
    const i = (Number(f[0]) - t0) / MIN; if (!(i >= 0 && i < n && Number.isInteger(i))) return;
    c.po[i] = +f[1]; c.ph[i] = +f[2]; c.pl[i] = +f[3]; c.pc[i] = +f[4]; seenP[i] = 1;
  });
  // Missing minutes: a flat bar at the last close, no volume, not tradable.
  let gaps = 0;
  for (let i = 0; i < n; i++) {
    c.valid[i] = seenS[i] && seenP[i] && c.sc[i] > 0 && c.pc[i] > 0 ? 1 : 0;
    if (!seenS[i] || !(c.sc[i] > 0)) { const pc = i ? c.sc[i - 1] : NaN; c.so[i] = c.sh[i] = c.sl[i] = c.sc[i] = pc; c.sv[i] = 0; c.stb[i] = 0; }
    if (!seenP[i] || !(c.pc[i] > 0)) { const pc = i ? c.pc[i - 1] : NaN; c.po[i] = c.ph[i] = c.pl[i] = c.pc[i] = pc; }
    if (!c.valid[i]) gaps++;
  }
  // Funding: Binance's settled rates, then Kalshi's rate at each Kalshi instant (applied at the end of the minute
  // that ends at it: a position open across that instant pays or receives it).
  const binance: Array<[number, number]> = [];
  await readCsv(fFund, (f) => { const t = +f[0], r = +f[1]; if (fin(t) && fin(r)) binance.push([t, r]); });
  binance.sort((a, b) => a[0] - b[0]);
  const fundRaw = new Float32Array(n);
  let bi = 0, applied = 0;
  for (const tf of kalshiFundingTimes(t0 + MIN, t0 + n * MIN)) {
    while (bi < binance.length && binance[bi][0] <= tf - 8 * 3_600_000) bi++;
    let s = 0, k = bi, cnt = 0;
    for (; k < binance.length && binance[k][0] <= tf; k++) { s += binance[k][1]; cnt++; }
    if (!cnt) continue;
    const i = (tf - t0) / MIN - 1; // the minute that ends at tf
    if (i < 0 || i >= n) continue;
    // A zero-rate instant is stored as 1e-12 (no money moves) so "fund[i] !== 0" still marks every instant.
    c.fund[i] = kalshiRateFromBinance(s) || 1e-12; fundRaw[i] = s; applied++;
  }
  // Open interest (5-minute snapshots, from September 2020): carried forward to each minute's end.
  const oi: Array<[number, number]> = [];
  await readCsv(fOi, (f) => { const t = +f[0], v = +f[1]; if (fin(t) && v > 0) oi.push([t, v]); });
  oi.sort((a, b) => a[0] - b[0]);
  let oj = 0, cur = NaN;
  for (let i = 0; i < n; i++) {
    const end = t0 + (i + 1) * MIN;
    while (oj < oi.length && oi[oj][0] <= end) cur = oi[oj++][1];
    c.oi[i] = cur;
  }
  log(`${asset}: ${n} minutes ${new Date(t0).toISOString().slice(0, 10)} .. ${new Date(t0 + (n - 1) * MIN).toISOString().slice(0, 16)}, ${gaps} not tradable, ${applied} Kalshi funding instants (${binance.length} Binance rates), ${oi.length} OI snapshots`);
  return { asset, t0, n, c, fundRaw };
}

export function writeGrid(g: Grid, file: string): void {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const header = Buffer.from(JSON.stringify({ schema: 'perpta1', asset: g.asset, t0: g.t0, n: g.n, cols: [...COLS, 'fundRaw'] }) + '\n');
  const fd = fs.openSync(`${file}.tmp`, 'w');
  fs.writeSync(fd, header);
  for (const k of COLS) fs.writeSync(fd, Buffer.from(g.c[k].buffer, g.c[k].byteOffset, g.c[k].byteLength));
  fs.writeSync(fd, Buffer.from(g.fundRaw.buffer, g.fundRaw.byteOffset, g.fundRaw.byteLength));
  fs.closeSync(fd);
  fs.renameSync(`${file}.tmp`, file);
}

export function readGrid(file: string): Grid {
  const buf = fs.readFileSync(file);
  const nl = buf.indexOf(10);
  const h = JSON.parse(buf.subarray(0, nl).toString('utf8')) as { schema: string; asset: string; t0: number; n: number; cols: string[] };
  if (h.schema !== 'perpta1') throw new Error(`${file}: not a perp-ta grid`);
  let off = nl + 1;
  const take = () => { const a = new Float32Array(h.n); Buffer.from(a.buffer).set(buf.subarray(off, off + 4 * h.n)); off += 4 * h.n; return a; };
  const c = Object.fromEntries(COLS.map((k) => [k, take()])) as Record<Col, Float32Array>;
  return { asset: h.asset, t0: h.t0, n: h.n, c, fundRaw: take() };
}

// ---------------------------------------------------------------------------------------------------------------
// Bars of a timeframe from the 1-minute grid. Bar k of an m-minute timeframe covers minutes [k m, (k + 1) m) of the
// grid (which starts at a UTC midnight), so it is closed, and readable, at the end of minute (k + 1) m - 1.

export function aggregate(g: Grid, m: number, nMax = g.n): Candle[] {
  const { so, sh, sl, sc, sv, stb } = g.c;
  const out: Candle[] = [];
  for (let k = 0; (k + 1) * m <= nMax; k++) {
    const a = k * m, b = a + m;
    let h = -Infinity, l = Infinity, v = 0, tb = 0, tbOk = true;
    for (let i = a; i < b; i++) { if (sh[i] > h) h = sh[i]; if (sl[i] < l) l = sl[i]; v += sv[i]; const x = stb[i]; if (fin(x)) tb += x; else tbOk = false; }
    out.push({ ts: g.t0 + a * MIN, o: so[a], h, l, c: sc[b - 1], v, tb: tbOk ? tb : undefined });
  }
  return out;
}

// ---------------------------------------------------------------------------------------------------------------
// Primitives: -1 / 0 / +1 per bar of their timeframe, from that bar and earlier ones only.

type Fam = (cs: Candle[]) => Int8Array;
const sg = (x: number) => (x > 0 ? 1 : x < 0 ? -1 : 0);
const mk = (n: number, f: (i: number) => number): Int8Array => { const s = new Int8Array(n); for (let i = 0; i < n; i++) { const v = f(i); s[i] = v > 0 ? 1 : v < 0 ? -1 : 0; } return s; };
const closesOf = (cs: Candle[]) => cs.map((c) => c.c);

function rollingStd(xs: number[], n: number): Float64Array {
  const out = new Float64Array(xs.length).fill(NaN);
  let s = 0, s2 = 0, cnt = 0;
  for (let i = 0; i < xs.length; i++) {
    const x = xs[i]; if (fin(x)) { s += x; s2 += x * x; cnt++; }
    if (i >= n) { const y = xs[i - n]; if (fin(y)) { s -= y; s2 -= y * y; cnt--; } }
    if (cnt >= n * 0.8) { const m = s / cnt; out[i] = Math.sqrt(Math.max(0, s2 / cnt - m * m)); }
  }
  return out;
}

function supertrend(cs: Candle[], n = 10, mult = 3): Int8Array {
  const a = atr(cs, n), out = new Int8Array(cs.length);
  let up = NaN, dn = NaN, dir = 0;
  for (let i = 0; i < cs.length; i++) {
    if (!fin(a[i])) continue;
    const mid = (cs[i].h + cs[i].l) / 2, bu = mid + mult * a[i], bl = mid - mult * a[i];
    const pc = i ? cs[i - 1].c : cs[i].c;
    up = fin(up) && pc <= up ? Math.min(bu, up) : bu;
    dn = fin(dn) && pc >= dn ? Math.max(bl, dn) : bl;
    if (dir === 0) dir = cs[i].c >= mid ? 1 : -1;
    else if (dir > 0 && cs[i].c < dn) dir = -1;
    else if (dir < 0 && cs[i].c > up) dir = 1;
    out[i] = dir;
  }
  return out;
}

function sessionVwapDev(cs: Candle[]): Int8Array {
  const dev: number[] = new Array(cs.length).fill(NaN);
  let day = -1, pv = 0, vv = 0;
  for (let i = 0; i < cs.length; i++) {
    const d = Math.floor(cs[i].ts / DAY);
    if (d !== day) { day = d; pv = 0; vv = 0; }
    const tp = (cs[i].h + cs[i].l + cs[i].c) / 3; pv += tp * cs[i].v; vv += cs[i].v;
    if (vv > 0) dev[i] = cs[i].c / (pv / vv) - 1;
  }
  const sd = rollingStd(dev, 100);
  return mk(cs.length, (i) => { const z = dev[i] / sd[i]; return fin(z) ? (z < -2 ? 1 : z > 2 ? -1 : 0) : 0; });
}

function tsmom(cs: Candle[], n: number): Int8Array {
  const c = closesOf(cs), r1 = c.map((x, i) => (i ? Math.log(x / c[i - 1]) : NaN)), sd = rollingStd(r1, 100);
  return mk(cs.length, (i) => { if (i < n) return 0; const z = Math.log(c[i] / c[i - n]) / (sd[i] * Math.sqrt(n)); return fin(z) ? (z > 1 ? 1 : z < -1 ? -1 : 0) : 0; });
}

function tflow(cs: Candle[], n: number, th: number): Int8Array {
  return mk(cs.length, (i) => {
    if (i < n - 1) return 0;
    let tb = 0, v = 0;
    for (let j = i - n + 1; j <= i; j++) { const x = cs[j].tb; if (x === undefined || !fin(x)) return 0; tb += x; v += cs[j].v; }
    if (!(v > 0)) return 0;
    const imb = (2 * tb - v) / v;
    return imb > th ? 1 : imb < -th ? -1 : 0;
  });
}

export const FAMILIES: Record<string, Fam> = {
  emax9_21: (cs) => { const c = closesOf(cs), a = ema(c, 9), b = ema(c, 21); return mk(cs.length, (i) => (fin(a[i]) && fin(b[i]) ? a[i] - b[i] : 0)); },
  emax20_50: (cs) => { const c = closesOf(cs), a = ema(c, 20), b = ema(c, 50); return mk(cs.length, (i) => (fin(a[i]) && fin(b[i]) ? a[i] - b[i] : 0)); },
  px_ema200: (cs) => { const c = closesOf(cs), a = ema(c, 200); return mk(cs.length, (i) => (fin(a[i]) ? c[i] - a[i] : 0)); },
  macd_hist: (cs) => { const h = macd(closesOf(cs)).hist; return mk(cs.length, (i) => (fin(h[i]) ? h[i] : 0)); },
  adx_dir: (cs) => { const d = adx(cs); return mk(cs.length, (i) => (d.adx[i] >= 25 ? d.plusDI[i] - d.minusDI[i] : 0)); },
  donch20: (cs) => { const d = donchian(cs, 20); return mk(cs.length, (i) => (cs[i].c > d.upper[i] ? 1 : cs[i].c < d.lower[i] ? -1 : 0)); },
  donch55: (cs) => { const d = donchian(cs, 55); return mk(cs.length, (i) => (cs[i].c > d.upper[i] ? 1 : cs[i].c < d.lower[i] ? -1 : 0)); },
  tsmom12: (cs) => tsmom(cs, 12),
  tsmom48: (cs) => tsmom(cs, 48),
  supertrend: (cs) => supertrend(cs),
  ichimoku: (cs) => { const k = ichimoku(cs); return mk(cs.length, (i) => { const hi = Math.max(k.spanA[i], k.spanB[i]), lo = Math.min(k.spanA[i], k.spanB[i]); if (!fin(hi) || !fin(lo)) return 0; return cs[i].c > hi && k.tenkan[i] > k.kijun[i] ? 1 : cs[i].c < lo && k.tenkan[i] < k.kijun[i] ? -1 : 0; }); },
  rsi_mom: (cs) => { const r = rsi(closesOf(cs)); return mk(cs.length, (i) => (r[i] > 55 ? 1 : r[i] < 45 ? -1 : 0)); },
  rsi14_30: (cs) => { const r = rsi(closesOf(cs)); return mk(cs.length, (i) => (r[i] < 30 ? 1 : r[i] > 70 ? -1 : 0)); },
  rsi14_20: (cs) => { const r = rsi(closesOf(cs)); return mk(cs.length, (i) => (r[i] < 20 ? 1 : r[i] > 80 ? -1 : 0)); },
  rsi2_10: (cs) => { const r = rsi(closesOf(cs), 2); return mk(cs.length, (i) => (r[i] < 10 ? 1 : r[i] > 90 ? -1 : 0)); },
  bb20_2: (cs) => { const b = bollinger(closesOf(cs), 20, 2); return mk(cs.length, (i) => (cs[i].c < b.lower[i] ? 1 : cs[i].c > b.upper[i] ? -1 : 0)); },
  bb20_25: (cs) => { const b = bollinger(closesOf(cs), 20, 2.5); return mk(cs.length, (i) => (cs[i].c < b.lower[i] ? 1 : cs[i].c > b.upper[i] ? -1 : 0)); },
  stoch_x: (cs) => { const s = stochastic(cs); return mk(cs.length, (i) => (s.k[i] < 20 && s.k[i] > s.d[i] ? 1 : s.k[i] > 80 && s.k[i] < s.d[i] ? -1 : 0)); },
  vwap_dev: (cs) => sessionVwapDev(cs),
  keltner_bo: (cs) => { const k = keltner(cs); return mk(cs.length, (i) => (cs[i].c > k.upper[i] ? 1 : cs[i].c < k.lower[i] ? -1 : 0)); },
  tflow3: (cs) => tflow(cs, 3, 0.1),
  tflow12: (cs) => tflow(cs, 12, 0.05),
  vol_spike: (cs) => { const va = sma(cs.map((c) => c.v), 20); return mk(cs.length, (i) => (i > 0 && cs[i].v > 3 * va[i - 1] ? cs[i].c - cs[i].o : 0)); },
  obv_slope: (cs) => { const o = obv(cs), e = ema(o, 20); return mk(cs.length, (i) => (fin(e[i]) ? o[i] - e[i] : 0)); },
  cmf20: (cs) => { const m = cmf(cs); return mk(cs.length, (i) => (m[i] > 0.1 ? 1 : m[i] < -0.1 ? -1 : 0)); },
  mfi14: (cs) => { const m = mfi(cs); return mk(cs.length, (i) => (m[i] < 20 ? 1 : m[i] > 80 ? -1 : 0)); },
  engulf: (cs) => mk(cs.length, (i) => {
    if (i < 1) return 0; const a = cs[i - 1], b = cs[i];
    if (a.c < a.o && b.c > b.o && b.c >= a.o && b.o <= a.c && b.c - b.o > a.o - a.c) return 1;
    if (a.c > a.o && b.c < b.o && b.c <= a.o && b.o >= a.c && b.o - b.c > a.c - a.o) return -1;
    return 0;
  }),
  pinbar: (cs) => mk(cs.length, (i) => {
    const b = cs[i], r = b.h - b.l; if (!(r > 0)) return 0;
    const body = Math.abs(b.c - b.o), lw = Math.min(b.o, b.c) - b.l, uw = b.h - Math.max(b.o, b.c);
    if (lw >= 2 * body && lw >= 0.6 * r && b.c >= b.l + (2 / 3) * r) return 1;
    if (uw >= 2 * body && uw >= 0.6 * r && b.c <= b.l + (1 / 3) * r) return -1;
    return 0;
  }),
  inside_bo: (cs) => mk(cs.length, (i) => {
    if (i < 2) return 0; const m = cs[i - 2], p = cs[i - 1], b = cs[i];
    if (!(p.h <= m.h && p.l >= m.l)) return 0;
    return b.c > p.h ? 1 : b.c < p.l ? -1 : 0;
  }),
  fvg: (cs) => mk(cs.length, (i) => (i < 2 ? 0 : cs[i].l > cs[i - 2].h ? 1 : cs[i].h < cs[i - 2].l ? -1 : 0)),
  three_bar: (cs) => mk(cs.length, (i) => {
    if (i < 2) return 0; const a = cs[i - 2], b = cs[i - 1], c = cs[i];
    if (a.c > a.o && b.c > b.o && c.c > c.o && b.c > a.c && c.c > b.c) return 1;
    if (a.c < a.o && b.c < b.o && c.c < c.o && b.c < a.c && c.c < b.c) return -1;
    return 0;
  }),
  squeeze_bo: (cs) => {
    const c = closesOf(cs), b = bollinger(c, 20, 2), k = keltner(cs, 20, 1.5);
    const on = (i: number) => fin(b.upper[i]) && fin(k.upper[i]) && b.upper[i] < k.upper[i] && b.lower[i] > k.lower[i];
    return mk(cs.length, (i) => (i > 0 && on(i - 1) && !on(i) ? (c[i] > b.mid[i] ? 1 : c[i] < b.mid[i] ? -1 : 0) : 0));
  },
  nr7_bo: (cs) => mk(cs.length, (i) => {
    if (i < 8) return 0; const p = cs[i - 1], r = p.h - p.l;
    for (let j = i - 7; j < i - 1; j++) if (cs[j].h - cs[j].l <= r) return 0;
    return cs[i].c > p.h ? 1 : cs[i].c < p.l ? -1 : 0;
  }),
};

/** Which families run on which timeframe (minutes). 1m: the fast ones; 4h: trend context. */
const MAIN_TFS = [5, 15, 60];
const MAIN_FAMS = Object.keys(FAMILIES);
const FAST_FAMS = ['emax9_21', 'rsi2_10', 'bb20_2', 'tflow3', 'vol_spike', 'engulf', 'three_bar', 'fvg'];
const CTX_FAMS = ['emax20_50', 'px_ema200', 'adx_dir', 'supertrend', 'ichimoku', 'macd_hist'];

export interface Prim { id: string; fam: string; m: number; s: Int8Array }

/** Perp readings on the 1-minute grid (m = 1) or 5-minute bars: Kalshi funding (fade the crowded side), the perp's
 *  premium over spot (fade an extreme), open interest with price (new positions: follow), an open-interest flush
 *  (fade the move that flushed it). */
function perpPrims(g: Grid, nMax: number): Prim[] {
  const { fund, oi, sc, pc } = g.c;
  const fs1 = new Int8Array(nMax), oiPx = new Int8Array(nMax), oiFlush = new Int8Array(nMax);
  let last = 0;
  for (let i = 0; i < nMax; i++) {
    if (fund[i] !== 0) last = fund[i]; // an instant (zero-rate instants hold 1e-12)
    // The rate known at the end of minute i is the last instant's (one ending at i included).
    fs1[i] = last >= 0.0001 ? -1 : last <= -0.0001 ? 1 : 0;
    if (i >= 60 && oi[i] > 0 && oi[i - 60] > 0) {
      const d = oi[i] / oi[i - 60] - 1, r = sc[i] / sc[i - 60] - 1;
      oiPx[i] = d >= 0.015 ? (r > 0 ? 1 : r < 0 ? -1 : 0) : 0;
      oiFlush[i] = d <= -0.02 ? (r > 0 ? -1 : r < 0 ? 1 : 0) : 0;
    }
  }
  const m5 = 5, k5 = Math.floor(nMax / m5), prem: number[] = new Array(k5);
  for (let k = 0; k < k5; k++) { const i = (k + 1) * m5 - 1; prem[k] = pc[i] / sc[i] - 1; }
  const mu = sma(prem, 288), sd = rollingStd(prem, 288);
  const basis = mk(k5, (k) => { const z = (prem[k] - mu[k]) / sd[k]; return fin(z) ? (z > 2 ? -1 : z < -2 ? 1 : 0) : 0; });
  return [
    { id: 'perp_fund_fade@1m', fam: 'perp_fund', m: 1, s: fs1 },
    { id: 'perp_oi_px@1m', fam: 'perp_oi_px', m: 1, s: oiPx },
    { id: 'perp_oi_flush@1m', fam: 'perp_oi_flush', m: 1, s: oiFlush },
    { id: 'perp_basis_fade@5m', fam: 'perp_basis', m: 5, s: basis },
  ];
}

export function buildPrims(g: Grid, nMax: number, log: (m: string) => void = console.log): Prim[] {
  const out: Prim[] = [];
  const plan: Array<[number, string[]]> = [[1, FAST_FAMS], ...MAIN_TFS.map((m) => [m, MAIN_FAMS] as [number, string[]]), [240, CTX_FAMS]];
  for (const [m, fams] of plan) {
    const t = Date.now();
    const cs = aggregate(g, m, nMax);
    for (const f of fams) out.push({ id: `${f}@${m}m`, fam: f, m, s: FAMILIES[f](cs) });
    log(`primitives @${m}m: ${fams.length} on ${cs.length} bars in ${((Date.now() - t) / 1000).toFixed(1)} s`);
  }
  out.push(...perpPrims(g, nMax));
  return out;
}

/** State of a primitive at the end of minute i (its last bar closed by then). */
export const stateAt = (p: Prim, i: number): number => { const k = Math.floor((i + 1) / p.m) - 1; return k >= 0 && k < p.s.length ? p.s[k] : 0; };

/** Trigger minutes: the primitive's bar closes on a new nonzero reading (edge-triggered). */
export function triggers(p: Prim, valid: Float32Array, nMax: number): { idx: Int32Array; dir: Int8Array } {
  const idx: number[] = [], dir: number[] = [];
  for (let k = 1; k < p.s.length; k++) {
    const v = p.s[k];
    if (v === 0 || v === p.s[k - 1]) continue;
    const i = (k + 1) * p.m - 1;
    if (i + 1 >= nMax || !valid[i] || !valid[i + 1]) continue;
    idx.push(i); dir.push(v);
  }
  return { idx: Int32Array.from(idx), dir: Int8Array.from(dir) };
}

// ---------------------------------------------------------------------------------------------------------------
// Exits and costs.

/** How a trade is entered. Absent (round 1): taker at the next perp bar's open, paying the taker fee and half the spread.
 *  Round 2 enters as the live executor does (bot/perps/hedger.ts: post-only maker orders, never taker):
 *    peg    a post-only order at the touch (the bid for a long, the ask for a short), re-pegged at every minute's open to
 *           the last perp close less (long) / plus (short) the coin's half-spread, resting up to w minutes
 *    limit  a post-only order off x the 15-minute ATR below (long) / above (short) the decision minute's close, w minutes
 *  A resting order fills when the perp trades ttBps THROUGH its price (a bare touch does not fill an order at the back of
 *  the queue), at its price, paying the maker fee. An order that does not fill is cancelled after w minutes: no trade,
 *  and the rule takes no other entry while it rests. */
export interface Entry { kind: 'peg' | 'limit'; w: number; off?: number; /** the ATR timeframe (minutes) of off; 15 if absent */ tf?: number }
/** sl / tp / trail in ATRs of the policy's timeframe tf (minutes: 15 if absent; round 3 uses 60 and 240). */
export interface Policy { id: string; sl: number; tp: number; max: number; trail?: number; entry?: Entry; tf?: number }
/** The 12 exits (round 1's policies: taker entries). */
export const EXITS: Policy[] = [
  { id: 'T5', sl: 3, tp: 0, max: 5 },
  { id: 'T15', sl: 3, tp: 0, max: 15 },
  { id: 'T60', sl: 3, tp: 0, max: 60 },
  { id: 'T240', sl: 4, tp: 0, max: 240 },
  { id: 'S.5T1', sl: 0.5, tp: 1, max: 60 },
  { id: 'S1T1', sl: 1, tp: 1, max: 120 },
  { id: 'S1T2', sl: 1, tp: 2, max: 240 },
  { id: 'S2T2', sl: 2, tp: 2, max: 240 },
  { id: 'S3T1', sl: 3, tp: 1, max: 240 },
  { id: 'S1.5T3', sl: 1.5, tp: 3, max: 480 },
  { id: 'S2T4', sl: 2, tp: 4, max: 960 },
  { id: 'TR1.5', sl: 1.5, tp: 0, max: 480, trail: 1.5 },
];
export const ENTRIES: Array<{ tag: string; entry: Entry }> = [
  { tag: 'MP5', entry: { kind: 'peg', w: 5 } },
  { tag: 'MP15', entry: { kind: 'peg', w: 15 } },
  { tag: 'ML15', entry: { kind: 'limit', w: 15, off: 0.25 } },
];
export const POLICIES_R1: Policy[] = EXITS;
/** Round 2: every maker entry with every exit (36 policies, id "<entry>:<exit>"). */
export const POLICIES_R2: Policy[] = ENTRIES.flatMap(({ tag, entry }) => EXITS.map((x) => ({ ...x, id: `${tag}:${x.id}`, entry })));
/** Round 3: exits sized in 1-hour (H) and 4-hour (D) ATRs, holds of 4 hours to 7 days (no trailing stop). */
export const EXITS_R3: Policy[] = [
  { id: 'HT240', tf: 60, sl: 3, tp: 0, max: 240 },
  { id: 'HT1440', tf: 60, sl: 3, tp: 0, max: 1440 },
  { id: 'HS1T1', tf: 60, sl: 1, tp: 1, max: 1440 },
  { id: 'HS1T2', tf: 60, sl: 1, tp: 2, max: 2880 },
  { id: 'HS2T2', tf: 60, sl: 2, tp: 2, max: 2880 },
  { id: 'HS3T1', tf: 60, sl: 3, tp: 1, max: 2880 },
  { id: 'HS1.5T3', tf: 60, sl: 1.5, tp: 3, max: 4320 },
  { id: 'HS2T4', tf: 60, sl: 2, tp: 4, max: 5760 },
  { id: 'DT1440', tf: 240, sl: 3, tp: 0, max: 1440 },
  { id: 'DS1T1', tf: 240, sl: 1, tp: 1, max: 2880 },
  { id: 'DS1T2', tf: 240, sl: 1, tp: 2, max: 5760 },
  { id: 'DS2T4', tf: 240, sl: 2, tp: 4, max: 10080 },
];
export const ENTRIES_R3: Array<{ tag: string; entry: Entry }> = [
  { tag: 'MP15', entry: { kind: 'peg', w: 15 } },
  { tag: 'ML15', entry: { kind: 'limit', w: 15, off: 0.25 } },
  { tag: 'ML60', entry: { kind: 'limit', w: 60, off: 0.25, tf: 60 } },
];
export const POLICIES_R3: Policy[] = ENTRIES_R3.flatMap(({ tag, entry }) => EXITS_R3.map((x) => ({ ...x, id: `${tag}:${x.id}`, entry })));
export const ROUND = 3;
/** The policies this round's sweep walks. The study and the blind test read a run's own from its header. */
export const POLICIES: Policy[] = POLICIES_R3;
/** Every round's policies, for looking a policy up by id (the ids differ between rounds). */
export const POLICIES_ALL: Policy[] = [...POLICIES_R3, ...POLICIES_R2, ...POLICIES_R1];
/** The entry tags of every round (fill-share reporting). */
export const ENTRY_TAGS: string[] = [...new Set([...ENTRIES_R3, ...ENTRIES].map((e) => e.tag))];

/** ttBps: how far price must trade THROUGH a resting order (a target, or a maker entry) before it counts as filled (a bare
 *  touch of the Binance high or low does not fill a maker order at the back of the queue).
 *  fundOffsetBps: added to the modelled Kalshi rate at every funding instant (bps per 8 h, + = longs pay more): Kalshi's
 *  measured premium over the Binance-based model (research/perpTaFidelity.ts, Oct 21 - Nov 3 2026: BTC 1.66, ETH 1.19,
 *  SOL 0.14, XRP 1.57). fundMult multiplies the rate (a stress; 1 = none). */
export interface Costs { takerBps: number; makerBps: number; halfSpreadBps: number; ttBps?: number; fundOffsetBps?: number; fundMult?: number }
export const KALSHI_COSTS: Costs = { takerBps: 12, makerBps: 5, halfSpreadBps: 2, ttBps: 1 };

/** The ATR(14) of tf-minute bars (15 by default) as a fraction of price, known at the end of each minute (last closed bar). */
export function atrUnit(g: Grid, nMax: number, tf = 15): Float32Array {
  const cs = aggregate(g, tf, nMax), a = atr(cs, 14), out = new Float32Array(nMax);
  for (let i = 0; i < nMax; i++) { const k = Math.floor((i + 1) / tf) - 1; const v = k >= 0 ? a[k] / cs[k].c : NaN; out[i] = fin(v) ? Math.max(0.001, Math.min(0.05, v)) : NaN; }
  return out;
}

/** The funding applied at the end of each minute (a fraction of notional, + = longs pay), cumulated: cum[i + 1] = the
 *  funding at the ends of minutes 0..i. The grid marks every instant (a zero rate as 1e-12); the offset and the stress
 *  apply at instants only. */
export function fundingCum(g: Grid, nMax: number, costs: Costs): Float64Array {
  const fund = g.c.fund, off = (costs.fundOffsetBps ?? 0) / 1e4, mult = costs.fundMult ?? 1;
  const cum = new Float64Array(nMax + 1);
  for (let i = 0; i < nMax; i++) { const f = fund[i]; cum[i + 1] = cum[i] + (fin(f) && f !== 0 ? ((Math.abs(f) < 1e-9 ? 0 : f) + off) * mult : 0); }
  return cum;
}

export interface Outcomes {
  /** Per policy and direction (index policy * 2 + (long ? 0 : 1)), indexed by the decision minute i: net bps, NaN = no trade. */
  net: Float32Array[];
  /** The minute the position is flat again; for a maker entry that never filled, the minute its order was cancelled
   *  (net NaN); -1 = not tradable. */
  exit: Int32Array[];
  /** Minutes in the position (from the fill minute to the exit minute, both counted). */
  hold: Uint16Array[];
  /** fundingCum: a trade's funding is d * (cum[exit] - cum[exit - hold + 1]). */
  cum: Float64Array;
  /** Maker entries: orders placed (a full window of tradable minutes, or a fill before a gap) and filled. */
  fills: Array<{ tried: number; filled: number }>;
}

/** Outcome tables: for each policy and direction, the net result (bps of notional) of a trade decided at the end of
 *  minute i and the minute it is flat again. A taker entry fills at the open of minute i + 1; a maker entry (Entry) at
 *  its price in the first minute that trades through it. In a maker entry's fill minute only the stop is judged (the
 *  minute's range came partly before the fill: a bar reaching the stop counts as stopped, its target is never credited).
 *  NaN = not tradable, not filled, or not finished before nMax. unit = the 15-minute ATR (atrUnit); a policy or entry with
 *  another tf gets atrUnit(g, nMax, tf). The exit scan skips whole 64- and 4096-minute blocks that neither a fixed stop nor
 *  the target can touch (exact; opts.noSkip scans minute by minute, for the tests). */
export function outcomes(g: Grid, nMax: number, unit: Float32Array, costs: Costs, pols: Policy[] = POLICIES, opts: { noSkip?: boolean } = {}): Outcomes {
  const { po, ph, pl, pc, valid } = g.c;
  const cum = fundingCum(g, nMax, costs);
  const units = new Map<number, Float32Array>([[15, unit]]);
  const unitOf = (tf = 15): Float32Array => { let u = units.get(tf); if (!u) { u = atrUnit(g, nMax, tf); units.set(tf, u); } return u; };
  // Block lows / highs over the perp bars and whether every minute of the block is valid: B1 = 64, B2 = 4096 minutes.
  const S1 = 6, S2 = 12, n1 = nMax >> S1, n2 = nMax >> S2;
  const lo1 = new Float32Array(n1), hi1 = new Float32Array(n1), ok1 = new Uint8Array(n1), lo2 = new Float32Array(n2), hi2 = new Float32Array(n2), ok2 = new Uint8Array(n2);
  if (!opts.noSkip) {
    for (let b = 0; b < n1; b++) { let l = Infinity, h = -Infinity, ok = 1; for (let j = b << S1, e = j + (1 << S1); j < e; j++) { if (!valid[j]) ok = 0; if (pl[j] < l) l = pl[j]; if (ph[j] > h) h = ph[j]; } lo1[b] = l; hi1[b] = h; ok1[b] = ok; }
    const r = 1 << (S2 - S1);
    for (let b = 0; b < n2; b++) { let l = Infinity, h = -Infinity, ok = 1; for (let c = b * r, e = c + r; c < e; c++) { if (!ok1[c]) ok = 0; if (lo1[c] < l) l = lo1[c]; if (hi1[c] > h) h = hi1[c]; } lo2[b] = l; hi2[b] = h; ok2[b] = ok; }
  }
  const M1 = (1 << S1) - 1, M2 = (1 << S2) - 1;
  const net: Float32Array[] = [], exit: Int32Array[] = [], hold: Uint16Array[] = [], fills: Outcomes['fills'] = [];
  const takerSide = costs.takerBps + costs.halfSpreadBps, makerSide = costs.makerBps, tt = (costs.ttBps ?? 1) / 1e4, h = costs.halfSpreadBps / 1e4;
  for (const p of pols) for (const d of [1, -1]) {
    const nt = new Float32Array(nMax).fill(NaN), ex = new Int32Array(nMax).fill(-1), hd = new Uint16Array(nMax);
    // The exit's ATR (the policy's tf) and the entry offset's own (its tf, 15 if absent: ML15 stays 0.25 x the 15-minute ATR).
    const en = p.entry, U = unitOf(p.tf), UE = en ? unitOf(en.tf ?? 15) : U;
    const skip = !opts.noSkip && !p.trail;
    let tried = 0, filled = 0;
    for (let i = 0; i + 1 < nMax; i++) {
      const A = U[i], AE = UE[i];
      if (!valid[i] || !valid[i + 1] || !(A > 0) || !(AE > 0)) continue;
      let e = i + 1, P0 = po[e], entryCost = takerSide, fillMinute = false;
      if (en) {
        if (i + en.w >= nMax) continue;
        const lim = en.kind === 'limit' ? pc[i] * (1 - d * (en.off ?? 0) * AE) : NaN;
        let f = -1, bad = false;
        for (let j = i + 1; j <= i + en.w; j++) {
          if (!valid[j]) { bad = true; break; } // the book is unknown across missing minutes: no trade
          const q = en.kind === 'peg' ? pc[j - 1] * (1 - d * h) : lim;
          if (!(q > 0)) { bad = true; break; }
          if (d > 0 ? pl[j] <= q * (1 - tt) : ph[j] >= q * (1 + tt)) { f = j; P0 = q; break; }
        }
        if (bad) continue;
        tried++;
        if (f < 0) { ex[i] = i + en.w; continue; } // not filled: cancelled at the end of minute i + w
        filled++;
        e = f; entryCost = makerSide; fillMinute = true;
      }
      if (!(P0 > 0)) continue;
      let stop = P0 * (1 - d * p.sl * A);
      const tpPx = p.tp > 0 ? P0 * (1 + d * p.tp * A) : NaN;
      const last = e + p.max - 1;
      if (last >= nMax) continue;
      let fill = NaN, maker = false, j = e, best = P0, gap = false;
      if (fillMinute) {
        // A minute that opened through the stop (the resting order filled at its price on the way) exits at the open.
        if (d > 0 ? pl[e] <= stop : ph[e] >= stop) fill = (d > 0 ? po[e] < stop : po[e] > stop) ? po[e] : stop;
        else {
          if (p.trail) { if (d > 0 ? pc[e] > best : pc[e] < best) best = pc[e]; const ts = best * (1 - d * p.trail * A); if (d > 0 ? ts > stop : ts < stop) stop = ts; }
          j = e + 1;
        }
      }
      // The levels a minute must reach to end the trade (a fixed stop and target: no trailing stop when skipping).
      const tpHit = p.tp > 0 ? (d > 0 ? tpPx * (1 + tt) : tpPx * (1 - tt)) : NaN;
      if (fill !== fill) for (; j <= last; j++) {
        if (skip && (j & M1) === 0) {
          // A whole block (inside the hold) that is valid and neither reaches the stop nor the target is passed over.
          if ((j & M2) === 0 && j + M2 <= last) { const b = j >> S2; if (ok2[b] && (d > 0 ? lo2[b] > stop && !(hi2[b] >= tpHit) : hi2[b] < stop && !(lo2[b] <= tpHit))) { j += M2; continue; } }
          if (j + M1 <= last) { const b = j >> S1; if (ok1[b] && (d > 0 ? lo1[b] > stop && !(hi1[b] >= tpHit) : hi1[b] < stop && !(lo1[b] <= tpHit))) { j += M1; continue; } }
        }
        // A trade open across missing minutes (forward-filled flat bars) cannot be judged: dropped.
        if (!valid[j]) { gap = true; break; }
        if (d > 0) {
          if (pl[j] <= stop) { fill = j > e && po[j] < stop ? po[j] : stop; break; }
          if (p.tp > 0 && ph[j] >= tpPx * (1 + tt)) { fill = tpPx; maker = true; break; }
          if (p.trail) { if (pc[j] > best) best = pc[j]; const ts = best * (1 - p.trail * A); if (ts > stop) stop = ts; }
        } else {
          if (ph[j] >= stop) { fill = j > e && po[j] > stop ? po[j] : stop; break; }
          if (p.tp > 0 && pl[j] <= tpPx * (1 - tt)) { fill = tpPx; maker = true; break; }
          if (p.trail) { if (pc[j] < best) best = pc[j]; const ts = best * (1 + p.trail * A); if (ts < stop) stop = ts; }
        }
      }
      if (gap) continue;
      if (j > last) { j = last; fill = pc[last]; }
      // Funding at the ends of minutes e .. j - 1 (a position exited during or at the close of minute j is flat
      // before the instant that ends it).
      const fundBps = d * (cum[j] - cum[e]) * 1e4;
      nt[i] = d * (fill / P0 - 1) * 1e4 - entryCost - (maker ? makerSide : takerSide) - fundBps;
      ex[i] = j; hd[i] = Math.min(65535, j - e + 1);
    }
    net.push(nt); exit.push(ex); hold.push(hd); fills.push({ tried, filled });
  }
  return { net, exit, hold, cum, fills };
}

// ---------------------------------------------------------------------------------------------------------------
// Conditions and folds.

export const BASE_CONDS = ['all', 'trend', 'range', 'vol_low', 'vol_mid', 'vol_high', 'asia', 'europe', 'us', 'late', 'fund_pos', 'fund_zero', 'fund_neg', 'weekday', 'weekend'];
/** Base conditions, then the bot modules' (research/perpTaModules.ts: character, Librarian strategy, TA Net volatility, HT trend mode). */
export const CONDS = [...BASE_CONDS, ...MODULE_CONDS];
export const NCOND = CONDS.length;
/** Condition slots per minute: 5 base (always set) and 4 module slots (NONE when the module has no reading). */
export const NZ = 9;

/** Per minute, the NZ condition cells (besides 'all') a trade entered then counts in (NONE = no cell in that slot). */
export function conditions(g: Grid, nMax: number, mod?: ModuleOut): Uint8Array {
  const out = new Uint8Array(nMax * NZ).fill(NONE);
  const B = BASE_CONDS.length, mh = mod?.hourly;
  const h1 = aggregate(g, 60, nMax), a = adx(h1).adx;
  const { sc, fund } = g.c;
  // 24 h realised volatility of 1-minute log returns, against its own 30-day mean (both trailing).
  const W = 1440, M = 30 * 1440;
  const rv = new Float64Array(nMax).fill(NaN);
  let s2 = 0;
  for (let i = 1; i < nMax; i++) {
    const r = Math.log(sc[i] / sc[i - 1]); s2 += fin(r) ? r * r : 0;
    if (i > W) { const q = Math.log(sc[i - W] / sc[i - W - 1]); s2 -= fin(q) ? q * q : 0; }
    if (i >= W) rv[i] = Math.sqrt(Math.max(0, s2) / W);
  }
  let sm = 0, cnt = 0;
  let lastFund = 0;
  for (let i = 0; i < nMax; i++) {
    if (fin(rv[i])) { sm += rv[i]; cnt++; }
    if (i >= M && fin(rv[i - M])) { sm -= rv[i - M]; cnt--; }
    const k = Math.floor((i + 1) / 60) - 1;
    const trend = k >= 0 && a[k] >= 25 ? 0 : 1; // cells 1 trend, 2 range
    const ratio = cnt > 1440 ? rv[i] / (sm / cnt) : NaN;
    const vol = !fin(ratio) ? 1 : ratio < 0.8 ? 0 : ratio > 1.25 ? 2 : 1;
    const ts = g.t0 + (i + 1) * MIN, hr = new Date(ts).getUTCHours(), wd = new Date(ts).getUTCDay();
    const sess = hr < 7 ? 0 : hr < 13 ? 1 : hr < 20 ? 2 : 3;
    if (fund[i] !== 0) lastFund = fund[i];
    const f = lastFund >= 0.0001 ? 0 : lastFund <= -0.0001 ? 2 : 1;
    const o = i * NZ;
    out[o] = 1 + trend; out[o + 1] = 3 + vol; out[o + 2] = 6 + sess; out[o + 3] = 10 + f; out[o + 4] = wd === 0 || wd === 6 ? 14 : 13;
    if (mh && k >= 0) {
      const a = [mh.char[k], mh.lib[k], mh.vol[k], mh.ht[k]];
      for (let z = 0; z < 4; z++) if (a[z] !== undefined && a[z] !== NONE) out[o + 5 + z] = B + a[z];
    }
  }
  return out;
}

export interface Folds { starts: number[]; labels: string[]; of: Int8Array; discovery: number; }
/** Half-year folds from the grid's start to nMax; folds starting before `validFrom` are discovery. */
export function folds(g: Grid, nMax: number, validFrom: number): Folds {
  const starts: number[] = [], labels: string[] = [];
  const d0 = new Date(g.t0);
  let y = d0.getUTCFullYear(), h = d0.getUTCMonth() < 6 ? 0 : 1;
  for (;;) {
    const t = Date.UTC(y, h * 6, 1), i = Math.max(0, Math.round((t - g.t0) / MIN));
    if (i >= nMax) break;
    starts.push(i); labels.push(`${y}H${h + 1}`);
    if (h === 1) { y++; h = 0; } else h = 1;
  }
  const of = new Int8Array(nMax);
  let f = 0;
  for (let i = 0; i < nMax; i++) { while (f + 1 < starts.length && i >= starts[f + 1]) f++; of[i] = f; }
  const vi = Math.round((validFrom - g.t0) / MIN);
  return { starts, labels, of, discovery: starts.filter((s) => s < vi).length };
}

// ---------------------------------------------------------------------------------------------------------------
// The sweep.

const NPOL = POLICIES.length;
const NCELL = 2 * NPOL * 2 * NCOND; // mode x policy x signal side x condition
// Per fold: n, sum, sumsq, wins, hold minutes, sum and sum of squares of the excess over random entries, and the sum of the
// random entries' variance at each trade (the variance floor: a small target with a rare large stop can go 50 trades without
// a stop and show a tiny sample variance; the t statistics never use less than what a random entry with that exit varies),
// and the funding paid (bps, signed: + = paid) and its absolute value (the funding stress).
const NS = 10;
const cellIdx = (mode: number, p: number, side: number, c: number) => ((mode * NPOL + p) * 2 + side) * NCOND + c;

export interface CellRec {
  a: string; rule: string; mode: 'follow' | 'fade'; pol: string; side: 'long' | 'short'; cond: string;
  /** Per fold: [n, sum bps, sum of squares, wins, hold minutes, sum of excess bps, its sum of squares, sum of the random
   *  entries' variance at each trade, funding paid (bps, + = paid), its absolute value] (round 1 records stop at 8). */
  f: number[][];
  /** Discovery: net bps per trade and its t, and the excess over entering at a random minute of the same month in
   *  the same condition with the same exit and side (exc, tExc: what the signal adds; drift and fees cancel). */
  disc: { n: number; mean: number; t: number; hit: number; exc: number; tExc: number };
  /** The same cell traded the other way (the other mode): what a reversed signal does. */
  rev: { n: number; mean: number; t: number; exc?: number; tExc?: number };
  placebo?: { pct: number; mean: number; sd: number; shifts: number };
}

function discStats(acc: Float64Array, base: number, nf: number): { n: number; mean: number; t: number; hit: number; exc: number; tExc: number } {
  let n = 0, s = 0, s2 = 0, w = 0, e = 0, e2 = 0, vb = 0;
  for (let f = 0; f < nf; f++) { const o = base + f * NS; n += acc[o]; s += acc[o + 1]; s2 += acc[o + 2]; w += acc[o + 3]; e += acc[o + 5]; e2 += acc[o + 6]; vb += acc[o + 7]; }
  if (n < 2) return { n, mean: n ? s / n : NaN, t: NaN, hit: n ? w / n : NaN, exc: n ? e / n : NaN, tExc: NaN };
  const floor = Math.max(1e-9, vb / n);
  const mean = s / n, v = Math.max(floor, (s2 - n * mean * mean) / (n - 1));
  const em = e / n, ev = Math.max(floor, (e2 - n * em * em) / (n - 1));
  return { n, mean, t: mean / Math.sqrt(v / n), hit: w / n, exc: em, tExc: em / Math.sqrt(ev / n) };
}

export interface RuleDef { id: string; trig: number; filt: number }

/** Which part of the library a primitive comes from (the report's funnel by source). */
export const sourceOf = (id: string): string => (id.startsWith('ta:') ? 'analyzer rule' : id.startsWith('book:') ? 'rule book' : id.startsWith('conf:') || id === 'ta_net' ? 'confluence'
  : id.startsWith('conv:') ? 'conviction' : /^(cdl_|tl_)/.test(id) ? 'TA-Lib' : /^(tanet_|lib_|xg_)/.test(id) ? 'TA Net / Librarian / cross graph' : id.startsWith('perp_') ? 'perp' : 'classic TA');

/** Context filters a trigger is paired with (a confluence = trigger AND filter agreeing): higher-timeframe trend, the
 *  analyzer's trend / structure / momentum readings, its 13 confluences and net vote, the forecasts, perp readings. */
export const FILTERS = [
  'emax20_50@240m', 'px_ema200@240m', 'adx_dir@240m', 'supertrend@240m', 'ichimoku@240m', 'macd_hist@240m',
  'emax20_50@60m', 'supertrend@60m', 'donch55@60m', 'tsmom12@60m', 'tsmom48@60m', 'vwap_dev@15m', 'tflow12@15m',
  'perp_fund_fade@1m', 'perp_basis_fade@5m', 'perp_oi_px@1m',
  'ta_net', 'ta:ema_stack@1h', 'ta:ema_stack@4h', 'ta:ma_regime@4h', 'ta:ma_regime@1d', 'ta:market_structure@1h', 'ta:market_structure@4h',
  'ta:momentum_state@1h', 'ta:momentum_state@4h', 'ta:ichimoku_cloud@4h', 'ta:ichimoku_cloud@1d', 'ta:adx_trend@1h', 'ta:obv_trend@1h', 'ta:cmf_flow@1h', 'ta:vwap_side@15m',
  'tanet_up1', 'tanet_up4', 'lib_net', 'xg_rel4', 'xg_rel24', 'xg_rank',
  'tl_sar@60m', 'tl_aroon@60m', 'tl_kama@60m',
];
const isFilter = (id: string) => FILTERS.includes(id) || id.startsWith('conf:') || id.startsWith('conv:');

export interface SweepOut { header: Record<string, unknown>; recs: CellRec[] }

export function sweepAsset(g: Grid, o: { seal: number; validFrom: number; costs: Costs; minN?: number; storeT?: number; placeboTop?: number; shifts?: number; log?: (m: string) => void; rules?: (r: RuleDef) => boolean;
  /** The bot's TA modules (research/perpTaModules.ts); false = classic families only. */
  modules?: false | { history?: string; forecasts?: string; cacheDir?: string };
  /** 'ctx' (default): every trigger alone and with each context filter (FILTERS); 'all': every ordered pair. */
  pairs?: 'ctx' | 'all';
  /** Fewest discovery trades for a cell to be a candidate (BH-eligible and given a placebo); smaller cells still count in m. */
  minBhN?: number }): SweepOut {
  const log = o.log ?? console.log;
  const minN = o.minN ?? 30, storeT = o.storeT ?? 2.5;
  const nMax = Math.min(g.n, Math.max(0, Math.round((o.seal - g.t0) / MIN)));
  let t = Date.now();
  const prims = buildPrims(g, nMax, log);
  const mod = o.modules === false ? undefined : modulePrims(g, nMax, { ...(o.modules ?? {}), discoveryEnd: o.validFrom, log });
  if (mod) prims.push(...mod.prims);
  log(`primitives: ${prims.length} (${Object.entries(prims.reduce((a, p) => { const k = sourceOf(p.id); a[k] = (a[k] ?? 0) + 1; return a; }, {} as Record<string, number>)).map(([k, v]) => `${k} ${v}`).join(', ')}) in ${((Date.now() - t) / 60000).toFixed(1)} min`);
  t = Date.now();
  const unit = atrUnit(g, nMax);
  const out = outcomes(g, nMax, unit, o.costs);
  const fillShare = Object.fromEntries(POLICIES.map((p, k) => { const a = out.fills[2 * k], b = out.fills[2 * k + 1], n = a.tried + b.tried; return [p.id, n ? +((a.filled + b.filled) / n).toFixed(4) : null]; }));
  log(`outcome tables: ${NPOL} policies x 2 sides in ${((Date.now() - t) / 1000).toFixed(1)} s${POLICIES.some((p) => p.entry) ? `; maker fill share ${ENTRY_TAGS.filter((tag) => POLICIES.some((p) => p.id.startsWith(`${tag}:`))).map((tag) => { const ks = POLICIES.map((p, k) => (p.id.startsWith(`${tag}:`) ? k : -1)).filter((k) => k >= 0); let n = 0, f = 0; for (const k of ks) for (const z of [0, 1]) { n += out.fills[2 * k + z].tried; f += out.fills[2 * k + z].filled; } return `${tag} ${n ? ((100 * f) / n).toFixed(1) : '-'}%`; }).join(', ')}` : ''}`);
  const cond = conditions(g, nMax, mod);
  const fo = folds(g, nMax, o.validFrom);
  const NF = fo.starts.length;
  // The random-entry baseline: per policy, trade direction, condition and calendar month, the mean result of entering
  // at every tradable minute (what any entry would have made then: drift, fees, funding and the exit's own shape).
  t = Date.now();
  const monthOf = new Int16Array(nMax);
  const y0 = new Date(g.t0).getUTCFullYear(), m0 = new Date(g.t0).getUTCMonth();
  for (let i = 0; i < nMax; i++) { const d = new Date(g.t0 + i * MIN); monthOf[i] = (d.getUTCFullYear() - y0) * 12 + d.getUTCMonth() - m0; }
  const NM = monthOf[nMax - 1] + 1;
  const base = new Float64Array(NPOL * 2 * NCOND * NM), bvar = new Float64Array(base.length);
  {
    const cnt = new Float64Array(base.length);
    for (let k = 0; k < NPOL * 2; k++) {
      const nt = out.net[k];
      for (let i = 0; i < nMax; i++) {
        const x = nt[i]; if (x !== x) continue;
        const mo = monthOf[i], b0 = k * NCOND * NM;
        base[b0 + mo] += x; bvar[b0 + mo] += x * x; cnt[b0 + mo]++;
        for (let z = 0; z < NZ; z++) { const cz = cond[i * NZ + z]; if (cz === NONE) continue; const j = b0 + cz * NM + mo; base[j] += x; bvar[j] += x * x; cnt[j]++; }
      }
    }
    for (let j = 0; j < base.length; j++) { base[j] = cnt[j] ? base[j] / cnt[j] : 0; bvar[j] = cnt[j] > 1 ? Math.max(0, bvar[j] / cnt[j] - base[j] * base[j]) : 0; }
  }
  log(`random-entry baseline: ${NM} months in ${((Date.now() - t) / 1000).toFixed(1)} s`);
  const trig = prims.map((p) => triggers(p, g.c.valid, nMax));
  const rules: RuleDef[] = [];
  const filt = prims.map((p, b) => (o.pairs === 'all' || isFilter(p.id) ? b : -1)).filter((b) => b >= 0);
  for (let a = 0; a < prims.length; a++) {
    rules.push({ id: prims[a].id, trig: a, filt: -1 });
    for (const b of filt) if (b !== a) rules.push({ id: `${prims[a].id}+${prims[b].id}`, trig: a, filt: b });
  }
  const bySrc: Record<string, { trig: [number, number]; filt: [number, number] }> = {};
  const tally = (r: RuleDef, stored: boolean) => {
    const a = (bySrc[sourceOf(prims[r.trig].id)] ??= { trig: [0, 0], filt: [0, 0] }).trig;
    a[0]++; if (stored) a[1]++;
    if (r.filt >= 0) { const b = (bySrc[sourceOf(prims[r.filt].id)] ??= { trig: [0, 0], filt: [0, 0] }).filt; b[0]++; if (stored) b[1]++; }
  };
  const todo = o.rules ? rules.filter(o.rules) : rules;
  log(`${prims.length} primitives, ${todo.length} rules, ${NF} folds (${fo.discovery} discovery: ${fo.labels.slice(0, fo.discovery).join(' ')}; validation ${fo.labels.slice(fo.discovery).join(' ')}), sealed from ${new Date(o.seal).toISOString().slice(0, 10)}`);

  const acc = new Float64Array(NCELL * NF * NS);
  const recs: CellRec[] = [];
  const tHist = new Array(81).fill(0); // discovery t of every tested cell, -10..+10 in 0.25 steps
  let tested = 0;
  const entriesOf = (r: RuleDef): { idx: Int32Array; dir: Int8Array; len: number } => {
    const tr = trig[r.trig];
    if (r.filt < 0) return { idx: tr.idx, dir: tr.dir, len: tr.idx.length };
    const fp = prims[r.filt], idx = new Int32Array(tr.idx.length), dir = new Int8Array(tr.idx.length);
    let k = 0;
    for (let q = 0; q < tr.idx.length; q++) { const i = tr.idx[q]; if (stateAt(fp, i) === tr.dir[q]) { idx[k] = i; dir[k] = tr.dir[q]; k++; } }
    return { idx, dir, len: k };
  };
  const walk = (en: { idx: Int32Array; dir: Int8Array; len: number }, mode: number, p: number, into: Float64Array, onlySide = -1, onlyCond = -1, shift = 0): void => {
    let nextFree = 0;
    const L = en.len;
    // A shifted (placebo) walk visits the rotated entries in time order: from the first index that lands at or after
    // the shift's wrap point.
    let start = 0;
    if (shift) { const cut = nMax - shift; while (start < L && en.idx[start] < cut) start++; }
    for (let q0 = 0; q0 < L; q0++) {
      const q = shift ? (start + q0) % L : q0;
      let i = en.idx[q];
      if (shift) { i += shift; if (i >= nMax) i -= nMax; }
      if (i < nextFree) continue;
      if (!g.c.valid[i] || i + 1 >= nMax || !g.c.valid[i + 1]) continue;
      const sd = en.dir[q], td = mode === 0 ? sd : -sd, k = p * 2 + (td > 0 ? 0 : 1);
      const x = out.net[k][i];
      // A maker order that never filled rested until its cancel minute: the rule took no other entry meanwhile.
      if (x !== x) { const c = out.exit[k][i]; if (c > nextFree) nextFree = c; continue; }
      const ex = out.exit[k][i];
      nextFree = ex;
      const f = fo.of[i];
      if (fo.of[ex] !== f) continue; // purged: the exit falls in the next fold
      const side = sd > 0 ? 0 : 1;
      if (onlySide >= 0 && side !== onlySide) continue;
      const hd = out.hold[k][i], win = x > 0 ? 1 : 0, b0 = k * NCOND * NM + monthOf[i];
      const fb = td * (out.cum[ex] - out.cum[ex - hd + 1]) * 1e4, fa = Math.abs(fb);
      const add = (c: number) => { const b = (cellIdx(mode, p, side, c) * NF + f) * NS, j = b0 + c * NM, e = x - base[j]; into[b] += 1; into[b + 1] += x; into[b + 2] += x * x; into[b + 3] += win; into[b + 4] += hd; into[b + 5] += e; into[b + 6] += e * e; into[b + 7] += bvar[j]; into[b + 8] += fb; into[b + 9] += fa; };
      if (onlyCond >= 0) { let hit = onlyCond === 0; for (let z = 0; z < NZ && !hit; z++) hit = cond[i * NZ + z] === onlyCond; if (hit) add(onlyCond); continue; }
      add(0);
      for (let z = 0; z < NZ; z++) { const cz = cond[i * NZ + z]; if (cz !== NONE) add(cz); }
    }
  };

  t = Date.now();
  let done = 0;
  for (const r of todo) {
    const en = entriesOf(r);
    done++;
    if (en.len < minN) continue;
    acc.fill(0);
    for (let mode = 0; mode < 2; mode++) for (let p = 0; p < NPOL; p++) walk(en, mode, p, acc);
    for (let mode = 0; mode < 2; mode++) for (let p = 0; p < NPOL; p++) for (let side = 0; side < 2; side++) for (let c = 0; c < NCOND; c++) {
      const cb = cellIdx(mode, p, side, c) * NF * NS;
      const d = discStats(acc, cb, fo.discovery);
      if (!(d.n >= minN) || !fin(d.tExc)) continue;
      tested++;
      tHist[Math.max(0, Math.min(80, Math.floor((d.tExc + 10) * 4)))]++; // bin b holds t in [b/4 - 10, (b+1)/4 - 10)
      tally(r, d.tExc >= storeT);
      if (d.tExc < storeT) continue;
      const rv = discStats(acc, cellIdx(1 - mode, p, side, c) * NF * NS, fo.discovery);
      const f: number[][] = [];
      for (let k = 0; k < NF; k++) { const b = cb + k * NS; f.push([acc[b], +acc[b + 1].toFixed(1), +acc[b + 2].toFixed(0), acc[b + 3], acc[b + 4], +acc[b + 5].toFixed(1), +acc[b + 6].toFixed(0), +acc[b + 7].toFixed(0), +acc[b + 8].toFixed(1), +acc[b + 9].toFixed(1)]); }
      recs.push({ a: g.asset, rule: r.id, mode: mode ? 'fade' : 'follow', pol: POLICIES[p].id, side: side ? 'short' : 'long', cond: CONDS[c], f, disc: { n: d.n, mean: +d.mean.toFixed(2), t: +d.t.toFixed(3), hit: +d.hit.toFixed(3), exc: +d.exc.toFixed(2), tExc: +d.tExc.toFixed(3) }, rev: { n: rv.n, mean: +rv.mean.toFixed(2), t: +(rv.t || 0).toFixed(3), exc: +(rv.exc || 0).toFixed(2), tExc: +(rv.tExc || 0).toFixed(3) } });
    }
    if (done % 1000 === 0) log(`rules ${done}/${todo.length}: ${tested} cells tested, ${recs.length} stored (${((Date.now() - t) / 60000).toFixed(1)} min)`);
  }
  log(`sweep: ${todo.length} rules, ${tested} cells tested, ${recs.length} stored with t >= ${storeT} in ${((Date.now() - t) / 60000).toFixed(1)} min`);

  // Placebo for the strongest stored cells: the rule's own entries moved by whole days (the time of day kept).
  // Placebo slots: the cell each group (coin, rule, mode, side) would put forward (its best discovery excess t among cells
  // that survive the +3 bps per side stress), best groups first: the report judges exactly these representatives.
  const repBest = new Map<string, CellRec>();
  for (const r of recs) { if (!(r.disc.mean - 6 > 0) || !(r.disc.n >= (o.minBhN ?? 100))) continue; const k = `${r.rule}|${r.mode}|${r.side}`, b = repBest.get(k); if (!b || r.disc.tExc > b.disc.tExc) repBest.set(k, r); }
  const top = [...repBest.values()].sort((x, y) => y.disc.tExc - x.disc.tExc).slice(0, o.placeboTop ?? 3000);
  const S = o.shifts ?? 60, days = Math.floor(nMax / 1440);
  const shifts = Array.from({ length: S }, (_, k) => Math.round(7 + (k * (days - 14)) / Math.max(1, S - 1)) * 1440).filter((s) => s > 0 && s < nMax);
  const byRule = new Map<string, RuleDef>(todo.map((r) => [r.id, r]));
  const one = new Float64Array(NCELL * NF * NS);
  t = Date.now();
  for (const rec of top) {
    const r = byRule.get(rec.rule)!, en = entriesOf(r);
    const mode = rec.mode === 'fade' ? 1 : 0, p = POLICIES.findIndex((x) => x.id === rec.pol), side = rec.side === 'short' ? 1 : 0, c = CONDS.indexOf(rec.cond);
    const cb = cellIdx(mode, p, side, c) * NF * NS;
    const means: number[] = [];
    for (const sh of shifts) {
      for (let k = 0; k < NF * NS; k++) one[cb + k] = 0;
      walk(en, mode, p, one, side, c, sh);
      const d = discStats(one, cb, fo.discovery);
      if (d.n >= 10) means.push(d.mean);
    }
    if (!means.length) continue;
    const mu = means.reduce((a, b) => a + b, 0) / means.length, sd = Math.sqrt(means.reduce((a, b) => a + (b - mu) ** 2, 0) / Math.max(1, means.length - 1));
    rec.placebo = { pct: +(means.filter((m) => m < rec.disc.mean).length / means.length).toFixed(3), mean: +mu.toFixed(2), sd: +sd.toFixed(2), shifts: means.length };
  }
  log(`placebo: ${top.length} cells x ${shifts.length} whole-day shifts in ${((Date.now() - t) / 60000).toFixed(1)} min`);
  const header = {
    schema: 'perpta-sweep3', round: ROUND, sha: process.env.GITHUB_SHA ?? 'local', asset: g.asset, at: new Date().toISOString(), t0: new Date(g.t0).toISOString(), seal: new Date(o.seal).toISOString(), validFrom: new Date(o.validFrom).toISOString(),
    nMinutes: nMax, prims: prims.map((p) => p.id), filters: filt.map((b) => prims[b].id), rules: todo.length, bySource: bySrc, modules: mod?.notes ?? 'off', tested, stored: recs.length, storeT, minN, tHist, folds: fo.labels, discoveryFolds: fo.discovery,
    foldDays: fo.starts.map((s, k) => +(((k + 1 < fo.starts.length ? fo.starts[k + 1] : nMax) - s) / 1440).toFixed(2)),
    policies: POLICIES, fillShare, conds: CONDS, costs: o.costs, minBhN: o.minBhN ?? 100,
    triggersPerDay: Object.fromEntries(prims.map((p, k) => [p.id, +(trig[k].idx.length / (nMax / 1440)).toFixed(2)])),
  };
  return { header, recs };
}

// ---------------------------------------------------------------------------------------------------------------
// The report: multiple testing, adversaries, validation folds, CSCV.

/** Writes lines as gzip in members of up to 20,000 lines (no single string near V8's limit; gunzip reads concatenated
 *  members as one stream). */
export function writeJsonlGz(file: string, lines: Iterable<string>): void {
  const fd = fs.openSync(file, 'w');
  try {
    let buf: string[] = [];
    const flush = () => { if (buf.length) { fs.writeSync(fd, zlib.gzipSync(buf.join('\n') + '\n')); buf = []; } };
    for (const l of lines) { buf.push(l); if (buf.length >= 20_000) flush(); }
    flush();
  } finally { fs.closeSync(fd); }
}

/** The non-empty lines of a gzip file (one or several members), decoded one at a time: the file is never one string. */
export function readJsonlGz(file: string): string[] {
  const b = zlib.gunzipSync(fs.readFileSync(file)), out: string[] = [];
  for (let s = 0; s < b.length;) { let e = b.indexOf(10, s); if (e < 0) e = b.length; if (e > s) out.push(b.toString('utf8', s, e)); s = e + 1; }
  return out;
}

const normSf = (z: number): number => { // P(Z > z)
  const t = 1 / (1 + 0.2316419 * Math.abs(z)), d = 0.3989422804014327 * Math.exp(-z * z / 2);
  const p = d * t * (0.31938153 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
  return z >= 0 ? p : 1 - p;
};

/** fund / fundAbs: mean funding paid per trade (bps, + = paid) and its mean absolute value (0 on round 1 records). */
export interface Pooled { n: number; mean: number; t: number; hit: number; hold: number; pos: number; folds: number; exc: number; tExc: number; excPos: number; fund: number; fundAbs: number }
export function pool(f: number[][], from: number, to: number): Pooled {
  let n = 0, s = 0, s2 = 0, w = 0, h = 0, pos = 0, nf = 0, e = 0, e2 = 0, excPos = 0, vb = 0, fu = 0, fa = 0;
  for (let k = from; k < to && k < f.length; k++) { const [a, b, c, d, hh, x, x2, xb, xf, xa] = f[k]; n += a; s += b; s2 += c; w += d; h += hh; e += x; e2 += x2; vb += xb ?? 0; fu += xf ?? 0; fa += xa ?? 0; if (a > 0) { nf++; if (b > 0) pos++; if (x > 0) excPos++; } }
  const floor = n ? Math.max(1e-9, vb / n) : 1e-9;
  const mean = n ? s / n : NaN, v = n > 1 ? Math.max(floor, (s2 - n * mean * mean) / (n - 1)) : NaN;
  const em = n ? e / n : NaN, ev = n > 1 ? Math.max(floor, (e2 - n * em * em) / (n - 1)) : NaN;
  return { n, mean, t: n > 1 ? mean / Math.sqrt(v / n) : NaN, hit: n ? w / n : NaN, hold: n ? h / n : NaN, pos, folds: nf, exc: em, tExc: n > 1 ? em / Math.sqrt(ev / n) : NaN, excPos, fund: n ? fu / n : 0, fundAbs: n ? fa / n : 0 };
}

/** CSCV probability of backtest overfitting (Bailey, Borwein, Lopez de Prado, Zhu 2015) over a configs x folds matrix
 *  of per-fold mean returns: the share of in-sample / out-of-sample splits where the in-sample best ranks below the
 *  out-of-sample median. */
export function pbo(M: number[][]): number {
  const T = M[0]?.length ?? 0;
  if (M.length < 2 || T < 4) return NaN;
  const S = T % 2 ? T - 1 : T, half = S / 2;
  const combos: number[][] = [];
  const rec = (start: number, cur: number[]) => { if (cur.length === half) { combos.push([...cur]); return; } for (let i = start; i < S; i++) { cur.push(i); rec(i + 1, cur); cur.pop(); } };
  rec(0, []);
  let below = 0, total = 0;
  for (const is of combos) {
    const isSet = new Set(is), oos = Array.from({ length: S }, (_, i) => i).filter((i) => !isSet.has(i));
    const score = (row: number[], cols: number[]) => cols.reduce((a, c) => a + (fin(row[c]) ? row[c] : 0), 0) / cols.length;
    let best = 0, bestV = -Infinity;
    M.forEach((row, r) => { const v = score(row, is); if (v > bestV) { bestV = v; best = r; } });
    const oosScores = M.map((row) => score(row, oos));
    const rank = oosScores.filter((v) => v < oosScores[best]).length / (M.length - 1); // 0 worst .. 1 best
    if (rank < 0.5) below++;
    total++;
  }
  return below / total;
}

/** P(T > t) for Student's t with df degrees of freedom (regularized incomplete beta; normal tail for df > 2000). */
export function tSf(t: number, df: number): number {
  if (!fin(t)) return 1;
  if (!(df >= 1)) return 1;
  if (df > 2000) return normSf(t);
  const x = df / (df + t * t), p = 0.5 * ibeta(x, df / 2, 0.5);
  return t >= 0 ? p : 1 - p;
}
function ibeta(x: number, a: number, b: number): number {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  const lbeta = lgamma(a + b) - lgamma(a) - lgamma(b);
  const front = Math.exp(Math.log(x) * a + Math.log(1 - x) * b + lbeta);
  return x < (a + 1) / (a + b + 2) ? (front * betacf(x, a, b)) / a : 1 - (front * betacf(1 - x, b, a)) / b;
}
function betacf(x: number, a: number, b: number): number {
  const TINY = 1e-300;
  let c = 1, d = 1 - ((a + b) * x) / (a + 1);
  if (Math.abs(d) < TINY) d = TINY;
  d = 1 / d;
  let h = d;
  for (let m = 1; m <= 300; m++) {
    const m2 = 2 * m;
    let aa = (m * (b - m) * x) / ((a + m2 - 1) * (a + m2));
    d = 1 + aa * d; if (Math.abs(d) < TINY) d = TINY; c = 1 + aa / c; if (Math.abs(c) < TINY) c = TINY; d = 1 / d; h *= d * c;
    aa = (-(a + m) * (a + b + m) * x) / ((a + m2) * (a + m2 + 1));
    d = 1 + aa * d; if (Math.abs(d) < TINY) d = TINY; c = 1 + aa / c; if (Math.abs(c) < TINY) c = TINY; d = 1 / d;
    const del = d * c; h *= del;
    if (Math.abs(del - 1) < 1e-12) break;
  }
  return h;
}
function lgamma(z: number): number { // Lanczos
  const g = 7, cf = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
  if (z < 0.5) return Math.log(Math.PI / Math.abs(Math.sin(Math.PI * z))) - lgamma(1 - z);
  z -= 1;
  let x = cf[0];
  for (let i = 1; i < g + 2; i++) x += cf[i] / (z + i);
  const t = z + g + 0.5;
  return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(x);
}

/** Benjamini-Hochberg: the indices (into ps) rejected at q with m hypotheses (m >= ps.length: untested-here ones have p = 1). */
function bhReject(ps: number[], q: number, m = ps.length): Set<number> {
  const ord = ps.map((p, i) => [p, i] as const).sort((a, b) => a[0] - b[0]);
  let kMax = 0;
  ord.forEach(([p], k) => { if (p <= (q * (k + 1)) / m) kMax = k + 1; });
  return new Set(ord.slice(0, kMax).map(([, i]) => i));
}

/** A cell reading the forecasts or forecast conditions: their model selection (tournament hyperparameters, the input
 *  cull) saw 2024-2026 outcomes, past the seal, so they are diagnostic only until re-exported on cut history. */
const FORECAST_CONDS = new Set(['tanet_vol_hi', 'tanet_vol_lo', 'lib_trend', 'lib_revert', 'lib_breakout', 'lib_flat']);
export const isDiagnostic = (c: { rule: string; cond: string }) => c.rule.split('+').some((id) => sourceOf(id) === 'TA Net / Librarian / cross graph') || FORECAST_CONDS.has(c.cond);

/** costs / policyDef: the coin's costs and the exit policy as its sweep ran them (the blind test trades exactly these). */
export interface Candidate extends CellRec { p: number; val: Pooled; discPooled: Pooled; tradesPerDay: number; usdPerHourPer1k: number; valUsdPerHourPer1k: number; stress6: number; fundStress: number; why: string[]; group: string; valP?: number; diagnostic: boolean; costs?: Costs; policyDef?: Policy }

/** The report. Selection, all pre-registered (/mnt/project-files/perp-ta/preregistration.md):
 *   1. every tested cell of every coin is one hypothesis (m); a cell with >= minBhN discovery trades gets the one-sided
 *      Student-t p of its discovery excess (variance floored at the random entries'); Benjamini-Hochberg at q
 *   2. each group (coin, rule, mode, side) puts forward ONE cell, chosen on discovery alone: its best excess t among
 *      cells that survive +3 bps per side (net - 6 bps > 0) with >= minBhN trades (the sweep gave exactly these a placebo)
 *   3. the representative must be a BH discovery, positive and above random in >= 60% of discovery half-years, placebo
 *      percentile >= 0.95, reversed excess < 0 (a mechanical check: kept as a leak flag)
 *   4. validation: Benjamini-Hochberg at q over the representatives left (forecast-reading ones excluded: diagnostic) on
 *      the one-sided t-test of the validation excess (>= 30 trades), and validation net > 0 and excess > 0
 *   round 2 adds the funding stress (funding paid x1.5, received x0.5: net - half the mean absolute funding per trade):
 *      discovery >= minBps (step 3) and validation > 0 (step 4). */
export function report(files: string[], o: { q?: number; minBps?: number; log?: (m: string) => void }): { summary: Record<string, unknown>; candidates: Candidate[]; funnel: Record<string, number>; md: string } {
  const log = o.log ?? console.log;
  const q = o.q ?? 0.1, minBps = o.minBps ?? 3;
  const recs: CellRec[] = [], headers: Array<Record<string, any>> = [];
  for (const file of files) {
    const lines = readJsonlGz(file);
    headers.push(JSON.parse(lines[0]));
    for (const l of lines.slice(1)) recs.push(JSON.parse(l));
  }
  const m = headers.reduce((a, h) => a + h.tested, 0);
  const hdr = new Map(headers.map((h) => [h.asset as string, h]));
  const minBhN = (a: string) => (hdr.get(a)?.minBhN as number | undefined) ?? 100;
  // 1. BH over every tested cell.
  const elig = recs.filter((r) => r.disc.n >= minBhN(r.a));
  const pEl = elig.map((r) => tSf(r.disc.tExc, r.disc.n - 1));
  const bhIdx = bhReject(pEl, q, m);
  const bhSet = new Set<CellRec>([...bhIdx].map((i) => elig[i]));
  const pOf = new Map<CellRec, number>(elig.map((r, i) => [r, pEl[i]]));
  // 2. One representative per group, on discovery alone.
  const groupOf = (r: CellRec) => `${r.a}|${r.rule}|${r.mode}|${r.side}`;
  const reps = new Map<string, CellRec>();
  for (const r of elig) { if (!(r.disc.mean - 6 > 0)) continue; const k = groupOf(r), b = reps.get(k); if (!b || r.disc.tExc > b.disc.tExc) reps.set(k, r); }
  const cands: Candidate[] = [];
  for (const [g, r] of reps) {
    const h = hdr.get(r.a)!, D = h.discoveryFolds as number, NF = (h.folds as string[]).length;
    const disc = pool(r.f, 0, D), val = pool(r.f, D, NF);
    const fd = h.foldDays as number[], days = fd.slice(0, D).reduce((a, b) => a + b, 0), vDays = fd.slice(D).reduce((a, b) => a + b, 0);
    const why: string[] = [];
    if (!bhSet.has(r)) why.push('not a discovery under Benjamini-Hochberg');
    if (disc.mean < minBps) why.push(`discovery ${disc.mean.toFixed(1)} bps/trade < ${minBps}`);
    const fundStress = disc.mean - 0.5 * disc.fundAbs;
    if (!(fundStress >= minBps)) why.push(`funding x1.5: discovery ${fundStress.toFixed(1)} bps/trade < ${minBps} (mean funding ${disc.fund.toFixed(2)} bps)`);
    if (disc.pos < Math.ceil(0.6 * disc.folds) || disc.excPos < Math.ceil(0.6 * disc.folds)) why.push(`net positive in ${disc.pos}/${disc.folds} discovery half-years, above random in ${disc.excPos}`);
    if (r.rev.exc !== undefined ? r.rev.exc >= 0 : r.rev.mean >= 0) why.push(`reversed excess ${r.rev.exc ?? r.rev.mean} >= 0`);
    if (!r.placebo) why.push('no placebo run'); else if (r.placebo.pct < 0.95) why.push(`placebo percentile ${r.placebo.pct}`);
    const diagnostic = isDiagnostic(r);
    if (diagnostic) why.push('reads a forecast whose model selection saw 2024-2026: diagnostic only');
    const tradesPerDay = disc.n / days;
    const policyDef = (h.policies as Policy[] | undefined)?.find((x) => x.id === r.pol);
    cands.push({ ...r, p: pOf.get(r) ?? 1, val, discPooled: disc, tradesPerDay: +tradesPerDay.toFixed(2), usdPerHourPer1k: +((disc.mean / 1e4) * 1000 * tradesPerDay / 24).toFixed(3), valUsdPerHourPer1k: +((val.mean / 1e4) * 1000 * (val.n / Math.max(1, vDays)) / 24).toFixed(3), stress6: +(disc.mean - 6).toFixed(2), fundStress: +fundStress.toFixed(2), why, group: g, diagnostic, costs: h.costs as Costs, policyDef });
  }
  // The funnel through the discovery checks, in the order they are applied (before any validation reason is added).
  const funnel: Record<string, number> = { tested: m, stored: recs.length, [`n>=${minBhN(recs[0]?.a ?? '')}`]: elig.length, bh: bhSet.size, groups: reps.size };
  const has = (c: Candidate, pre: string) => c.why.some((w) => w.startsWith(pre));
  const STAGES: Array<[string, string[]]> = [['+bh', ['not a discovery']], ['+economic', ['discovery ']], ['+funding', ['funding x1.5: discovery']], ['+stable', ['net positive']], ['+reversed', ['reversed']], ['+placebo', ['no placebo', 'placebo percentile']]];
  const gone: string[] = [];
  for (const [name, pres] of STAGES) { gone.push(...pres); funnel[name] = cands.filter((c) => !gone.some((pre) => has(c, pre))).length; }
  // 4. Validation: BH over the representatives that passed every discovery check.
  const discOk = (c: Candidate) => c.why.length === 0 || (c.why.length === 1 && c.diagnostic);
  const fam = cands.filter((c) => discOk(c) && !c.diagnostic);
  const vp = fam.map((c) => (c.val.n >= 30 ? tSf(c.val.tExc, c.val.n - 1) : 1));
  const vRej = bhReject(vp, q);
  fam.forEach((c, i) => { c.valP = +vp[i].toExponential(3); });
  for (const c of cands.filter(discOk)) {
    const i = fam.indexOf(c);
    if (!(c.val.n >= 30)) c.why.push(`only ${c.val.n} validation trades`);
    else if (!(c.val.mean > 0 && c.val.exc > 0)) c.why.push(`validation ${c.val.mean.toFixed(1)} bps/trade, ${c.val.exc.toFixed(1)} above random`);
    else if (!(c.val.mean - 0.5 * c.val.fundAbs > 0)) c.why.push(`funding x1.5: validation ${(c.val.mean - 0.5 * c.val.fundAbs).toFixed(1)} bps/trade`);
    else if (i >= 0 && !vRej.has(i)) c.why.push(`validation excess t ${c.val.tExc.toFixed(2)} not a discovery under Benjamini-Hochberg over ${fam.length} groups`);
    else if (i < 0) { const pv = tSf(c.val.tExc, c.val.n - 1); c.valP = +pv.toExponential(3); }
  }
  funnel['non-forecast'] = fam.length;
  funnel['+validation'] = cands.filter((c) => c.why.length === 0).length;
  const pass = cands.filter((c) => c.why.length === 0);
  // CSCV over the 200 strongest groups (their discovery representative from every stored cell), per-fold excess means
  // over discovery and validation folds; an odd fold count drops the oldest.
  const best200 = new Map<string, CellRec>();
  for (const r of recs) { const k = groupOf(r), b = best200.get(k); if (!b || r.disc.tExc > b.disc.tExc) best200.set(k, r); }
  const topM = [...best200.values()].sort((a, b) => b.disc.tExc - a.disc.tExc).slice(0, 200);
  const NFmin = Math.min(...topM.map((c) => c.f.length));
  const PBO = topM.length >= 2 ? pbo(topM.map((c) => { const f = c.f.slice(c.f.length - NFmin); const off = f.length % 2; return f.slice(off).map((x) => (x[0] ? x[5] / x[0] : 0)); })) : NaN;
  // The t distribution of all tested cells (null ~ N(0, 1) if nothing works and nothing leaks).
  const tAll = new Array(81).fill(0);
  for (const h of headers) (h.tHist as number[]).forEach((v, i) => { tAll[i] += v; });
  const share = (lo: number) => tAll.reduce((a, v, i) => a + (i / 4 - 10 >= lo ? v : 0), 0) / Math.max(1, m);
  // Descriptive: the 40 strongest non-forecast groups' validation trades pooled (their trades overlap: no test).
  const top40 = cands.filter((c) => !c.diagnostic).sort((a, b) => b.disc.tExc - a.disc.tExc).slice(0, 40);
  const vPool = (() => { if (!top40.length) return undefined; const acc: number[][] = []; for (const c of top40) { const D = hdr.get(c.a)!.discoveryFolds as number; for (const row of c.f.slice(D)) { const z = new Array(10).fill(0); row.forEach((v, k) => { z[k] = v; }); acc.push(z); } } return pool(acc, 0, acc.length); })();
  const round = (headers[0]?.round as number | undefined) ?? 1;
  const costLine = headers.filter((h, k) => headers.findIndex((x) => x.asset === h.asset) === k).map((h) => { const c = h.costs as Costs; return `${h.asset} taker ${c.takerBps} + half-spread ${c.halfSpreadBps}, maker ${c.makerBps}${c.fundOffsetBps ? `, funding ${c.fundOffsetBps > 0 ? '+' : ''}${c.fundOffsetBps} bps / 8 h over the model` : ''}${c.fundMult && c.fundMult !== 1 ? ` x${c.fundMult}` : ''}${h.fillShare ? `; maker fills ${ENTRY_TAGS.filter((tag) => Object.keys(h.fillShare as object).some((k) => k.startsWith(`${tag}:`))).map((tag) => { const v = Object.entries(h.fillShare as Record<string, number | null>).filter(([k, x]) => k.startsWith(`${tag}:`) && x !== null).map(([, x]) => x as number); return `${tag} ${v.length ? (100 * v.reduce((a, b) => a + b, 0) / v.length).toFixed(0) : '-'}%`; }).join(' ')}` : ''}`; }).join('; ');
  const summary = { at: new Date().toISOString(), sha: (headers[0]?.sha as string | undefined) ?? 'local', round, assets: headers.map((h) => h.asset), tested: m, q, minBps, funnel, pbo: PBO, top40Validation: vPool ? { n: vPool.n, mean: +vPool.mean.toFixed(2), exc: +vPool.exc.toFixed(2), fund: +vPool.fund.toFixed(2) } : null, tShareAbove2: +share(2).toFixed(4), tShareAbove3: +share(3).toFixed(5), normalAbove2: 0.0228, normalAbove3: 0.00135, perAsset: headers.map((h) => ({ asset: h.asset, tested: h.tested, stored: h.stored, minutes: h.nMinutes, folds: h.folds, discovery: h.discoveryFolds, prims: (h.prims as string[]).length, modules: h.modules, costs: h.costs, fillShare: h.fillShare })) } as Record<string, unknown>;
  const f1 = (x: number) => (fin(x) ? x.toFixed(1) : '-');
  const fmt = (c: Candidate) => `| ${c.a} | ${c.rule} | ${c.mode} | ${c.pol} | ${c.side} | ${c.cond} | ${c.disc.n} | ${c.disc.mean} | ${c.disc.exc} | ${c.disc.tExc} | ${c.placebo ? c.placebo.pct : '-'} | ${c.val.n} | ${f1(c.val.mean)} | ${f1(c.val.exc)} | ${f1(c.val.tExc)} | ${c.tradesPerDay} | ${c.valUsdPerHourPer1k} | ${c.why.join('; ') || 'PASS'} |`;
  const head = '| coin | rule | mode | exit | side | condition | disc n | disc bps | disc excess | excess t | placebo | val n | val bps | val excess | val excess t | trades/day | val $/h per $1k | verdict |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|';
  const rank = (a: Candidate, b: Candidate) => (a.why.length - b.why.length) || (b.disc.tExc - a.disc.tExc);
  // The table: the best group per coin, trigger, mode and side (the same signal under other filters is in the funnel).
  const seen = new Set<string>();
  const best = [...cands].sort(rank).filter((c) => { const k = `${c.a}|${c.rule.split('+')[0]}|${c.mode}|${c.side}`; if (seen.has(k)) return false; seen.add(k); return true; }).slice(0, 40);
  // By source (the bot's modules vs the classic families): tested / stored from the sweeps; groups, BH and pass here.
  const src: Record<string, { tt: number; ts: number; tb: number; tp: number; ft: number; fs: number; fb: number; fp: number }> = {};
  const S = (k: string) => (src[k] ??= { tt: 0, ts: 0, tb: 0, tp: 0, ft: 0, fs: 0, fb: 0, fp: 0 });
  for (const h of headers) for (const [k, v] of Object.entries((h.bySource ?? {}) as Record<string, { trig: number[]; filt: number[] }>)) { const x = S(k); x.tt += v.trig[0]; x.ts += v.trig[1]; x.ft += v.filt[0]; x.fs += v.filt[1]; }
  const srcOf = (c: Candidate) => { const [a, b] = c.rule.split('+'); return [sourceOf(a), b ? sourceOf(b) : undefined] as const; };
  for (const c of cands) { if (has(c, 'not a discovery')) continue; const [a, b] = srcOf(c); S(a).tb++; if (!c.why.length) S(a).tp++; if (b) { S(b).fb++; if (!c.why.length) S(b).fp++; } }
  summary.bySource = src;
  const bestBySrc = Object.keys(src).flatMap((k) => { const sn = new Set<string>(); return cands.filter((c) => srcOf(c)[0] === k && !has(c, 'not a discovery')).sort(rank).filter((c) => { const key = `${c.a}|${c.rule.split('+')[0]}`; if (sn.has(key)) return false; sn.add(key); return true; }).slice(0, 3); });
  const diag = cands.filter((c) => c.diagnostic && !has(c, 'not a discovery')).sort(rank).slice(0, 10);
  const md = [
    `### Perp TA sweep, round ${round} (with the bot's TA modules${round >= 2 ? '; post-only maker entries' : ''}${round >= 3 ? '; exits in 1-hour and 4-hour ATRs, holds of 4 hours to 7 days' : ''})`,
    `Tested ${m.toLocaleString()} cells (${headers.map((h) => `${h.asset} ${h.tested.toLocaleString()}`).join(', ')}); Benjamini-Hochberg q=${q} on Student-t p of the discovery excess (cells with >= ${minBhN(recs[0]?.a ?? '')} trades): ${bhSet.size} cells pass, in ${funnel['+bh']} of ${reps.size} groups (coin, rule, mode, side).`,
    `Share of cells whose discovery excess over random entries has t >= 2: ${(share(2) * 100).toFixed(2)}% (pure noise would give 2.28%); t >= 3: ${(share(3) * 100).toFixed(3)}% (noise 0.135%).`,
    `Funnel (groups after "groups"): ${Object.entries(funnel).map(([k, v]) => `${k} ${v}`).join(' -> ')}. CSCV PBO over the top ${topM.length} groups: ${fin(PBO) ? PBO.toFixed(2) : 'n/a'}.`,
    `Passing every check, validation included: ${pass.length}. Costs (bps; resting orders need a ${headers[0]?.costs?.ttBps ?? 0} bp trade-through; Kalshi funding signed): ${costLine}.`,
    vPool ? `The 40 strongest non-forecast groups on validation, pooled (descriptive, their trades overlap): ${vPool.n.toLocaleString()} trades, net ${vPool.mean.toFixed(1)} bps a trade, ${vPool.exc.toFixed(1)} above random entries, funding ${vPool.fund.toFixed(2)} bps a trade.` : '',
    '', head, ...best.map(fmt),
    '', '**By source** (cells with that source as the trigger / as the filter: tested, discovery excess t >= 2.5 in the sweep; groups whose representative is a BH discovery, and groups passing every check)',
    '| source | trigger tested | t >= 2.5 | BH groups | pass | filter tested | t >= 2.5 | BH groups | pass |', '|---|---|---|---|---|---|---|---|---|',
    ...Object.entries(src).sort((a, b) => b[1].tt - a[1].tt).map(([k, x]) => `| ${k} | ${x.tt.toLocaleString()} | ${x.ts.toLocaleString()} | ${x.tb} | ${x.tp} | ${x.ft.toLocaleString()} | ${x.fs.toLocaleString()} | ${x.fb} | ${x.fp} |`),
    ...(bestBySrc.length ? ['', '**Best per trigger source**', '', head, ...bestBySrc.map(fmt)] : []),
    ...(diag.length ? ['', '**Forecast-reading groups (diagnostic: the TA Net / Librarian / cross-graph model selection saw 2024-2026)**', '', head, ...diag.map(fmt)] : []),
    '', '<details><summary>Module coverage per coin</summary>', '',
    ...headers.map((h) => `- ${h.asset}: ${Array.isArray(h.modules) ? (h.modules as string[]).join('; ') : String(h.modules ?? 'n/a')}`),
    '', '</details>',
  ].join('\n');
  log(md);
  return { summary, candidates: cands, funnel, md };
}

// ---------------------------------------------------------------------------------------------------------------
// CLI.

function arg(k: string, d?: string): string | undefined { const i = process.argv.indexOf(`--${k}`); return i >= 0 && process.argv[i + 1] !== undefined && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : d; }

async function main(): Promise<void> {
  const mode = process.argv[2];
  const log = (m: string) => console.log(`[perp-ta] ${m}`);
  if (mode === 'prep') {
    const asset = arg('asset')!, hist = arg('history', 'data/history')!, outDir = arg('out', 'data/perp-ta')!;
    if (arg('download', 'true') === 'true') {
      const { downloadBinance, downloadBinanceFunding, downloadBinanceOpenInterest } = await import('./history/binanceVision');
      const quiet = () => undefined;
      const from = arg('from-month', '2019-09')!;
      const sums = [
        ...await downloadBinance({ out: hist, assets: [asset], intervals: ['1m'], markets: ['spot'], source: 'binance-1m', fromMonth: from, log: quiet, concurrency: 8 }),
        ...await downloadBinance({ out: hist, assets: [asset], intervals: ['1m'], markets: ['um'], fromMonth: from, log: quiet, concurrency: 8 }),
      ];
      await downloadBinanceFunding({ out: hist, assets: [asset], fromMonth: from, log: quiet });
      await downloadBinanceOpenInterest({ out: hist, assets: [asset], fromDay: `${from}-01`, log: quiet, concurrency: 8 });
      // Every coin's spot hourly bars: the character classifier's cross-coin correlation and the breadth reading.
      sums.push(...await downloadBinance({ out: hist, assets: (arg('others', 'BTC,ETH,SOL,XRP')!).split(','), intervals: ['1h'], markets: ['spot'], source: 'binance-1h', fromMonth: from, log: quiet, concurrency: 8 }));
      for (const x of sums) log(`${x.pair} ${x.market} ${x.tf}: ${x.listed} archives listed, ${x.fetched} fetched, ${x.skipped} kept, ${x.failed} FAILED, ${x.bars} bars${x.note ? ` (${x.note})` : ''}`);
      const failed = sums.filter((x) => x.failed > 0);
      if (failed.length) log(`WARNING: ${failed.length} series had failed downloads (gaps become invalid minutes): ${failed.map((x) => `${x.pair} ${x.market} ${x.tf}`).join(', ')}`);
      log(`${asset}: downloads done`);
    }
    writeGrid(await buildGrid(hist, asset, log), path.join(outDir, `${asset}.bin`));
    return;
  }
  if (mode === 'sweep') {
    const g = readGrid(arg('data')!);
    const seal = Date.parse(arg('seal', '2025-07-01')! + 'T00:00:00Z'), validFrom = Date.parse(arg('valid-from', '2024-01-01')! + 'T00:00:00Z');
    const costs: Costs = { takerBps: +arg('taker', '12')!, makerBps: +arg('maker', '5')!, halfSpreadBps: +arg('half-spread', '2')!, ttBps: +arg('trade-through', '1')!, fundOffsetBps: +arg('funding-offset', '0')!, fundMult: +arg('funding-mult', '1')! };
    for (const [k, v] of Object.entries(costs)) if (!fin(v)) throw new Error(`--${k}: not a number`);
    const shard = +arg('shard', '0')!, shards = +arg('shards', '1')!;
    const modules = arg('modules', 'true') === 'false' ? false as const : { history: arg('history'), forecasts: arg('forecasts'), cacheDir: arg('module-cache') };
    const res = sweepAsset(g, { seal, validFrom, costs, log, modules, pairs: arg('pairs', 'ctx') === 'all' ? 'all' : 'ctx', placeboTop: +arg('placebo-top', '3000')!, minBhN: +arg('min-bh-n', '100')!, shifts: +arg('shifts', '60')!, storeT: +arg('store-t', '2.5')!, rules: shards > 1 ? (r) => r.trig % shards === shard : undefined });
    const file = arg('out')!;
    fs.mkdirSync(path.dirname(file), { recursive: true });
    writeJsonlGz(file, (function* () { yield JSON.stringify({ ...res.header, shard, shards }); for (const r of res.recs) yield JSON.stringify(r); })());
    log(`wrote ${file} (${res.recs.length} cells)`);
    return;
  }
  if (mode === 'report') {
    const dir = arg('in')!, outDir = arg('out', 'report')!;
    const files = fs.readdirSync(dir, { recursive: true }).map(String).filter((f) => f.endsWith('.jsonl.gz')).map((f) => path.join(dir, f));
    const r = report(files, { q: +arg('q', '0.1')!, minBps: +arg('min-bps', '3')!, log });
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(path.join(outDir, 'summary.json'), JSON.stringify(r.summary, null, 1));
    fs.writeFileSync(path.join(outDir, 'candidates.json.gz'), zlib.gzipSync(JSON.stringify(r.candidates)));
    fs.writeFileSync(path.join(outDir, 'summary.md'), r.md + '\n');
    // Rows for the project trial registry (registry v1, research/perpTaRegistry.ts): the random-entry control, the run
    // (N_raw = cells tested) and every group that passed the discovery checks, paired with the control. No daily P&L
    // before the sealed block is read (counted in N_raw, not scored).
    const now = new Date(), est = now.toLocaleString('en-US', { timeZone: 'America/New_York', hour12: false });
    // code_sha = the sweep's commit (its cells' header), which the blind test's freeze reads back from summary.json.
    const run = process.env.GITHUB_RUN_ID ?? 'local', sha = (r.summary.sha as string) || process.env.GITHUB_SHA || 'local', round = r.summary.round as number;
    const base = { thread: 'perp-ta-rulebook', round, run, sha, at_utc: now.toISOString(), at_eastern: est, evidence: 'binance-history (spot TA, USD-M fills)', doge_excluded: true, prereg: '/mnt/project-files/perp-ta/preregistration.md' };
    const codeEpoch = `perp-ta round ${round}`, ref = runRef(run);
    const ctl = regRow({ arm: controlArm(run), role: 'control', codeSha: sha, codeEpoch, ref, at: now, verdict: 'random entries through the same exits (the excess baseline)' });
    const rows = [
      ctl,
      regRow({ arm: `r${round}:sweep:run-${run}`, role: 'candidate', control: ctl.trial_id, codeSha: sha, codeEpoch, ref, at: now, verdict: `${r.summary.tested} cells tested; ${(r.funnel as Record<string, number>)['+validation'] ?? 0} pass validation`, raw: { ...base, kind: 'run', n_raw: r.summary.tested, funnel: r.funnel, pbo: r.summary.pbo, assets: r.summary.assets, blocks: { discovery: '< 2024-01-01', validation: '2024-01-01 .. 2025-06-30', sealed: '>= 2025-07-01 (not opened)' } } }),
      ...r.candidates.filter((c) => !c.why.some((w) => w.startsWith('not a discovery'))).map((c) => regRow({ arm: `r${round}:run-${run}:${c.group}|${c.pol}|${c.cond}`, role: 'candidate', control: ctl.trial_id, codeSha: sha, codeEpoch, ref, at: now, verdict: c.why.length ? c.why.join('; ') : 'PASS (awaiting the sealed blind test)', raw: { ...base, kind: 'group', group: c.group, pol: c.pol, cond: c.cond, disc: c.disc, val: { n: c.val.n, mean: +c.val.mean.toFixed(2), exc: +c.val.exc.toFixed(2), tExc: +c.val.tExc.toFixed(3) }, gate: c.why.length ? 'discovery' : 'validation', diagnostic: c.diagnostic } })),
    ];
    fs.writeFileSync(path.join(outDir, 'registry.jsonl'), rows.map((x) => JSON.stringify(x)).join('\n') + '\n');
    return;
  }
  console.log('usage: perpTaSweep.ts prep|sweep|report (see the header)');
  process.exitCode = 1;
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) main().catch((e) => { console.error(e); process.exitCode = 1; });
