// Perp TA round 4, PTA-R4-slow: one slow trend rule on the Kalshi perps (thread "Build a TA rulebook for perpetuals").
// Pre-registered in /mnt/project-files/perp-ta/preregistration.md, section "Round 4" (written Nov 5 2026, 7:39 PM EST /
// Nov 6 00:39 UTC, amended 7:42 and 7:45 PM EST, and 8:38 PM EST after the adversarial code review, all before any run on
// real data). Why: the failure diagnosis of rounds 1-3
// (/mnt/project-files/perp-ta/round4/diagnosis-plan.md): a fixed 17-25 bps round trip against signals that last minutes;
// only signals right for days to weeks, traded rarely, can clear it. One cell, every value fixed here (SLOW):
//
//   daily close  the Binance spot close of the 23:59 UTC minute, else the last spot close in the 60 minutes before 00:00
//   vote         v = sign(r7) + sign(r14) + sign(r28) at 00:00 UTC, r_k = ln(C_t / C_t-k days); a missing close: no vote
//   positions    flat -> long at +3, flat -> short at -3; long -> flat at v <= -1, short -> flat at v >= +1; a reversal on
//                the same day only at -3 (long to short) or +3 (short to long)
//   size         $250 x min(1, 0.02 / sigma30) at entry, sigma30 = sample stdev of the last 30 daily log returns, 1x
//   execution    post-only at the touch on the USD-M perp (buy at the last minute's close - half-spread, sell at + half-
//                spread, re-pegged every minute), filled when a minute trades 1 bp through it, at maker 5 bps; unfilled
//                after 60 minutes: taker at minute 61's open, 12 bps + half-spread. No stop, no target, no time cap.
//   funding      the sweep's Kalshi model (the grid's instants) plus the measured offsets, longs pay, on contracts x close
//   booking      marked to market at every 00:00 UTC; whole UTC days only
//
// Blocks: discovery (grid start .. 2023-12-31) and validation (2024-01-01 .. 2025-06-30) are kill-only gates (`gates` reads
// nothing at or after the seal, 2025-07-01). `sealed` reads the sealed block (to the lockbox cap, 2026-11-06 00:00 UTC, never
// later) only after both gates passed with this rule's hash; the workflow logs the opening on Drive before it runs.
//
//   node --import tsx research/perpTaSlow.ts gates  --grids data/perp-ta --history data --out out/slow [--macro dir]
//   node --import tsx research/perpTaSlow.ts sealed --grids data/perp-ta --history data --gates out/slow/gates.json --out out/slow [--macro dir]
//   node --import tsx research/perpTaSlow.ts macro  --data data/perp-ta/BTC.bin --history data/hist-BTC --forecasts dir --module-cache dir --end seal|lockbox --out out/macro/BTC.json

import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import { readGrid, type Grid } from './perpTaSweep';
import { spotFromCsv, rvTerciles } from './perpTaRegime';
import { ho1Of, type Ho1 } from './perpTaBlind';
import { regRow, runRef, type RegRow } from './perpTaRegistry';

const MIN = 60_000;
const DAY = 86_400_000;
const MPD = 1440;
const fin = Number.isFinite;

export const SLOW = {
  id: 'PTA-R4-slow', lookbacks: [7, 14, 28], sizeUsd: 250, volTarget: 0.02, volDays: 30, closeWithin: 60,
  pegMinutes: 60, ttBps: 1, makerBps: 5, takerBps: 12,
  half: { BTC: 0.19, ETH: 0.22, SOL: 1.23, XRP: 1.94 } as Record<string, number>,
  fundOff: { BTC: 1.66, ETH: 1.19, SOL: 0.14, XRP: 1.57 } as Record<string, number>,
  validFrom: Date.UTC(2024, 0, 1), seal: Date.UTC(2025, 6, 1), lockbox: Date.UTC(2026, 10, 6),
  shifts: 1000, minShift: 90, minEntries: 30, bootBlock: 16, bootResamples: 10_000, stressBps: 3,
  assets: ['BTC', 'ETH', 'SOL', 'XRP'],
};
/** What the result depends on: the constants and this file's source. A changed rule or simulator is a new hash, whose
 *  gates must be run again before the sealed block can be read. */
export function ruleHash(src = fs.readFileSync(new URL(import.meta.url), 'utf8')): string {
  return crypto.createHash('sha256').update(JSON.stringify(SLOW)).update(src).digest('hex').slice(0, 16);
}

export interface Spot { has: Uint8Array; close: Float64Array }
const NOVOTE = -128;

/** C[k] = the close known at day boundary k (minute k x 1440): the last spot bar among the 60 minutes before it; NaN if none. */
export function dailyCloses(spot: Spot, nDays: number): Float64Array {
  const C = new Float64Array(nDays + 1).fill(NaN);
  for (let k = 1; k <= nDays; k++) {
    for (let j = k * MPD - 1; j >= Math.max(0, k * MPD - SLOW.closeWithin); j--) {
      if (j < spot.has.length && spot.has[j] && spot.close[j] > 0) { C[k] = spot.close[j]; break; }
    }
  }
  return C;
}

/** v[k] in -3..3 (NOVOTE when a close is missing). */
export function votes(C: Float64Array): Int8Array {
  const v = new Int8Array(C.length).fill(NOVOTE), L = SLOW.lookbacks;
  for (let k = L[L.length - 1]; k < C.length; k++) {
    if (!(C[k] > 0) || L.some((l) => !(C[k - l] > 0))) continue;
    v[k] = L.reduce((a, l) => a + Math.sign(Math.log(C[k] / C[k - l])), 0);
  }
  return v;
}

/** sigma30[k]: the sample stdev of the 30 daily log returns ending at boundary k; NaN when one is missing. */
export function sigma30(C: Float64Array): Float64Array {
  const s = new Float64Array(C.length).fill(NaN), n = SLOW.volDays;
  for (let k = n; k < C.length; k++) {
    const r: number[] = [];
    for (let j = k - n + 1; j <= k; j++) { if (!(C[j] > 0 && C[j - 1] > 0)) break; r.push(Math.log(C[j] / C[j - 1])); }
    if (r.length < n) continue;
    const m = r.reduce((a, b) => a + b, 0) / n;
    s[k] = Math.sqrt(r.reduce((a, b) => a + (b - m) ** 2, 0) / (n - 1));
  }
  return s;
}

/** The rule's next side from the side held and the vote (v NOVOTE keeps the side). */
export function nextSide(side: number, v: number): number {
  if (v === NOVOTE) return side;
  if (side === 0) return v === 3 ? 1 : v === -3 ? -1 : 0;
  if (side > 0) return v === -3 ? -1 : v <= -1 ? 0 : 1;
  return v === 3 ? 1 : v >= 1 ? 0 : -1;
}

export type Variant = 'rule' | 'reversed' | 'long' | 'short' | 'always-long' | 'always-short' | 'taker' | 'macro';
export const DIAGNOSTICS: Variant[] = ['reversed', 'taker', 'long', 'short', 'always-long', 'always-short', 'macro'];

export interface CoinCosts {
  half: number; fundOff: number; maker?: number; taker?: number; tt?: number;
  /** extra bps on every fill (the +3 bps per side stress) */ extraBps?: number;
  /** funding stress: a payment the position makes x paidMult, one it receives x recvMult */ paidMult?: number; recvMult?: number;
  /** the Kalshi offset x offMult (0 = the Binance model alone) */ offMult?: number;
}

/** A closed position, or (open: true) the one still held when the simulation ends (exitMin NaN, marked at the last close). */
export interface Trade { side: number; entryMin: number; entryPx: number; qty: number; ter: number; exitMin: number; exitPx: number; usd: number; fees: number; funding: number; mae: number; taker: boolean[]; open?: boolean }

export interface CoinRun {
  asset: string; t0: number; nDays: number;
  /** Per day k (from boundary k to k + 1): marked-to-market $ and its parts. */
  mtm: Float64Array; price: Float64Array; fee: Float64Array; fund: Float64Array;
  /** Per day k and RV tercile t (index 3k + t): $ of the positions entered in tercile t (NA tercile: not counted). */
  terUsd: Float64Array;
  /** Per day k and tercile t: each hour's MTM in the tercile of the hour's first minute (reported only). */
  hourTerUsd: Float64Array;
  /** For the placebo: the signed notional held through day k (contracts after day k's fills x the boundary-k close), the
   *  position held then (0 = flat), the close-to-close return over day k and the day's funding rate (+ = longs pay). */
  notional: Float64Array; posId: Int32Array; ret: Float64Array; fundRate: Float64Array;
  /** 1 when a position was opened on day k. */
  entries: Uint8Array;
  trades: Trade[];
  /** Per day k: notional traded, fees paid, maker and taker fills, and what the taker fallbacks cost over a maker fill. */
  traded: Float64Array; fees: Float64Array; makerFills: Uint16Array; takerFills: Uint16Array; fallbackExtra: Float64Array;
  /** Orders placed, and orders carried over a 00:00 decision unfilled (no perp bar for nearly a day), in all and per day. */
  orders: number; carried: number; ordersDay: Uint16Array; carriedDay: Uint16Array;
  /** Minutes per RV tercile (0..2) and NA (3) per day k (index 4k + t), for HO-1's tercile hours. */
  terMinutes: Uint32Array;
}

interface Open { id: number; side: number; qty: number; entryMin: number; entryPx: number; ter: number; ref: number; fees: number; funding: number; worst: number; taker: boolean[] }
interface Order { dir: number; start: number; closeQty: number; openSide: number; openUsd: number }

/** The rule (or a diagnostic variant) on one coin over minutes [0, nMax): only whole days (boundaries 1 .. floor(nMax / 1440)
 *  are marked; decisions at boundaries 1 .. nDays - 1). ter: the RV tercile per minute (Int8, -1 NA). macro: per boundary,
 *  the bot's macro_trend confluence state (-1 / 0 / 1), for the 'macro' variant. */
export function simulate(g: Grid, spot: Spot, nMax: number, cc: CoinCosts, o: { variant?: Variant; ter?: Int8Array; macro?: Int8Array } = {}): CoinRun {
  if (g.t0 % DAY !== 0) throw new Error(`${g.asset}: grid does not start at a UTC midnight`);
  nMax = Math.min(nMax, g.n, spot.has.length);
  const variant = o.variant ?? 'rule', { po, ph, pl, pc, valid, fund } = g.c;
  const nDays = Math.floor(nMax / MPD);
  const C = dailyCloses(spot, nDays), V = votes(C), S = sigma30(C);
  const h = cc.half / 1e4, tt = (cc.tt ?? SLOW.ttBps) / 1e4, extra = (cc.extraBps ?? 0) / 1e4;
  const mk = (cc.maker ?? SLOW.makerBps) / 1e4 + extra, tk = ((cc.taker ?? SLOW.takerBps) + cc.half) / 1e4 + extra;
  const off = (cc.fundOff / 1e4) * (cc.offMult ?? 1), paidMult = cc.paidMult ?? 1, recvMult = cc.recvMult ?? 1;
  const z = () => new Float64Array(nDays);
  const run: CoinRun = {
    asset: g.asset, t0: g.t0, nDays, mtm: z(), price: z(), fee: z(), fund: z(), terUsd: new Float64Array(3 * nDays), hourTerUsd: new Float64Array(3 * nDays),
    notional: z(), posId: new Int32Array(nDays), ret: z(), fundRate: z(), entries: new Uint8Array(nDays), trades: [],
    traded: z(), fees: z(), makerFills: new Uint16Array(nDays), takerFills: new Uint16Array(nDays), fallbackExtra: z(), orders: 0, carried: 0,
    ordersDay: new Uint16Array(nDays), carriedDay: new Uint16Array(nDays), terMinutes: new Uint32Array(4 * nDays),
  };
  const terAt = (i: number) => (o.ter && i < o.ter.length ? o.ter[i] : -1);
  // A perp bar exists at minute i when the minute is valid, or when it is not the grid's fill of a missing perp bar (po = ph
  // = pl = pc = the last close; research/perpTaSweep.ts buildGrid): a minute with a perp bar but no spot bar still fills.
  const perpBar = (i: number) => pc[i] > 0 && (valid[i] === 1 || !(po[i] === pc[i - 1] && ph[i] === po[i] && pl[i] === po[i] && pc[i] === po[i]));
  let pos = null as Open | null, order = null as Order | null, nextId = 1, logical = 0;
  // Cash buckets: price (-qty x fill price), fees, funding; equity = their sum + qty x mark.
  let cashP = 0, cashFee = 0, cashFund = 0, lastE = 0, lastEP = 0, lastEFee = 0, lastEFund = 0, lastEH = 0;
  const qtyNow = () => (pos ? pos.side * pos.qty : 0);
  const addTer = (day: number, ter: number, usd: number) => { if (day >= 0 && day < nDays && ter >= 0 && ter <= 2) run.terUsd[3 * day + ter] += usd; };

  const fill = (i: number, px: number, isTaker: boolean) => {
    const ord = order!, day = Math.floor(i / MPD), rate = isTaker ? tk : mk;
    (isTaker ? run.takerFills : run.makerFills)[day]++;
    if (ord.closeQty > 0 && pos) {
      const q = pos.qty, fee = q * px * rate;
      cashP += pos.side * q * px; cashFee -= fee; run.traded[day] += q * px; run.fees[day] += fee;
      addTer(day, pos.ter, pos.side * q * (px - pos.ref) - fee);
      pos.fees += fee; pos.taker.push(isTaker);
      const usd = pos.side * q * (px - pos.entryPx) - pos.fees - pos.funding;
      run.trades.push({ side: pos.side, entryMin: pos.entryMin, entryPx: pos.entryPx, qty: q, ter: pos.ter, exitMin: i, exitPx: px, usd, fees: pos.fees, funding: pos.funding, mae: pos.worst, taker: pos.taker });
      pos = null;
    }
    if (ord.openSide !== 0) {
      const q = ord.openUsd / px, fee = q * px * rate, ter = terAt(i);
      cashP -= ord.openSide * q * px; cashFee -= fee; run.traded[day] += q * px; run.fees[day] += fee;
      pos = { id: nextId++, side: ord.openSide, qty: q, entryMin: i, entryPx: px, ter, ref: px, fees: fee, funding: 0, worst: 0, taker: [isTaker] };
      addTer(day, ter, -fee);
      run.entries[day] = 1;
    }
    order = null;
  };

  for (let i = MPD; i <= nDays * MPD; i++) {
    // Hourly attribution (reported only): the hour that ends now, in the tercile of its first minute.
    if (i % 60 === 0) {
      const EH = cashP + cashFee + cashFund + qtyNow() * pc[i - 1];
      const d = Math.floor((i - 1) / MPD), t = terAt(i - 60);
      if (t >= 0 && t <= 2 && d < nDays) run.hourTerUsd[3 * d + t] += EH - lastEH;
      lastEH = EH;
    }
    if (i % MPD === 0) {
      // Boundary k: mark day k - 1 (with the close of minute i - 1: nothing at or after nMax is read), then decide.
      const k = i / MPD, m = pc[i - 1];
      const E = cashP + cashFee + cashFund + qtyNow() * m;
      run.mtm[k - 1] = E - lastE; run.price[k - 1] = cashP + qtyNow() * m - lastEP; run.fee[k - 1] = cashFee - lastEFee; run.fund[k - 1] = cashFund - lastEFund;
      if (pos) { addTer(k - 1, pos.ter, pos.side * pos.qty * (m - pos.ref)); pos.ref = m; }
      lastE = E; lastEP = cashP + qtyNow() * m; lastEFee = cashFee; lastEFund = cashFund;
      if (k === nDays) break;
      // An order still unfilled at the next 00:00 (no perp bar for nearly a day) is kept: its taker fallback takes the first
      // minute with a perp bar (item 14), and this boundary's vote is not acted on (amendment before any run, Nov 5 2026).
      if (order) { run.carried++; run.carriedDay[k]++; }
      else {
        let want: number;
        if (variant === 'always-long' || variant === 'always-short') want = variant === 'always-long' ? 1 : -1;
        else if (variant === 'macro') { const st = o.macro ? o.macro[k] ?? 0 : 0; if (st !== 0) logical = st; want = logical; }
        else {
          logical = nextSide(logical, V[k]);
          want = variant === 'reversed' ? -logical : variant === 'long' ? Math.max(0, logical) : variant === 'short' ? Math.min(0, logical) : logical;
        }
        const held = pos ? pos.side : 0;
        if (want !== held) {
          const usd = SLOW.sizeUsd * Math.min(1, SLOW.volTarget / S[k]);
          const canOpen = want !== 0 && fin(usd) && usd > 0, openSide = canOpen ? want : 0;
          // No entry without 30 daily returns: the rule stays flat and needs its entry vote again (always-* retry daily).
          if (want !== 0 && !canOpen && variant !== 'always-long' && variant !== 'always-short') logical = 0;
          if (held !== 0 || openSide !== 0) {
            order = { dir: held !== 0 ? -held : openSide, start: i, closeQty: held !== 0 ? 1 : 0, openSide, openUsd: openSide ? usd : 0 };
            run.orders++; run.ordersDay[k]++;
          }
        }
      }
    }
    // The resting order.
    if (order) {
      if (variant === 'taker') { if (perpBar(i)) fill(i, po[i], true); }
      else if (i < order.start + SLOW.pegMinutes) {
        const q = pc[i - 1] * (1 - order.dir * h);
        if (perpBar(i) && q > 0 && (order.dir > 0 ? pl[i] <= q * (1 - tt) : ph[i] >= q * (1 + tt))) fill(i, q, false);
      } else if (perpBar(i)) {
        const lastPeg = pc[order.start + SLOW.pegMinutes - 2] * (1 - order.dir * h), size = (order.closeQty && pos ? pos.qty * po[i] : 0) + order.openUsd;
        run.fallbackExtra[Math.floor(i / MPD)] += size * (tk - mk) + (order.dir * (po[i] - lastPeg) * size) / po[i];
        fill(i, po[i], true);
      }
    }
    // The position's adverse excursion (minutes with a perp bar) and funding at the end of the minute (after its fills).
    if (pos && perpBar(i)) { const a = pos.side > 0 ? pl[i] / pos.entryPx - 1 : 1 - ph[i] / pos.entryPx; if (a < pos.worst) pos.worst = a; }
    const f = fund[i], day = Math.floor(i / MPD);
    if (fin(f) && f !== 0) {
      const r = (Math.abs(f) < 1e-9 ? 0 : f) + off;
      if (day < nDays) run.fundRate[day] += r;
      if (pos) {
        let pay = pos.side * pos.qty * pc[i] * r;
        pay *= pay > 0 ? paidMult : recvMult;
        cashFund -= pay; pos.funding += pay; addTer(day, pos.ter, -pay);
      }
    }
    // The placebo's daily series: the position at the day's end (its last minute).
    if (i % MPD === MPD - 1) {
      const k = day, m0 = pc[k * MPD - 1];
      run.notional[k] = qtyNow() * m0; run.posId[k] = pos ? pos.id : 0; run.ret[k] = pc[i] / m0 - 1;
    }
    const t = terAt(i);
    if (day < nDays) run.terMinutes[4 * day + (t >= 0 && t <= 2 ? t : 3)]++;
  }
  // The position still held at the end: reported (adverse excursion, entries) as an open trade marked at the last close.
  if (pos && nDays > 0) {
    const m = pc[nDays * MPD - 1];
    run.trades.push({ side: pos.side, entryMin: pos.entryMin, entryPx: pos.entryPx, qty: pos.qty, ter: pos.ter, exitMin: NaN, exitPx: m, usd: pos.side * pos.qty * (m - pos.entryPx) - pos.fees - pos.funding, fees: pos.fees, funding: pos.funding, mae: pos.worst, taker: pos.taker, open: true });
  }
  return run;
}

// ---------------------------------------------------------------------------------------------------------------
// Blocks, the placebo and the pass rules.

export interface Block { name: 'discovery' | 'validation' | 'sealed'; from: number; to: number }
export const dayKey = (t0: number, k: number) => new Date(t0 + k * DAY).toISOString().slice(0, 10);
const dayRange = (r: CoinRun, b: Block): [number, number] => [Math.max(1, Math.ceil((b.from - r.t0) / DAY)), Math.min(r.nDays, Math.floor((b.to - r.t0) / DAY))];

/** The block's common calendar: absolute day numbers [G0, G0 + N) covering every coin's days [a, b). */
function calendar(runs: CoinRun[], a: number[], b: number[]): { G0: number; N: number } {
  const st = runs.map((r, i) => Math.floor(r.t0 / DAY) + a[i]), en = runs.map((r, i) => Math.floor(r.t0 / DAY) + b[i]);
  const ok = runs.map((_, i) => b[i] > a[i]);
  const G0 = Math.min(...st.filter((_, i) => ok[i])), G1 = Math.max(...en.filter((_, i) => ok[i]));
  return { G0, N: fin(G0) && fin(G1) ? G1 - G0 : 0 };
}

/** The book's daily series priced at daily resolution (each coin: notional x the day's return, minus the day's funding on
 *  the notional, minus c x the notional traded when the position changes), every coin's position series shifted by the same
 *  s days on the block's common calendar with wrap (a coin is flat on calendar days it has no data for). */
export function dailyPriced(runs: CoinRun[], a: number[], b: number[], c: number[], s: number): number {
  const { G0, N } = calendar(runs, a, b);
  let total = 0;
  if (!(N > 0)) return total;
  runs.forEach((r, ci) => {
    if (b[ci] <= a[ci]) return;
    const d0 = Math.floor(r.t0 / DAY);
    let prevN = 0, prevId = -1;
    for (let k = a[ci]; k < b[ci]; k++) {
      const gs = ((((d0 + k - G0 - s) % N) + N) % N), j = gs + G0 - d0;
      const inData = j >= a[ci] && j < b[ci], Nn = inData ? r.notional[j] : 0, id = inData ? r.posId[j] : 0;
      total += Nn * r.ret[k] - Nn * r.fundRate[k];
      if (k > a[ci] && id !== prevId) total -= c[ci] * (Math.abs(prevN) + Math.abs(Nn));
      prevN = Nn * (1 + r.ret[k]); prevId = id;
    }
  });
  return total;
}

function rng(seed: number): () => number { let x = seed >>> 0; return () => { x = (x + 0x6d2b79f5) >>> 0; let t = x; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

export interface Placebo { rule: number; mean: number; percentile: number; shifts: number }
/** 1,000 common circular shifts (k uniform on 90 .. N - 90 days of the block's calendar) of all coins' daily series together. */
export function placebo(runs: CoinRun[], blk: Block, seed: number, shifts = SLOW.shifts): Placebo {
  const ab = runs.map((r) => dayRange(r, blk)), a = ab.map((x) => x[0]), b = ab.map((x) => x[1]);
  // The rule's realised cost per $ traded in the block (fees, the taker legs' half-spread), each coin's own.
  const c = runs.map((r, i) => { let f = 0, t = 0; for (let k = a[i]; k < b[i]; k++) { f += r.fees[k]; t += r.traded[k]; } return t > 0 ? f / t : SLOW.makerBps / 1e4; });
  const { N } = calendar(runs, a, b);
  const rule = dailyPriced(runs, a, b, c, 0);
  if (!(N > 2 * SLOW.minShift)) return { rule, mean: NaN, percentile: NaN, shifts: 0 };
  const r = rng(seed), vals: number[] = [];
  for (let k = 0; k < shifts; k++) vals.push(dailyPriced(runs, a, b, c, SLOW.minShift + Math.floor(r() * (N - 2 * SLOW.minShift + 1))));
  const mean = vals.reduce((x, y) => x + y, 0) / vals.length;
  return { rule, mean, percentile: vals.filter((v) => v < rule).length / vals.length, shifts };
}

export interface BlockResult {
  block: Block['name']; days: number; from: string; to: string; usd: number; usdPerHour: number; priceUsd: number; feeUsd: number; fundUsd: number;
  byCoin: Record<string, number>; entries: number; entriesByCoin: Record<string, number>; effectiveBets: number; meanPairCorr: number;
  meanGrossUsd: number; placebo: Placebo; byDay: Record<string, number>; months: Record<string, number>; bestMonthShare: number;
  lb90: number; fills: { orders: number; maker: number; taker: number; carried: number; fallbackExtraUsd: number; tradedUsd: number; feesUsd: number };
  /** Item 9's hourly attribution: each hour's MTM in the RV tercile of its first minute (LOW, MID, HIGH), $ and $/h over the
   *  coins' mean hours in each tercile (HO-1's tercile hours). Reported, never judged. */
  hourTer: { usd: number[]; usdPerHour: Array<number | null>; hours: number[] };
  worstMae: number; liqHits: number; trades: number;
  /** Exit-day booking (each trade's $ on its exit day; trades exited in the block), by side; the open book at the block's end. */
  exitBookedUsd: number; bySide: { long: number; short: number }; openAtEnd: number;
  /** Daily Sharpe of the block's daily MTM, annualised (x sqrt 365), and its standard error (Lo 2002, iid). */
  sharpe: number; sharpeSe: number;
}

export function blockResult(runs: CoinRun[], blk: Block, seed: number, o: { resamples?: number } = {}): BlockResult {
  const ab = runs.map((r) => dayRange(r, blk));
  const from = Math.min(...ab.map((x, i) => runs[i].t0 + x[0] * DAY)), to = Math.max(...ab.map((x, i) => runs[i].t0 + x[1] * DAY));
  const byDay: Record<string, number> = {};
  for (let t = from; t < to; t += DAY) byDay[new Date(t).toISOString().slice(0, 10)] = 0;
  const byCoin: Record<string, number> = {}, entriesByCoin: Record<string, number> = {};
  let usd = 0, priceUsd = 0, feeUsd = 0, fundUsd = 0, entries = 0, gross = 0, worstMae = 0, liqHits = 0, trades = 0, exitBooked = 0, openAtEnd = 0;
  const bySide = { long: 0, short: 0 };
  const fills = { orders: 0, maker: 0, taker: 0, carried: 0, fallbackExtraUsd: 0, tradedUsd: 0, feesUsd: 0 };
  const series: Array<{ start: number; v: number[] }> = [], hT = [0, 0, 0], hM = [0, 0, 0];
  runs.forEach((r, ci) => {
    const [a, b] = ab[ci], s: number[] = [];
    let u = 0, e = 0;
    for (let k = a; k < b; k++) {
      const key = dayKey(r.t0, k);
      byDay[key] = (byDay[key] ?? 0) + r.mtm[k]; u += r.mtm[k]; s.push(r.mtm[k]);
      priceUsd += r.price[k]; feeUsd += r.fee[k]; fundUsd += r.fund[k]; e += r.entries[k]; gross += Math.abs(r.notional[k]);
      fills.maker += r.makerFills[k]; fills.taker += r.takerFills[k]; fills.fallbackExtraUsd += r.fallbackExtra[k]; fills.tradedUsd += r.traded[k]; fills.feesUsd += r.fees[k];
      fills.orders += r.ordersDay[k]; fills.carried += r.carriedDay[k];
      for (let t = 0; t < 3; t++) { hT[t] += r.hourTerUsd[3 * k + t]; hM[t] += r.terMinutes[4 * k + t]; }
    }
    series.push({ start: Math.floor(r.t0 / DAY) + a, v: s }); byCoin[r.asset] = +u.toFixed(2); entriesByCoin[r.asset] = e; usd += u; entries += e;
    const lo = r.t0 + a * MPD * MIN, hi = r.t0 + b * MPD * MIN;
    for (const tr of r.trades) {
      const te = r.t0 + tr.entryMin * MIN, tx = r.t0 + tr.exitMin * MIN;
      if (tx >= lo && tx < hi) { exitBooked += tr.usd; bySide[tr.side > 0 ? 'long' : 'short'] += tr.usd; }
      if (te < lo || te >= hi) continue;
      trades++; if (tr.mae < worstMae) worstMae = tr.mae; if (tr.mae <= -1 / 3) liqHits++;
    }
    if (b > a && r.posId[b - 1] !== 0) openAtEnd++;
  });
  const days = Object.keys(byDay).length;
  // Mean pairwise correlation of the coins' daily P&L on the calendar days both cover, and the effective number of bets.
  const corr = (X: { start: number; v: number[] }, Y: { start: number; v: number[] }) => {
    const lo = Math.max(X.start, Y.start), hi = Math.min(X.start + X.v.length, Y.start + Y.v.length), n = hi - lo;
    if (n < 3) return NaN;
    const x = X.v.slice(lo - X.start, hi - X.start), y = Y.v.slice(lo - Y.start, hi - Y.start);
    const mx = x.reduce((a, b) => a + b, 0) / n, my = y.reduce((a, b) => a + b, 0) / n;
    let sxy = 0, sxx = 0, syy = 0; for (let i = 0; i < n; i++) { sxy += (x[i] - mx) * (y[i] - my); sxx += (x[i] - mx) ** 2; syy += (y[i] - my) ** 2; }
    return sxx > 0 && syy > 0 ? sxy / Math.sqrt(sxx * syy) : NaN;
  };
  const cs: number[] = [];
  for (let i = 0; i < series.length; i++) for (let j = i + 1; j < series.length; j++) { const c = corr(series[i], series[j]); if (c === c) cs.push(c); }
  const rho = cs.length ? cs.reduce((a, b) => a + b, 0) / cs.length : 0;
  const effectiveBets = entries / (1 + (runs.length - 1) * Math.max(0, rho));
  const months: Record<string, number> = {};
  for (const [d, v] of Object.entries(byDay)) months[d.slice(0, 7)] = (months[d.slice(0, 7)] ?? 0) + v;
  const best = Math.max(0, ...Object.values(months));
  // Circular 16-day block bootstrap of the mean daily P&L.
  const daily = Object.keys(byDay).sort().map((d) => byDay[d]), R = o.resamples ?? SLOW.bootResamples, Bk = SLOW.bootBlock, r = rng(seed ^ 0x9e3779b9);
  const means = new Float64Array(R);
  if (daily.length) for (let k = 0; k < R; k++) {
    let s = 0, cnt = 0;
    while (cnt < daily.length) { const st = Math.floor(r() * daily.length); for (let j = 0; j < Bk && cnt < daily.length; j++, cnt++) s += daily[(st + j) % daily.length]; }
    means[k] = s / daily.length;
  }
  means.sort();
  const dm = daily.length ? daily.reduce((x, y) => x + y, 0) / daily.length : NaN;
  const dsd = daily.length > 1 ? Math.sqrt(daily.reduce((x, y) => x + (y - dm) ** 2, 0) / (daily.length - 1)) : NaN;
  const srd = dsd > 0 ? dm / dsd : NaN, srSe = daily.length ? Math.sqrt((1 + 0.5 * srd * srd) / daily.length) : NaN;
  return {
    block: blk.name, days, from: new Date(from).toISOString().slice(0, 10), to: new Date(to - DAY).toISOString().slice(0, 10),
    usd: +usd.toFixed(2), usdPerHour: days ? +(usd / (days * 24)).toFixed(4) : NaN, priceUsd: +priceUsd.toFixed(2), feeUsd: +feeUsd.toFixed(2), fundUsd: +fundUsd.toFixed(2),
    byCoin, entries, entriesByCoin, effectiveBets: +effectiveBets.toFixed(1), meanPairCorr: +rho.toFixed(3), meanGrossUsd: days ? +(gross / days).toFixed(1) : 0,
    placebo: placebo(runs, blk, seed), byDay, months, bestMonthShare: usd > 0 ? +(best / usd).toFixed(3) : NaN,
    lb90: daily.length ? +(means[Math.floor(0.1 * R)] / 24).toFixed(4) : NaN,
    fills: { ...fills, fallbackExtraUsd: +fills.fallbackExtraUsd.toFixed(2), tradedUsd: +fills.tradedUsd.toFixed(2), feesUsd: +fills.feesUsd.toFixed(2) },
    worstMae: +worstMae.toFixed(4), liqHits, trades,
    exitBookedUsd: +exitBooked.toFixed(2), bySide: { long: +bySide.long.toFixed(2), short: +bySide.short.toFixed(2) }, openAtEnd,
    sharpe: +(srd * Math.sqrt(365)).toFixed(3), sharpeSe: +(srSe * Math.sqrt(365)).toFixed(3),
    hourTer: (() => { const hours = hM.map((m) => m / 60 / Math.max(1, runs.length)); return { usd: hT.map((v) => +v.toFixed(2)), usdPerHour: hT.map((v, t) => (hours[t] > 0 ? +(v / hours[t]).toFixed(4) : null)), hours: hours.map((x) => +x.toFixed(1)) }; })(),
  };
}

/** HO-1 on a block: folds from the daily MTM; terciles at entry (the positions' $ by entry tercile, hours = the coins' mean
 *  minutes in each tercile); the placebo is the circular-shift mean (the rule priced the same way must beat it). */
export function ho1Slow(runs: CoinRun[], blk: Block, br: BlockResult): Ho1 {
  const ter = [0, 0, 0, 0], mins = [0, 0, 0];
  runs.forEach((r) => {
    const [a, b] = dayRange(r, blk);
    let na = 0;
    for (let k = a; k < b; k++) { for (let t = 0; t < 3; t++) { ter[t] += r.terUsd[3 * k + t]; mins[t] += r.terMinutes[4 * k + t]; } na += r.mtm[k] - r.terUsd[3 * k] - r.terUsd[3 * k + 1] - r.terUsd[3 * k + 2]; }
    ter[3] += na;
  });
  const terHours = mins.map((m) => m / 60 / runs.length);
  const taken = [0, 1, 2, -1].map((t, i) => ({ x: ter[i] * 1e4, ter: t }));
  return ho1Of(br.byDay, taken, terHours, 1, { placebo: { usd: br.placebo.rule, placeboUsd: br.placebo.mean } });
}

export interface Gate { block: Block['name']; pass: boolean; why: string[]; result: BlockResult }
export function gateOf(br: BlockResult): Gate {
  const why: string[] = [];
  if (!(br.usd > 0)) why.push(`${br.block}: net $${br.usd} <= 0`);
  // Item 8: net above its placebo mean; the rule priced as its shifts are must be above it too.
  if (!(br.usd > br.placebo.mean)) why.push(`${br.block}: net $${br.usd} not above the placebo mean $${br.placebo.mean.toFixed(2)}`);
  if (!(br.placebo.rule > br.placebo.mean)) why.push(`${br.block}: $${br.placebo.rule.toFixed(2)} (daily priced) not above the placebo mean $${br.placebo.mean.toFixed(2)}`);
  return { block: br.block, pass: !why.length, why, result: br };
}

export interface Stress { stress3: number; fundStress: number; offset0: number; offset2: number }
export interface Verdict { pass: boolean; inconclusive: boolean; status: string; why: string[] }
/** status: INCONCLUSIVE (fewer than 30 entries: never a pass), PASS (provisional), 'FAIL: edge not refuted, HO-1 not met'
 *  (above its placebo but the folds fail: item 12), or FAIL. */
export function sealedVerdict(br: BlockResult, ho1: Ho1, st: Stress): Verdict {
  const why = [...ho1.why];
  const c = br.byCoin;
  if (!(br.lb90 > 0)) why.push(`bootstrap 90% lower bound $${br.lb90}/h <= 0`);
  if (!((c.BTC ?? 0) > 0 && (c.ETH ?? 0) > 0 && ((c.SOL ?? 0) > 0 || (c.XRP ?? 0) > 0))) why.push('not positive on BTC, ETH and one of SOL / XRP');
  if (!(br.usd > 0 && br.bestMonthShare <= 0.5)) why.push(br.usd > 0 ? `best month holds ${(br.bestMonthShare * 100).toFixed(0)}% of the gain` : 'no gain');
  if (!(st.stress3 > 0)) why.push(`not above 0 at +${SLOW.stressBps} bps per side ($${st.stress3})`);
  if (!(st.fundStress > 0)) why.push(`not above 0 with funding paid x1.5, received x0.5 ($${st.fundStress})`);
  if (!(st.offset0 > 0)) why.push(`not above 0 with the Kalshi funding offset at 0 ($${st.offset0})`);
  if (!(st.offset2 > 0)) why.push(`not above 0 with the Kalshi funding offset x2 ($${st.offset2})`);
  if (!(br.priceUsd > 0)) why.push(`price-only P&L $${br.priceUsd} <= 0 (a pass cannot come from funding)`);
  const inconclusive = br.entries < SLOW.minEntries;
  if (inconclusive) why.push(`INCONCLUSIVE: ${br.entries} entries < ${SLOW.minEntries}`);
  const foldsFail = ho1.why.some((w) => /folds won|worst fold|held-out days/.test(w));
  const status = inconclusive ? 'INCONCLUSIVE' : !why.length ? 'PASS (provisional)' : ho1.beats_placebo && foldsFail ? 'FAIL: edge not refuted, HO-1 not met' : 'FAIL';
  return { pass: !why.length, inconclusive, status, why };
}

// ---------------------------------------------------------------------------------------------------------------
// One evaluation over all coins: the rule, its stresses and the diagnostics, on the blocks asked for.

export interface CoinData { g: Grid; spot: Spot; ter: Int8Array; macro?: Int8Array }
export interface Evaluation { hash: string; nMax: Record<string, number>; blocks: Record<string, { rule: BlockResult; gate?: Gate; ho1?: Ho1; stress?: Stress; verdict?: Verdict; diagnostics: Record<string, Partial<BlockResult> & { notRun?: string }> }> }

export function evaluate(coins: CoinData[], end: number, blocks: Block[], hash: string, o: { resamples?: number; shifts?: number } = {}): Evaluation {
  const seed = parseInt(hash.slice(0, 8), 16) || 1;
  const nMaxOf = (cd: CoinData) => Math.max(0, Math.min(cd.g.n, Math.floor((end - cd.g.t0) / MIN)));
  const costsOf = (a: string): CoinCosts => {
    if (!(a in SLOW.half) || !(a in SLOW.fundOff)) throw new Error(`${a}: no pre-registered costs`);
    return { half: SLOW.half[a], fundOff: SLOW.fundOff[a] };
  };
  const runAll = (variant: Variant, extra: Partial<CoinCosts> = {}) => coins.map((cd) => simulate(cd.g, cd.spot, nMaxOf(cd), { ...costsOf(cd.g.asset), ...extra }, { variant, ter: cd.ter, macro: cd.macro }));
  const base = runAll('rule');
  const out: Evaluation = { hash, nMax: Object.fromEntries(coins.map((cd) => [cd.g.asset, nMaxOf(cd)])), blocks: {} };
  const variants: Record<string, CoinRun[] | string> = {};
  for (const v of DIAGNOSTICS) variants[v] = v === 'macro' && coins.some((cd) => !cd.macro) ? 'the macro_trend states were not computed' : runAll(v);
  const sealedBlk = blocks.find((b) => b.name === 'sealed');
  const stressRuns = sealedBlk ? { s3: runAll('rule', { extraBps: SLOW.stressBps }), fs: runAll('rule', { paidMult: 1.5, recvMult: 0.5 }), o0: runAll('rule', { offMult: 0 }), o2: runAll('rule', { offMult: 2 }) } : undefined;
  for (const blk of blocks) {
    const rule = blockResult(base, blk, seed, o);
    if (o.shifts !== undefined) rule.placebo = placebo(base, blk, seed, o.shifts);
    const diagnostics: Evaluation['blocks'][string]['diagnostics'] = {};
    for (const [v, rs] of Object.entries(variants)) {
      if (typeof rs === 'string') { diagnostics[v] = { notRun: rs }; continue; }
      const d = blockResult(rs, blk, seed, { resamples: 1 });
      diagnostics[v] = { usd: d.usd, usdPerHour: d.usdPerHour, priceUsd: d.priceUsd, feeUsd: d.feeUsd, fundUsd: d.fundUsd, entries: d.entries, byCoin: d.byCoin };
    }
    const e: Evaluation['blocks'][string] = { rule, diagnostics };
    if (blk.name === 'sealed' && stressRuns) {
      const tot = (rs: CoinRun[]) => blockResult(rs, blk, seed, { resamples: 1 }).usd;
      e.stress = { stress3: tot(stressRuns.s3), fundStress: tot(stressRuns.fs), offset0: tot(stressRuns.o0), offset2: tot(stressRuns.o2) };
      e.ho1 = ho1Slow(base, blk, rule);
      e.verdict = sealedVerdict(rule, e.ho1, e.stress);
    } else e.gate = gateOf(rule);
    out.blocks[blk.name] = e;
  }
  return out;
}

// ---------------------------------------------------------------------------------------------------------------
// Report and registry rows.

const usdH1k = (b: BlockResult) => b.usdPerHour; // the book's notional is capped at $1,000: $/h of the book = $/h per $1k cap

export function markdown(ev: Evaluation, mode: 'gates' | 'sealed'): string {
  const L: string[] = [];
  L.push(`### Perp TA round 4, PTA-R4-slow (${mode}; rule hash ${ev.hash})`);
  L.push('One pre-registered rule: hold each coin in the direction its 7-, 14- and 28-day Binance spot returns all agree on, flat once two of three turn; post-only at the touch with a 60-minute taker fallback; $250 x min(1, 2% / 30-day vol) per coin. Target: $4.50/h; the column below is $/h of a book capped at $1,000 (= $/h per $1k).');
  L.push('');
  L.push('| block | days | net $ | $/h per $1k | price $ | funding $ | fees $ | entries | effective bets | placebo mean $ (daily priced; rule $) | percentile | lb90 $/h | best month | by coin $ | verdict |');
  L.push('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|');
  for (const [name, b] of Object.entries(ev.blocks)) {
    const r = b.rule, v = b.gate ? (b.gate.pass ? 'gate PASS' : `gate FAIL: ${b.gate.why.join('; ')}`) : b.verdict ? (b.verdict.pass ? '**PASS** (provisional until the recorded-quote forward check)' : `${b.verdict.status}: ${b.verdict.why.join('; ')}`) : '';
    L.push(`| ${name} | ${r.days} (${r.from} .. ${r.to}) | ${r.usd} | ${usdH1k(r)} | ${r.priceUsd} | ${r.fundUsd} | ${r.feeUsd} | ${r.entries} | ${r.effectiveBets} (rho ${r.meanPairCorr}) | ${r.placebo.mean.toFixed(2)} (${r.placebo.rule.toFixed(2)}) | ${r.placebo.percentile} | ${r.lb90} | ${r.bestMonthShare} | ${Object.entries(r.byCoin).map(([k, x]) => `${k} ${x}`).join(', ')} | ${v} |`);
  }
  L.push('');
  for (const [name, b] of Object.entries(ev.blocks)) {
    const f = b.rule.fills;
    L.push(`- ${name}: Sharpe ${b.rule.sharpe} (SE ${b.rule.sharpeSe}, annualised from daily MTM); exit-day booking $${b.rule.exitBookedUsd} (long $${b.rule.bySide.long}, short $${b.rule.bySide.short}; ${b.rule.openAtEnd} coins still open at the block's end).`);
    L.push(`- ${name}: orders ${f.orders} (${f.carried} carried over a 00:00 unfilled); fills maker ${f.maker}, taker fallback ${f.taker} (${f.maker + f.taker ? ((100 * f.taker) / (f.maker + f.taker)).toFixed(0) : 0}%), fallback cost over a maker fill $${f.fallbackExtraUsd}; worst adverse excursion ${(100 * b.rule.worstMae).toFixed(1)}% (${b.rule.liqHits} beyond a 3x liquidation distance of 33%); mean gross $${b.rule.meanGrossUsd}.`);
    L.push(`- ${name}: hourly attribution (each hour's MTM in its RV tercile; reported only) LOW/MID/HIGH $${b.rule.hourTer.usd.join(' / ')}, $/h ${b.rule.hourTer.usdPerHour.map((x) => x ?? 'n/a').join(' / ')} (${b.rule.hourTer.hours.join(' / ')} h).`);
    if (b.ho1) L.push(`- HO-1: folds won ${b.ho1.folds_won}/${b.ho1.folds} ($/h ${b.ho1.fold_usd_per_hour.join(', ')}); RV terciles LOW/MID/HIGH $/h ${b.ho1.tercile_usd_per_hour.map((x) => x ?? 'n/a').join(' / ')} (${b.ho1.tercile_hours.join(' / ')} h); placebo: rule $${b.rule.placebo.rule.toFixed(2)} vs mean $${b.rule.placebo.mean.toFixed(2)}.`);
    if (b.stress) L.push(`- Stresses: +${SLOW.stressBps} bps per side $${b.stress.stress3}; funding paid x1.5 / received x0.5 $${b.stress.fundStress}; Kalshi offset 0 $${b.stress.offset0}, x2 $${b.stress.offset2}.`);
    L.push(`- Diagnostics (counted, never candidates): ${Object.entries(b.diagnostics).map(([k, d]) => (d.notRun ? `${k}: not run (${d.notRun})` : `${k} $${d.usd} (price ${d.priceUsd}, funding ${d.fundUsd}, fees ${d.feeUsd}, ${d.entries} entries)`)).join('; ')}.`);
  }
  return L.join('\n');
}

export function registryRows(ev: Evaluation, mode: 'gates' | 'sealed', sha: string, run: string, at = new Date()): RegRow[] {
  const epoch = `perp-ta round 4 slow (${ev.hash})`, ref = runRef(run), rows: RegRow[] = [];
  for (const [name, b] of Object.entries(ev.blocks)) {
    const held = name === 'sealed';
    const flat = regRow({ arm: `r4:slow:${name}:flat`, role: 'control', round: 4, codeSha: sha, codeEpoch: epoch, byDay: Object.fromEntries(Object.keys(b.rule.byDay).map((d) => [d, 0])), ref, at, heldOut: held, verdict: 'flat: no position' });
    const ho = b.ho1 ? (({ fold_usd_per_hour: _f, tercile_usd_per_hour: _t, tercile_hours: _h, placebo_usd: _p, why: _w, worst_tercile_per_hour: wt, ...h }) => ({ ...h, ...(wt === null ? {} : { worst_tercile_per_hour: wt }) }))(b.ho1) : undefined;
    const verdict = b.gate ? (b.gate.pass ? 'gate PASS' : b.gate.why.join('; ')) : b.verdict ? (b.verdict.pass ? 'PASS (provisional)' : `${b.verdict.status}: ${b.verdict.why.join('; ')}`) : '';
    rows.push(flat, regRow({ arm: `r4:slow:${name}`, role: 'candidate', round: 4, control: flat.trial_id, codeSha: sha, codeEpoch: epoch, byDay: b.rule.byDay, fills: b.rule.trades, ref, at, heldOut: held, heldout: ho, verdict, raw: { kind: 'r4-slow', hash: ev.hash, mode, block: name, usd_per_hour_per_1k: b.rule.usdPerHour, target_usd_per_hour: 4.5, placebo: b.rule.placebo, entries: b.rule.entries, effective_bets: b.rule.effectiveBets, status: b.verdict?.status ?? (b.gate ? (b.gate.pass ? 'gate PASS' : 'gate FAIL') : null), hour_tercile: b.rule.hourTer, price_usd: b.rule.priceUsd, funding_usd: b.rule.fundUsd, fee_usd: b.rule.feeUsd, by_side_exit_booked: b.rule.bySide } }));
    for (const [v, d] of Object.entries(b.diagnostics)) rows.push(regRow({ arm: `r4:slow:${name}:diag:${v}`, role: 'neighbour', round: 4, control: flat.trial_id, codeSha: sha, codeEpoch: epoch, ref, at, verdict: d.notRun ? `not run: ${d.notRun}` : `diagnostic: $${d.usd}`, raw: { kind: 'r4-slow-diagnostic', hash: ev.hash, block: name, ...d } }));
  }
  // The candidates the diagnosis weighed and never ran (counted: the family's selection).
  if (mode === 'gates') for (const c of ['84-day-sign', 'vote-no-band', 'carry-hurdle-28d', 'regime-gated-r3-top40']) rows.push(regRow({ arm: `r4:considered:${c}`, role: 'neighbour', round: 4, codeSha: sha, codeEpoch: epoch, ref, at, verdict: 'weighed in the round 4 diagnosis, never run' }));
  return rows;
}

// ---------------------------------------------------------------------------------------------------------------
// CLI.

function arg(k: string, d?: string): string | undefined { const i = process.argv.indexOf(`--${k}`); return i >= 0 && process.argv[i + 1] !== undefined && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : d; }

async function loadCoin(a: string, grids: string, hist: string, macroDir: string | undefined, end: number): Promise<CoinData> {
  const g = readGrid(path.join(grids, `${a}.bin`));
  const nMax = Math.max(0, Math.min(g.n, Math.floor((end - g.t0) / MIN)));
  const spot = await spotFromCsv(path.join(hist, `hist-${a}`, 'binance-1m', a, '1m.csv'), g.t0, nMax);
  if (!spot) throw new Error(`${a}: no Binance spot CSV under ${hist}/hist-${a}`);
  const ter = rvTerciles(g.t0, nMax, (i) => spot.has[i] === 1, (i) => spot.close[i], 0, nMax);
  let macro: Int8Array | undefined;
  const mf = macroDir ? path.join(macroDir, `${a}.json`) : '';
  if (mf && fs.existsSync(mf)) {
    const m = JSON.parse(fs.readFileSync(mf, 'utf8')) as { t0: number; end: number; states: number[] };
    if (m.t0 === g.t0 && m.end >= end) macro = Int8Array.from(m.states);
  }
  return { g, spot, ter, macro };
}

async function main(): Promise<void> {
  const mode = process.argv[2];
  const hash = ruleHash(), sha = process.env.GITHUB_SHA ?? 'local', run = process.env.GITHUB_RUN_ID ?? 'local';
  const assets = (arg('assets') ?? SLOW.assets.join(',')).split(',').filter(Boolean);
  if (assets.includes('DOGE')) throw new Error('DOGE is excluded (Steven, Nov 5)');
  if (mode === 'hash') { console.log(hash); return; }
  if (mode === 'macro') {
    // The bot's macro_trend confluence state at every day boundary (the analyzer walk: research/perpTaModules.ts).
    const { modulePrims } = await import('./perpTaModules');
    const { stateAt } = await import('./perpTaSweep');
    const g = readGrid(arg('data')!), end = arg('end') === 'lockbox' ? SLOW.lockbox : SLOW.seal;
    const nMax = Math.max(0, Math.min(g.n, Math.floor((end - g.t0) / MIN)));
    const mod = modulePrims(g, nMax, { history: arg('history'), forecasts: arg('forecasts'), cacheDir: arg('module-cache'), discoveryEnd: SLOW.validFrom, log: (m) => console.log(`[perp-ta-slow] ${m}`) });
    const p = mod.prims.find((x) => x.id === 'conf:macro_trend');
    const nDays = Math.floor(nMax / MPD), states = new Array(nDays + 1).fill(0);
    if (p) for (let k = 1; k <= nDays; k++) states[k] = stateAt(p, k * MPD - 1);
    fs.mkdirSync(path.dirname(arg('out')!), { recursive: true });
    fs.writeFileSync(arg('out')!, JSON.stringify({ asset: g.asset, t0: g.t0, end, found: !!p, states }));
    console.log(`[perp-ta-slow] ${g.asset}: macro_trend ${p ? `states for ${nDays} days (${states.filter((s) => s > 0).length} bullish, ${states.filter((s) => s < 0).length} bearish)` : 'never scored'}`);
    return;
  }
  if (mode !== 'gates' && mode !== 'sealed') throw new Error('usage: perpTaSlow.ts gates|sealed|macro|hash ...');
  // The coins are part of the rule (one cell, four coins): a subset is refused, except gates with --any-coins (tests only).
  if (assets.join(',') !== SLOW.assets.join(',') && !(mode === 'gates' && process.argv.includes('--any-coins'))) throw new Error(`${mode}: the rule trades ${SLOW.assets.join(',')}, not ${assets.join(',')}: refused`);
  const outDir = arg('out', 'out/slow')!;
  fs.mkdirSync(outDir, { recursive: true });
  if (mode === 'sealed') {
    const gf = arg('gates');
    if (!gf || !fs.existsSync(gf)) throw new Error('sealed: --gates <gates.json> is required');
    const gj = JSON.parse(fs.readFileSync(gf, 'utf8')) as { hash: string; pass: boolean; assets: string[] };
    if (gj.hash !== hash) throw new Error(`sealed: the gates ran rule ${gj.hash}, this code is ${hash}: refused`);
    if (!gj.pass) throw new Error('sealed: the gates did not pass: the sealed block stays closed (pre-registered)');
    if (gj.assets.join(',') !== SLOW.assets.join(',')) throw new Error('sealed: the gates ran other coins: refused');
  }
  const end = mode === 'gates' ? SLOW.seal : SLOW.lockbox;
  const coins: CoinData[] = [];
  for (const a of assets) { coins.push(await loadCoin(a, arg('grids', 'data/perp-ta')!, arg('history', 'data')!, arg('macro'), end)); console.log(`[perp-ta-slow] ${a}: loaded`); }
  const t0 = Math.min(...coins.map((c) => c.g.t0));
  const blocks: Block[] = mode === 'gates'
    ? [{ name: 'discovery', from: t0, to: SLOW.validFrom }, { name: 'validation', from: SLOW.validFrom, to: SLOW.seal }]
    : [{ name: 'sealed', from: SLOW.seal, to: SLOW.lockbox }];
  const ev = evaluate(coins, end, blocks, hash);
  const md = markdown(ev, mode);
  const pass = mode === 'gates' ? Object.values(ev.blocks).every((b) => b.gate?.pass) : !!ev.blocks.sealed?.verdict?.pass;
  fs.writeFileSync(path.join(outDir, `${mode}.json`), JSON.stringify({ mode, pass, assets, at: new Date().toISOString(), sha, run, ...ev }, null, 1));
  fs.writeFileSync(path.join(outDir, `${mode}.md`), md + '\n');
  fs.writeFileSync(path.join(outDir, `registry-${mode}.jsonl`), registryRows(ev, mode, sha, run).map((r) => JSON.stringify(r)).join('\n') + '\n');
  console.log(md);
  console.log(`[perp-ta-slow] ${mode}: ${mode === 'sealed' ? ev.blocks.sealed?.verdict?.status ?? 'FAIL' : pass ? 'PASS' : 'FAIL'} (rule hash ${hash})`);
}

if (process.argv[1] && /perpTaSlow\.ts$/.test(process.argv[1])) main().catch((e) => { console.error(e); process.exitCode = 1; });
