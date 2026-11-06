// Oracle setups, perpetual builder (python/oracle/SPEC.md 2a; prereg python/oracle/prereg/OR-H1.md "Decision times,
// entries, labels, exits: Perpetual", "Features", "Mining: matched base rate"). Reads one coin's perp TA grid
// (research/perpTaSweep.ts, schema perpta1) and writes two part directories in the "oracle-part-1" format (SPEC.md 1):
//
//   <out>/perp-<A>/   one row per decision at every 5-minute close (end of minute i = 5k + 4): t.npy = the decision
//                     instant t0 + (i + 1) min; taker entry at the perp open of minute i + 1; sides L / S, horizons 15 / 60.
//                     Labels from perpTaSweep outcomes() with unit = 1e-4 (bps) and {sl: 9999, tp: TP(size), max: h},
//                     TP(size) = 1e4 * 5 / size + taker + half spread + maker + 2 (a resting maker take-profit that nets
//                     +$5 after a 2 bps funding buffer, filled when the perp trades 1 bp through it; else a taker exit at
//                     the close of minute i + h). hit = the take-profit filled; trade $ = net bps / 1e4 * size;
//                     best = the most favourable bar extreme in minutes i+1..i+h as a limit fill (high / (1 + 1 bp),
//                     low x (1 + 1 bp)) less taker in and maker out (no funding); tradeLat = the same trade decided one
//                     minute later; tradeCost = taker and maker +5 bps each (TP re-derived from those costs).
//   <out>/spot-<A>/   every minute in [spot-from, spot-to): t_end.npy (end of the minute), the same X columns, the spot
//                     close, RV60 and its tercile, for the Price Prediction builder (python/oracle/pp.py) to join on.
//
// Features (X.npy int8, meta.features order): every buildPrims primitive (all of them: 113 classic + 4 perp = 117; the
// SPEC's "121" miscounts) and every modulePrims reading except the leaky forecasts (ids starting tanet / lib_ / xg_;
// forecasts are never passed) and analyzer readings that never fire before DEV_END (see keepModulePrim) as 'state' features
// = stateAt(p, i) (-1 / 0 / +1 of the last bar closed by the end of minute i), then 'bucket' features: character class and
// Hilbert trend mode (modulePrims hourly arrays, last CLOSED hour), UTC hour bucket (6 x 4 h), weekend, RV60 tercile and
// the signed z60 trend bucket (regime v1, research/oracle/regime.ts, label at the decision instant). modulePrims runs
// with discoveryEnd = DEV_END (the ta_net threshold sees only bars before 2026-08-01).
// Strata (prereg perp): hour bucket x RV tercile (0..17), -1 when the tercile is NA. group = UTC day index of t.
//
// Nothing at or after 2026-11-05T00:00Z is read: the grid is read only up to that minute (readGridCapped), the other coins'
// hourly CSVs are copied up to it, the spot CSV is parsed up to it. The one discovery row per horizon whose window ends
// exactly at DEV_END gets tradeLat NaN (its latency window would read the first HO-1 minute); rows whose primary window
// straddles DEV_END are written but belong to no split (python/oracle/common.py split_of).
// Logs carry aggregates of rows before DEV_END only. NEVER DOGE.
//
//   NODE_OPTIONS=--max-old-space-size=12000 node --import tsx research/oracle/oracleExport.ts --grid data/grids/BTC.bin \
//     --history <dir with binance-1h/<X>/1h.csv [and binance-1m/<A>/1m.csv]> --cache-dir <modcache> --out parts \
//     [--spot-from 2026-04-12] [--spot-to 2026-11-05] [--max-minutes N] [--modules true|false] [--code-sha <sha>]

import fs from 'fs';
import os from 'os';
import path from 'path';
import readline from 'readline';
import { execSync } from 'child_process';
import { COLS, buildPrims, outcomes, stateAt, KALSHI_COSTS, type Costs, type Grid, type Policy, type Prim } from '../perpTaSweep';
import { modulePrims, MODULE_CONDS, MODULES_VERSION, NONE, type ModuleOut } from '../perpTaModules';
import { taEngine } from '../../bot/ta/talib';
import { rv60, tercilesFromRv, z60, trendBucket, TREND_LEVELS, spotFromCsv } from './regime';
import { NpyWriter, writeNpy, typed, type Typed } from './npy';

// ---------------------------------------------------------------------------------------------------------------
// Constants (python/oracle/common.py mirror).

export const MIN = 60_000;
export const DAY = 86_400_000;
const H = 3_600_000;
export const SCHEMA = 'oracle-part-1';
export const TARGET_USD = 5.0;
export const ASSETS = ['BTC', 'ETH', 'SOL', 'XRP']; // never DOGE
export const DEV_END = Date.UTC(2026, 7, 1);
export const HOLD_FROM = Date.UTC(2026, 7, 1);
export const HOLD_TO = Date.UTC(2026, 10, 5); // exclusive: Nov 4 is the last HO-1 day; nothing at or after it is read
export const LOCKBOX_FROM = Date.UTC(2026, 10, 6, 5);
/** Half-open [from, to) by decision time; a row also needs its horizon inside the split (common.py split_of). */
export const SPLITS = {
  perp: { A: [Date.UTC(2020, 0, 1), Date.UTC(2025, 0, 1)], B: [Date.UTC(2025, 0, 1), DEV_END] },
  pp15: { A: [Date.UTC(2026, 3, 18), Date.UTC(2026, 5, 15)], B: [Date.UTC(2026, 5, 15), DEV_END] },
  pp60: { A: [Date.UTC(2026, 3, 18), Date.UTC(2026, 5, 15)], B: [Date.UTC(2026, 5, 15), DEV_END] },
  tennis: { A: [Date.UTC(2026, 3, 27, 5), Date.UTC(2026, 5, 22)], B: [Date.UTC(2026, 5, 22), Date.UTC(2026, 6, 31)] },
} as const;
export const FOLD_EDGES = [[7, 1], [7, 17], [8, 2], [8, 18], [9, 4], [9, 20], [10, 5]].map(([m, d]) => Date.UTC(2026, m, d));
export const SIZE_USD = { perp: 300, pp15: 20, pp60: 20, tennis: 10 } as const;
export const SIZE2_USD = { perp: 1000, pp15: 10, pp60: 10, tennis: 20 } as const;
/** This builder's sizes (perp): $300 notional (+$5 = 166.7 bps net), $1,000 sensitivity. */
export const SIZE = SIZE_USD.perp, SIZE2 = SIZE2_USD.perp;
export const SIDES = ['L', 'S'] as const;
export const HORIZONS = [15, 60] as const;
export const STEP_MIN = 5;
/** Per-coin half spread (bps) and Kalshi funding premium over the model (bps per 8 h): the perp thread's fidelity medians. */
export const HALF_SPREAD_BPS: Record<string, number> = { BTC: 0.19, ETH: 0.22, SOL: 1.23, XRP: 1.94 };
export const FUND_OFFSET_BPS: Record<string, number> = { BTC: 1.66, ETH: 1.19, SOL: 0.14, XRP: 1.57 };
export const COST_STRESS_BPS = 5;
export const FUND_BUFFER_BPS = 2;
/** Leaky forecast readings (prereg "Excluded as leaky"); modulePrims never gets forecasts, this drops them regardless. */
export const EXCLUDED_PREFIXES = ['tanet', 'lib_', 'xg_'];
export const SPOT_FROM = Date.UTC(2026, 3, 12), SPOT_TO = HOLD_TO;

export function assertAsset(a: string): void {
  if (/DOGE/i.test(a)) throw new Error('DOGE refused (never DOGE)');
  if (!ASSETS.includes(a)) throw new Error(`${a}: not one of ${ASSETS.join(', ')} (no per-coin costs)`);
}

export const costsFor = (asset: string): Costs => ({ ...KALSHI_COSTS, halfSpreadBps: HALF_SPREAD_BPS[asset], fundOffsetBps: FUND_OFFSET_BPS[asset], ttBps: 1 });
export const stressed = (c: Costs): Costs => ({ ...c, takerBps: c.takerBps + COST_STRESS_BPS, makerBps: c.makerBps + COST_STRESS_BPS });
/** The take-profit (bps over the entry) that nets +$5 at `size` after a taker entry, a maker exit and the funding buffer. */
export const tpBps = (size: number, c: Costs): number => (1e4 * TARGET_USD) / size + c.takerBps + c.halfSpreadBps + c.makerBps + FUND_BUFFER_BPS;

const iso = (t: number) => new Date(t).toISOString().slice(0, 16) + 'Z';
const fin = Number.isFinite;

// ---------------------------------------------------------------------------------------------------------------
// The grid, read only up to a cut-off.

/** readGrid (perpTaSweep.ts) loads the whole file; this reads the same perpta1 layout but only the minutes that end by
 *  `toMs` (and at most maxMinutes), so no byte of a later minute (the lockbox) is ever read. */
export function readGridCapped(file: string, toMs = HOLD_TO, maxMinutes = Infinity): Grid {
  const fd = fs.openSync(file, 'r');
  try {
    const head = Buffer.alloc(65536);
    const got = fs.readSync(fd, head, 0, head.length, 0);
    const nl = head.subarray(0, got).indexOf(10);
    if (nl < 0) throw new Error(`${file}: no header line`);
    const h = JSON.parse(head.subarray(0, nl).toString('utf8')) as { schema: string; asset: string; t0: number; n: number; cols: string[] };
    if (h.schema !== 'perpta1') throw new Error(`${file}: not a perp-ta grid`);
    assertAsset(h.asset);
    const cols = [...COLS, 'fundRaw'];
    if (JSON.stringify(h.cols) !== JSON.stringify(cols)) throw new Error(`${file}: columns ${h.cols} != ${cols}`);
    const n = Math.max(0, Math.min(h.n, Math.floor((toMs - h.t0) / MIN), maxMinutes));
    const take = (k: number) => {
      const a = new Float32Array(n), b = Buffer.from(a.buffer);
      let off = 0;
      while (off < b.length) { const r = fs.readSync(fd, b, off, b.length - off, nl + 1 + k * 4 * h.n + off); if (r <= 0) throw new Error(`${file}: truncated`); off += r; }
      return a;
    };
    const c = Object.fromEntries(COLS.map((k, j) => [k, take(j)])) as Grid['c'];
    return { asset: h.asset, t0: h.t0, n, c, fundRaw: take(COLS.length) };
  } finally { fs.closeSync(fd); }
}

/** Copies <history>/binance-1h/<X>/1h.csv for the four coins into `dst`, keeping only bars closed by `toMs` (the CSVs are
 *  time-sorted; parsing stops at the first later bar). modulePrims then never sees a later hour. Returns the coins copied. */
export async function trimHourly(history: string, dst: string, toMs = HOLD_TO): Promise<string[]> {
  const done: string[] = [];
  for (const a of ASSETS) {
    const src = path.join(history, 'binance-1h', a, '1h.csv');
    if (!fs.existsSync(src)) continue;
    const out: string[] = [];
    const input = fs.createReadStream(src), rl = readline.createInterface({ input, crlfDelay: Infinity });
    for await (const line of rl) {
      if (!line) continue;
      if (line.startsWith('ts')) { out.push(line); continue; }
      const ts = Number(line.slice(0, line.indexOf(',')));
      if (!fin(ts)) continue;
      if (ts + H > toMs) break;
      out.push(line);
    }
    rl.close(); input.destroy();
    fs.mkdirSync(path.join(dst, 'binance-1h', a), { recursive: true });
    fs.writeFileSync(path.join(dst, 'binance-1h', a, '1h.csv'), out.join('\n') + '\n');
    done.push(a);
  }
  return done;
}

// ---------------------------------------------------------------------------------------------------------------
// Labels.

export interface PerpLabels {
  /** Decision minute i of each row (sorted). */
  rows: Int32Array;
  /** Per-row arrays keyed as in SPEC.md 1 (ok_L15, hit_L15, trade_L15, best_L15, hold_L15, hit2_L15, trade2_L15,
   *  tradeLat_L15, tradeCost_L15, bestbps_L15, and the same for S and 60). */
  arrays: Record<string, Typed>;
  tp: Record<string, number>;
}

/** Whether outcomes()' take-profit filled in minute j for a trade decided at i (its exact comparison, recomputed: a
 *  take-profit in the last minute of the hold has the time stop's hold). */
function tpFilledAt(g: Grid, i: number, j: number, d: number, tp: number, A: number, tt: number): boolean {
  const P0 = g.c.po[i + 1], tpPx = P0 * (1 + d * tp * A);
  return d > 0 ? g.c.ph[j] >= tpPx * (1 + tt) : g.c.pl[j] <= tpPx * (1 - tt);
}

/** Every label of every 5-minute decision, then the rows (decisions tradable on at least one side / horizon). */
export function perpLabels(g: Grid, costs: Costs, log: (m: string) => void = () => undefined): PerpLabels {
  const nMax = g.n;
  const nDec = nMax >= STEP_MIN + 1 ? Math.floor((nMax - STEP_MIN - 1) / STEP_MIN) + 1 : 0; // i = 5k + 4 with i + 1 < nMax
  const dec = (k: number) => STEP_MIN * k + STEP_MIN - 1;
  const unit = new Float32Array(nMax).fill(1e-4);
  const tt = (costs.ttBps ?? 1) / 1e4;
  const per: Record<string, Float32Array | Uint8Array | Uint16Array> = {};
  const tp: Record<string, number> = {};
  const variants: Array<{ tag: '' | '2' | 'Cost'; size: number; c: Costs }> = [
    { tag: '', size: SIZE, c: costs }, { tag: '2', size: SIZE2, c: costs }, { tag: 'Cost', size: SIZE, c: stressed(costs) },
  ];
  let anomalies = 0;
  for (const v of variants) {
    const tpb = tpBps(v.size, v.c);
    tp[v.tag === '' ? `primary_${v.size}` : v.tag === '2' ? `size2_${v.size}` : `cost_stress_${v.size}`] = tpb;
    const pols: Policy[] = HORIZONS.map((h) => ({ id: `TP${h}`, sl: 9999, tp: tpb, max: h }));
    const t = Date.now();
    const o = outcomes(g, nMax, unit, v.c, pols);
    HORIZONS.forEach((h, p) => SIDES.forEach((s, q) => {
      const d = q === 0 ? 1 : -1, net = o.net[2 * p + q], ex = o.exit[2 * p + q], hd = o.hold[2 * p + q];
      const key = `${s}${h}`;
      const usd = new Float32Array(nDec);
      for (let k = 0; k < nDec; k++) usd[k] = (net[dec(k)] / 1e4) * v.size;
      if (v.tag === 'Cost') { per[`tradeCost_${key}`] = usd; return; }
      per[`trade${v.tag}_${key}`] = usd;
      const hit = new Uint8Array(nDec);
      for (let k = 0; k < nDec; k++) {
        const i = dec(k);
        if (!(net[i] === net[i])) continue;
        hit[k] = tpFilledAt(g, i, ex[i], d, tpb, unit[i], tt) ? 1 : 0;
        if (!hit[k] && hd[i] !== h) anomalies++; // an exit before the time stop that is not the take-profit (the 9999-bps stop)
      }
      per[`hit${v.tag}_${key}`] = hit;
      if (v.tag !== '') return;
      const hold = new Uint16Array(nDec), lat = new Float32Array(nDec);
      for (let k = 0; k < nDec; k++) {
        const i = dec(k), tDec = g.t0 + (i + 1) * MIN;
        hold[k] = hd[i];
        // Entry one minute later (decided at the end of minute i + 1). The row whose own window ends exactly at DEV_END
        // (a discovery row) would read the first HO-1 minute: NaN.
        lat[k] = i + 1 < nMax && !(tDec + h * MIN <= DEV_END && tDec + (h + 1) * MIN > DEV_END) ? (net[i + 1] / 1e4) * v.size : NaN;
      }
      per[`hold_${key}`] = hold; per[`tradeLat_${key}`] = lat;
    }));
    log(`outcomes ${v.tag || 'primary'} ($${v.size}, TP ${tpb.toFixed(2)} bps): ${((Date.now() - t) / 1000).toFixed(1)} s`);
  }
  if (anomalies) log(`WARNING: ${anomalies} exits before the time stop that are not take-profits (the 9999 bps stop)`);
  // Hindsight best: the most favourable bar extreme in the hold window as a limit fill (1 bp through), taker in, maker out.
  const { po, ph, pl } = g.c, inCost = costs.takerBps + costs.halfSpreadBps, outCost = costs.makerBps;
  for (const s of SIDES) for (const h of HORIZONS) { per[`bestbps_${s}${h}`] = new Float32Array(nDec).fill(NaN); per[`best_${s}${h}`] = new Float32Array(nDec).fill(NaN); }
  for (let k = 0; k < nDec; k++) {
    const i = dec(k), P0 = po[i + 1];
    let mx = -Infinity, mn = Infinity, j = i + 1;
    for (const h of HORIZONS) {
      for (; j <= i + h && j < nMax; j++) { if (ph[j] > mx) mx = ph[j]; if (pl[j] < mn) mn = pl[j]; }
      const okL = (per[`trade_L${h}`] as Float32Array)[k] === (per[`trade_L${h}`] as Float32Array)[k];
      const okS = (per[`trade_S${h}`] as Float32Array)[k] === (per[`trade_S${h}`] as Float32Array)[k];
      if (okL) { const b = (mx / (1 + tt) / P0 - 1) * 1e4 - inCost - outCost; (per[`bestbps_L${h}`] as Float32Array)[k] = b; (per[`best_L${h}`] as Float32Array)[k] = (b / 1e4) * SIZE; }
      if (okS) { const b = -((mn * (1 + tt)) / P0 - 1) * 1e4 - inCost - outCost; (per[`bestbps_S${h}`] as Float32Array)[k] = b; (per[`best_S${h}`] as Float32Array)[k] = (b / 1e4) * SIZE; }
    }
  }
  // Rows: decisions tradable (outcome not NaN: decision, entry and every hold minute valid, inside the data) somewhere.
  const okOf: Record<string, Uint8Array> = {};
  for (const s of SIDES) for (const h of HORIZONS) { const tr = per[`trade_${s}${h}`] as Float32Array, ok = new Uint8Array(nDec); for (let k = 0; k < nDec; k++) ok[k] = tr[k] === tr[k] ? 1 : 0; okOf[`${s}${h}`] = ok; }
  const keep: number[] = [];
  for (let k = 0; k < nDec; k++) if (Object.values(okOf).some((ok) => ok[k])) keep.push(k);
  const rows = Int32Array.from(keep, dec);
  const arrays: Record<string, Typed> = {};
  const pick = <T extends Float32Array | Uint8Array | Uint16Array>(a: T): T => { const C = a.constructor as new (n: number) => T; const out = new C(keep.length); for (let r = 0; r < keep.length; r++) out[r] = a[keep[r]]; return out; };
  for (const s of SIDES) for (const h of HORIZONS) {
    const key = `${s}${h}`, ok = okOf[key];
    arrays[`ok_${key}`] = pick(ok);
    for (const name of ['hit', 'hit2']) { const a = pick(per[`${name}_${key}`] as Uint8Array); arrays[`${name}_${key}`] = a; }
    for (const name of ['trade', 'best', 'trade2', 'tradeLat', 'tradeCost', 'bestbps']) arrays[`${name}_${key}`] = pick(per[`${name}_${key}`] as Float32Array);
    arrays[`hold_${key}`] = pick(per[`hold_${key}`] as Uint16Array);
    // Not ok: every label is NaN / 0 (the hit flags and holds of an untradable row carry nothing).
    const okR = arrays[`ok_${key}`] as Uint8Array;
    for (let r = 0; r < keep.length; r++) if (!okR[r]) {
      (arrays[`hit_${key}`] as Uint8Array)[r] = 0; (arrays[`hit2_${key}`] as Uint8Array)[r] = 0; (arrays[`hold_${key}`] as Uint16Array)[r] = 0;
      for (const name of ['best', 'trade2', 'tradeLat', 'tradeCost', 'bestbps']) (arrays[`${name}_${key}`] as Float32Array)[r] = NaN;
    }
  }
  return { rows, arrays, tp };
}

// ---------------------------------------------------------------------------------------------------------------
// Features.

export interface Feature { name: string; kind: 'state' | 'bucket'; levels: number[]; desc: string; level_names?: string[]; prim?: Prim; at?: (i: number) => number }

export interface Context {
  /** RV60 (NaN = NA) and its tercile and z60 per label index 0..n (index i + 1 = the end of minute i). */
  rv: Float64Array; ter: Int8Array; z: Float64Array;
}

const CHAR_LEVELS = ['char_calm', 'char_trending', 'char_vidio', 'char_vsys'];
const HT_LEVELS = ['ht_cycle', 'ht_trend'];

function primDesc(p: Prim, src: 'buildPrims' | 'modulePrims'): string {
  const tf = `${p.m}m bars`;
  if (src === 'buildPrims') return `buildPrims ${p.fam} on ${tf} (state of the last closed bar)`;
  if (p.id.startsWith('ta:')) return `analyzer rule ${p.id.slice(3)} (bot/ta/knowledge.ts RULES), direction at the last 5m close`;
  if (p.id.startsWith('book:')) return `rule-book rule ${p.id.slice(5)} (bot/ta/knowledge.ts BOOK_RULES, code-defined), direction at the last 5m close`;
  if (p.id.startsWith('conf:')) return `confluence ${p.id.slice(5)}: sign of its score at the last 5m close`;
  if (p.id === 'ta_net') return 'analyzer net vote beyond its discovery (before 2026-08-01) 80th percentile of |net|';
  if (p.id.startsWith('conv:')) return `directional conviction ${p.id.slice(5)} (bot/strategy/taConviction.ts) at the last 5m close`;
  if (p.id.startsWith('cdl_')) return `TA-Lib candlestick ${p.fam} on ${tf}`;
  if (p.id.startsWith('tl_')) return `TA-Lib indicator state ${p.fam} on ${tf}`;
  return `modulePrims ${p.id} on ${tf}`;
}

/** The analyzer walk creates a reading (ta: / book: / conf: / conv:) only when it first fires, so which of them exist
 *  depends on the data. Keeping those that fire in a bar closed before DEV_END makes the column list independent of
 *  HO-1 data (a reading that never fires there has no discovery support anyway). Without bars before DEV_END, all. */
export const ANALYZER_PREFIXES = ['ta:', 'book:', 'conf:', 'conv:'];
export function firesBefore(p: Prim, t0: number, until = DEV_END): boolean {
  if (until <= t0) return true;
  const kMax = Math.min(p.s.length, Math.floor((until - t0) / (p.m * MIN))); // bars closed by `until`
  for (let k = 0; k < kMax; k++) if (p.s[k] !== 0) return true;
  return false;
}

/** Module readings that go into X: no leaky forecast, no analyzer reading that never fires before DEV_END. */
export function keepModulePrim(p: Prim, t0: number): boolean {
  if (EXCLUDED_PREFIXES.some((x) => p.id.startsWith(x))) return false;
  return !ANALYZER_PREFIXES.some((x) => p.id.startsWith(x)) || firesBefore(p, t0);
}

/** The feature list: buildPrims, then modulePrims without the leaky forecasts, then the context buckets. */
export function featureList(g: Grid, prims: Prim[], mod: ModuleOut | undefined, cx: Context): Feature[] {
  const out: Feature[] = [];
  const seen = new Set<string>();
  const add = (f: Feature) => { if (seen.has(f.name)) throw new Error(`duplicate feature ${f.name}`); seen.add(f.name); out.push(f); };
  for (const p of prims) add({ name: p.id, kind: 'state', levels: [-1, 0, 1], desc: primDesc(p, 'buildPrims'), prim: p });
  for (const p of mod?.prims ?? []) if (keepModulePrim(p, g.t0)) add({ name: p.id, kind: 'state', levels: [-1, 0, 1], desc: primDesc(p, 'modulePrims'), prim: p });
  const t0 = g.t0;
  const hourK = (i: number) => Math.floor((i + 1) / 60) - 1; // the last hourly bar closed by the end of minute i
  if (mod) {
    const { char, ht } = mod.hourly;
    const lv = (codes: Uint8Array, names: string[]) => (i: number) => { const k = hourK(i); const c = k >= 0 && k < codes.length ? codes[k] : NONE; return c === NONE ? -1 : names.indexOf(MODULE_CONDS[c]); };
    add({ name: 'ctx:char', kind: 'bucket', levels: [0, 1, 2, 3], level_names: CHAR_LEVELS, desc: 'character class (bot/ta/character.ts) of the last closed hour', at: lv(char, CHAR_LEVELS) });
    add({ name: 'ctx:ht_mode', kind: 'bucket', levels: [0, 1], level_names: HT_LEVELS, desc: 'TA-Lib HT_TRENDMODE on 1h bars, last closed hour: 0 cycle, 1 trend', at: lv(ht, HT_LEVELS) });
  }
  const tEnd = (i: number) => t0 + (i + 1) * MIN;
  add({ name: 'ctx:hour4', kind: 'bucket', levels: [0, 1, 2, 3, 4, 5], level_names: ['00-04', '04-08', '08-12', '12-16', '16-20', '20-24'], desc: 'UTC hour of the decision instant / 4', at: (i) => Math.floor((((tEnd(i) % DAY) + DAY) % DAY) / (4 * H)) });
  add({ name: 'ctx:weekend', kind: 'bucket', levels: [0, 1], level_names: ['weekday', 'weekend'], desc: 'UTC Saturday or Sunday at the decision instant', at: (i) => { const wd = (Math.floor(tEnd(i) / DAY) + 4) % 7; return wd === 0 || wd === 6 ? 1 : 0; } });
  add({ name: 'ctx:rv', kind: 'bucket', levels: [0, 1, 2], level_names: ['LOW', 'MID', 'HIGH'], desc: 'regime v1 RV60 tercile at the decision instant (causal)', at: (i) => cx.ter[i + 1] });
  add({ name: 'ctx:trend60', kind: 'bucket', levels: [0, 1, 2, 3, 4], level_names: TREND_LEVELS, desc: 'regime v1 z60 trend bucket with sign (FLAT |z|<1, TREND 1-2, STRONG >2)', at: (i) => trendBucket(cx.z[i + 1]) });
  return out;
}

/** Streams X (rows x features, int8, C order) to disk in row blocks: the feature row of minute i is read at the end of i. */
export function writeX(file: string, mins: Int32Array, feats: Feature[]): void {
  const F = feats.length, n = mins.length;
  const B = Math.max(1, Math.min(Math.max(1, n), Math.floor((32 << 20) / Math.max(1, F))));
  const w = new NpyWriter(file, 'int8', [n, F]);
  const buf = new Int8Array(B * F);
  for (let r0 = 0; r0 < n; r0 += B) {
    const nb = Math.min(n, r0 + B) - r0;
    for (let f = 0; f < F; f++) {
      const ft = feats[f], p = ft.prim, at = ft.at;
      if (p) for (let r = 0; r < nb; r++) buf[r * F + f] = stateAt(p, mins[r0 + r]);
      else for (let r = 0; r < nb; r++) buf[r * F + f] = at!(mins[r0 + r]);
    }
    w.write(nb === B ? buf : buf.subarray(0, nb * F));
  }
  w.close();
}

// ---------------------------------------------------------------------------------------------------------------
// The export.

export interface ExportOpts {
  grid: string;
  history?: string;
  cacheDir?: string;
  out: string;
  spotFrom?: number;
  spotTo?: number;
  maxMinutes?: number;
  modules?: boolean;
  codeSha?: string;
  log?: (m: string) => void;
}

function codeSha(o: ExportOpts): string {
  if (o.codeSha) return o.codeSha;
  if (process.env.GITHUB_SHA) return process.env.GITHUB_SHA;
  try { return execSync('git rev-parse HEAD', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim(); } catch { return 'unknown'; }
}

const featMeta = (fs_: Feature[]) => fs_.map((f) => ({ name: f.name, kind: f.kind, levels: f.levels, desc: f.desc, ...(f.level_names ? { level_names: f.level_names } : {}) }));

/** Writes into <dir>.tmp-<pid> and swaps it in at the end (meta.json last), so a part directory is whole or absent. */
function partWriter(dir: string) {
  const tmp = `${dir}.tmp-${process.pid}`;
  fs.rmSync(tmp, { recursive: true, force: true });
  fs.mkdirSync(tmp, { recursive: true });
  return {
    tmp,
    npy: (name: string, a: Typed) => writeNpy(path.join(tmp, `${name}.npy`), a),
    finish: (meta: Record<string, unknown>) => {
      fs.writeFileSync(path.join(tmp, 'meta.json'), JSON.stringify(meta, null, 1));
      fs.rmSync(dir, { recursive: true, force: true });
      fs.renameSync(tmp, dir);
    },
  };
}

export async function exportAsset(o: ExportOpts): Promise<{ perp: string; spot: string; n: number; nSpot: number; features: string[] }> {
  const log = o.log ?? ((m: string) => console.log(`[oracle-export] ${m}`));
  if (/DOGE/i.test(path.basename(o.grid))) throw new Error('DOGE refused (never DOGE)');
  const g = readGridCapped(o.grid, HOLD_TO, o.maxMinutes ?? Infinity);
  const A = g.asset, nMax = g.n;
  if (nMax < 2 * 1440) throw new Error(`${A}: only ${nMax} minutes before ${iso(HOLD_TO)}`);
  log(`${A}: grid ${iso(g.t0)} .. ${iso(g.t0 + nMax * MIN)} (${nMax} minutes, capped at ${iso(HOLD_TO)})`);
  const costs = costsFor(A);
  const sha = codeSha(o);
  const useModules = o.modules !== false;
  const notes: string[] = [];

  // Regime v1 context: the coin's Binance 1m CSV when the history has it (regime.py's own input), else the grid's spot bars.
  const csv = o.history ? path.join(o.history, 'binance-1m', A, '1m.csv') : undefined;
  const sp = csv ? await spotFromCsv(csv, g.t0, nMax) : undefined;
  const bar = sp ? (i: number) => i < nMax && sp.has[i] === 1 : (i: number) => i < nMax && (g.c.valid[i] === 1 || g.c.sv[i] > 0);
  const close = sp ? (i: number) => sp.close[i] : (i: number) => g.c.sc[i];
  const rv = rv60(nMax + 1, bar, close);
  const cx: Context = { rv, ter: tercilesFromRv(g.t0, rv), z: z60(rv, bar, close) };
  notes.push(`regime v1 from ${sp ? 'the Binance 1m CSV (float64 closes)' : 'the grid spot bars (valid or volume > 0; Float32 closes)'}`);
  log(notes[notes.length - 1]);

  // Labels first (they fix the rows).
  const lab = perpLabels(g, costs, log);
  const n = lab.rows.length;

  // Features.
  let t = Date.now();
  const prims = buildPrims(g, nMax, log);
  log(`buildPrims: ${prims.length} primitives in ${((Date.now() - t) / 1000).toFixed(1)} s`);
  let mod: ModuleOut | undefined;
  if (useModules) {
    if (taEngine() !== 'talib') throw new Error(`TA-Lib did not load (engine ${taEngine()}): the TA-Lib readings would be silent zeros`);
    const tmpHist = fs.mkdtempSync(path.join(os.tmpdir(), 'oracle-h1-'));
    try {
      const copied = o.history ? await trimHourly(o.history, tmpHist) : [];
      notes.push(`modulePrims (${MODULES_VERSION}, TA engine ${taEngine()}, discoveryEnd ${iso(DEV_END)}, no forecasts): other coins' hourly bars ${copied.join(', ') || 'none'} (closed by ${iso(HOLD_TO)})`);
      t = Date.now();
      // Distribution notes over the whole grid (hours by character) are not logged: they include HO-1 hours.
      const quiet = (m: string) => { if (!m.startsWith('hours by character')) log(m); };
      mod = modulePrims(g, nMax, { history: tmpHist, cacheDir: o.cacheDir, discoveryEnd: DEV_END, others: ASSETS, log: quiet });
      log(`modulePrims: ${mod.prims.length} readings in ${((Date.now() - t) / 1000).toFixed(1)} s`);
      notes.push(...mod.notes.filter((x) => !x.startsWith('hours by character')));
    } finally { fs.rmSync(tmpHist, { recursive: true, force: true }); }
  } else notes.push('modules off (--modules false): no analyzer / TA-Lib readings, no character / HT buckets');
  const feats = featureList(g, prims, mod, cx);
  const dropped = (mod?.prims ?? []).filter((p) => EXCLUDED_PREFIXES.some((x) => p.id.startsWith(x))).map((p) => p.id);
  if (dropped.length) notes.push(`dropped leaky readings: ${dropped.join(', ')}`);
  const silent = (mod?.prims ?? []).filter((p) => !EXCLUDED_PREFIXES.some((x) => p.id.startsWith(x)) && !keepModulePrim(p, g.t0)).map((p) => p.id);
  if (silent.length) notes.push(`analyzer readings that never fire before ${iso(DEV_END)} left out (column list independent of HO-1): ${silent.join(', ')}`);
  log(`${feats.length} features (${feats.filter((f) => f.kind === 'state').length} state, ${feats.filter((f) => f.kind === 'bucket').length} bucket)`);

  // perp-<A>.
  const perpDir = path.join(o.out, `perp-${A}`);
  const pw = partWriter(perpDir);
  const tDec = new Float64Array(n), group = new Float64Array(n), hour = new Int8Array(n), rvT = new Int8Array(n);
  for (let r = 0; r < n; r++) {
    const i = lab.rows[r], tt = g.t0 + (i + 1) * MIN;
    tDec[r] = tt; group[r] = Math.floor(tt / DAY); hour[r] = Math.floor((((tt % DAY) + DAY) % DAY) / H); rvT[r] = cx.ter[i + 1];
  }
  pw.npy('t', typed('int64', tDec)); pw.npy('group', typed('int64', group)); pw.npy('asset', new Int8Array(n));
  pw.npy('rv', rvT); pw.npy('hour', hour);
  for (const s of SIDES) {
    const st = new Int16Array(n);
    const ok15 = lab.arrays[`ok_${s}15`] as Uint8Array, ok60 = lab.arrays[`ok_${s}60`] as Uint8Array;
    for (let r = 0; r < n; r++) st[r] = rvT[r] >= 0 && (ok15[r] || ok60[r]) ? Math.floor(hour[r] / 4) * 3 + rvT[r] : -1;
    pw.npy(`stratum_${s}`, st);
  }
  for (const [k, a] of Object.entries(lab.arrays)) pw.npy(k, a);
  t = Date.now();
  writeX(path.join(pw.tmp, 'X.npy'), lab.rows, feats);
  log(`perp-${A}: X ${n} x ${feats.length} in ${((Date.now() - t) / 1000).toFixed(1)} s`);
  // Aggregates of rows before DEV_END only.
  const dev = (r: number) => tDec[r] < DEV_END;
  let nDev = 0; for (let r = 0; r < n; r++) if (dev(r)) nDev++;
  const devStats = Object.fromEntries(SIDES.flatMap((s) => HORIZONS.map((h) => {
    const ok = lab.arrays[`ok_${s}${h}`] as Uint8Array, hit = lab.arrays[`hit_${s}${h}`] as Uint8Array;
    let k = 0, hh = 0; for (let r = 0; r < n; r++) if (dev(r) && tDec[r] + h * MIN <= DEV_END && ok[r]) { k++; hh += hit[r]; }
    return [`${s}${h}`, { ok: k, hits: hh }];
  })));
  log(`perp-${A}: ${n} rows (${nDev} before ${iso(DEV_END)}); before DEV_END: ${Object.entries(devStats).map(([k, v]) => `${k} ${v.ok} ok, ${v.hits} hits`).join('; ')}`);
  const meta = {
    schema: SCHEMA, ct: 'perp', scope: A, assets: [A], sides: [...SIDES], horizons: [...HORIZONS], size_usd: SIZE, size2_usd: SIZE2,
    step_min: STEP_MIN, code_sha: sha, n, features: featMeta(feats),
    strata_desc: 'stratum_{s} = hour4 * 3 + RV60 tercile (hour4 = UTC hour of t / 4, 0..5; 18 strata, same both sides); -1 when the tercile is NA or the side is not tradable at any horizon',
    notes: [
      't = end of decision minute i = t0 + (i + 1) min, i = 5k + 4; entry = taker at the perp open of minute i + 1 (+ taker + half spread)',
      `labels: perpTaSweep outcomes(), unit 1e-4, {sl: 9999, tp: TP(size), max: h}; TP(size) = 1e4*5/size + taker + half spread + maker + ${FUND_BUFFER_BPS}; maker TP fills when the perp trades ${costs.ttBps} bp through it; else taker at the close of minute i + h`,
      'hit = the take-profit filled (recomputed with outcomes()\' comparison at the exit minute, so a fill in the last minute counts); hold = exit minute - i',
      'best / bestbps = most favourable bar extreme over minutes i+1..i+h as a limit fill (high / (1 + 1 bp) long, low x (1 + 1 bp) short), less taker + half spread in and maker out, funding ignored',
      'tradeLat = the same trade decided at the end of minute i + 1 (NaN for the one row per horizon whose own window ends at DEV_END: its latency window would read the first HO-1 minute); tradeCost = taker and maker + 5 bps each with TP re-derived from those costs',
      'ok = outcome not NaN (decision, entry and every hold minute valid and inside the data); labels of a row that is not ok are NaN / 0',
      'X: state = stateAt(p, i) of the last bar closed by the end of minute i; bucket -1 = NA; ctx:* read the last closed hour / the regime label at t',
      ...notes,
    ],
    costs, tp_bps: lab.tp, grid: { file: path.basename(o.grid), t0: g.t0, t0_iso: iso(g.t0), n_read: nMax, end_iso: iso(g.t0 + nMax * MIN) },
    dev_end: DEV_END, hold_to: HOLD_TO, ta_engine: useModules ? taEngine() : null, modules_version: useModules ? MODULES_VERSION : null,
  };
  pw.finish(meta);

  // spot-<A>.
  const spotFrom = o.spotFrom ?? SPOT_FROM, spotTo = Math.min(o.spotTo ?? SPOT_TO, HOLD_TO);
  const m0 = Math.max(0, Math.ceil((spotFrom - g.t0) / MIN)), m1 = Math.min(nMax, Math.ceil((spotTo - g.t0) / MIN));
  const nSpot = Math.max(0, m1 - m0);
  const mins = new Int32Array(nSpot);
  for (let r = 0; r < nSpot; r++) mins[r] = m0 + r;
  const spotDir = path.join(o.out, `spot-${A}`);
  const sw = partWriter(spotDir);
  const tEnd = new Float64Array(nSpot), cl = new Float64Array(nSpot), rvF = new Float32Array(nSpot), rvS = new Int8Array(nSpot), val = new Uint8Array(nSpot);
  for (let r = 0; r < nSpot; r++) {
    const m = mins[r];
    tEnd[r] = g.t0 + (m + 1) * MIN;
    cl[r] = sp && sp.has[m] ? sp.close[m] : g.c.sc[m];
    rvF[r] = cx.rv[m + 1]; rvS[r] = cx.ter[m + 1]; val[r] = g.c.valid[m] ? 1 : 0;
  }
  sw.npy('t_end', typed('int64', tEnd)); sw.npy('close', cl); sw.npy('rv60', rvF); sw.npy('rv', rvS); sw.npy('valid', val);
  t = Date.now();
  writeX(path.join(sw.tmp, 'X.npy'), mins, feats);
  log(`spot-${A}: ${nSpot} minutes ${nSpot ? `${iso(tEnd[0] - MIN)} .. ${iso(tEnd[nSpot - 1])}` : ''}, X in ${((Date.now() - t) / 1000).toFixed(1)} s`);
  sw.finish({
    schema: SCHEMA, ct: 'spot', scope: A, assets: [A], step_min: 1, code_sha: sha, n: nSpot, features: featMeta(feats),
    notes: [
      'one row per grid minute m in [spot_from, spot_to): t_end = t0 + (m + 1) min (the end of the minute); X = the perp part\'s features read at the end of minute m',
      'close = spot close of minute m (float64; the Binance 1m CSV when present, else the grid); rv60 = sqrt(sum r^2) over the 60 one-minute log returns ending with bar m (NaN = NA under 50); rv = its regime v1 tercile (-1 NA); valid = grid valid flag (spot and perp bar present)',
      ...notes,
    ],
    spot_from: spotFrom, spot_to: spotTo, grid: { file: path.basename(o.grid), t0: g.t0, n_read: nMax },
  });
  return { perp: perpDir, spot: spotDir, n, nSpot, features: feats.map((f) => f.name) };
}

// ---------------------------------------------------------------------------------------------------------------
// CLI.

function arg(k: string, d?: string): string | undefined { const i = process.argv.indexOf(`--${k}`); return i >= 0 && process.argv[i + 1] !== undefined && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : d; }
/** A UTC day 'YYYY-MM-DD' (or 'YYYY-MM-DDTHH:MM', UTC) as epoch ms. */
const day = (s: string | undefined, d: number) => { if (!s) return d; const t = Date.parse(s.includes('T') ? `${s}:00Z` : `${s}T00:00:00Z`); if (!fin(t)) throw new Error(`bad date ${s}`); return t; };

async function main(): Promise<void> {
  const grid = arg('grid'), out = arg('out');
  if (!grid || !out) { console.log('usage: oracleExport.ts --grid <A.bin> --out <parts> [--history dir] [--cache-dir dir] [--spot-from YYYY-MM-DD] [--spot-to YYYY-MM-DD] [--max-minutes N] [--modules true|false] [--code-sha sha]'); process.exitCode = 1; return; }
  const mm = arg('max-minutes');
  await exportAsset({
    grid, out, history: arg('history'), cacheDir: arg('cache-dir'), spotFrom: day(arg('spot-from'), SPOT_FROM), spotTo: day(arg('spot-to'), SPOT_TO),
    maxMinutes: mm ? Number(mm) : undefined, modules: arg('modules', 'true') !== 'false', codeSha: arg('code-sha'),
  });
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) main().catch((e) => { console.error(e); process.exitCode = 1; });
