// The bot's own TA modules as perp-sweep primitives and conditions (research/perpTaSweep.ts; Steven, Nov 5 2026 13:59 UTC:
// "This needs to utilize the modules in the bot related to TA such as TA Net, TA Lib, the librarian, confluence and so on").
//
//   analyzer   bot/ta/analyzer.ts tfState + evaluate, the bot's own reading, on 5m / 15m / 1h / 4h / 1d spot bars (the
//              live bot's windows: 320 bars, 80 on 4h; closed bars only) at every 5-minute close: every rule of bot/ta/knowledge.ts RULES and BOOK_RULES on
//              each of its timeframes (ta:<rule>@<tf>, book:<rule>@<tf>: the rule's direction), each of the 13 CONFLUENCES
//              (conf:<id>: the sign of its score) and the net vote (ta_net: beyond its discovery 80th percentile). Breadth over
//              the four coins feeds the breadth rule; no other macro input (dominance, risk gauges) exists in the history.
//   TA-Lib     bot/ta/talib.ts tl() over full series on 15m and 1h bars: the 22 key candlestick patterns (cdl_<name>@<m>m),
//              their net (cdl_net: two or more patterns more one way), and the TA-Lib-only indicators the TA network reads
//              (SAR side, CCI back inside +-100, Aroon oscillator +-50, Ultimate oscillator 30 / 70, KAMA side, StochRSI
//              20 / 80, TRIX sign, CMO +-50, the A/D oscillator's sign, linear-regression slope sign)
//   forecasts  the walk-forward (out of sample) hourly forecasts the server keeps (raw/server-history on Drive): TA Net
//              (research/taNetOos.ts: tanet_up1, tanet_up4 beyond the discovery 70th percentile of their distance from the
//              discovery median), the Librarian (research/librarian.ts: lib_net, its net position, beyond the discovery 70th
//              percentile), the cross-asset graph (research/trainCrossGraph.ts: xg_rel4, xg_rel24, and xg_rank in its top or
//              bottom fifth)
//   conditions the bot's character classifier (bot/ta/character.ts characterOf at every hourly close, with the other coins'
//              Binance hourly bars: calm / trending / volatile idiosyncratic / volatile systemic), the strategy the Librarian
//              weights most (trend / revert / breakout / flat), TA Net's volatility forecast above or below its discovery
//              median, and TA-Lib's Hilbert trend mode on 1h (trend / cycle)
//
// Every threshold comes from the discovery period only (before validFrom). The forecasts are walk-forward in their weights
// only: the TA Net tournament's hyperparameters and the input cull the Librarian shares were chosen on the whole server
// history (to 2026), so cells reading them are reported as diagnostic, never as a pass, until they are re-exported from
// history cut before validFrom. The analyzer walk (the slow part, about 1.4 ms
// per bar) is cached per coin and sealed length (--module-cache), the rest is recomputed each run.

import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import { tfState, evaluate, type TfState } from '../bot/ta/analyzer';
import type { Timeframe } from '../bot/ta/knowledge';
import { tl, taEngine, KEY_PATTERNS } from '../bot/ta/talib';
import { characterOf } from '../bot/ta/character';
import { breadthOf } from '../bot/ta/marketContext';
import { readSeries, seriesPath } from '../bot/marketdata/historyStore';
import type { Candle } from '../bot/ta/indicators';
import { aggregate, type Grid, type Prim } from './perpTaSweep';

const MIN = 60_000, H = 3_600_000;
const fin = Number.isFinite;
export const MODULES_VERSION = 'mod2';
export const MODULE_CONDS = ['char_calm', 'char_trending', 'char_vidio', 'char_vsys', 'lib_trend', 'lib_revert', 'lib_breakout', 'lib_flat', 'tanet_vol_hi', 'tanet_vol_lo', 'ht_trend', 'ht_cycle'];
export const NONE = 255;

export interface ModuleOut {
  prims: Prim[];
  /** Per closed hourly bar (index k = bar open t0 + k h), the module condition codes (index into MODULE_CONDS; NONE = none). */
  hourly: { char: Uint8Array; lib: Uint8Array; vol: Uint8Array; ht: Uint8Array };
  notes: string[];
}

const quant = (xs: number[], p: number) => { if (!xs.length) return NaN; const s = [...xs].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };

// ---------------------------------------------------------------------------------------------------------------
// The analyzer walk (rules, rule book, confluences, net vote).

const TFS: Array<[Timeframe, number]> = [['5m', 5], ['15m', 15], ['1h', 60], ['4h', 240], ['1d', 1440]];
/** Bars per timeframe as the live bot holds them (bot/ta/candleStore.ts: 320 per timeframe, 4h built from the 320
 *  hourly bars, so at most 80): rules that need longer look-backs (a 4h SMA200) never fire live, so not here either. */
const W: Record<string, number> = { '5m': 320, '15m': 320, '1h': 320, '4h': 80, '1d': 320 };

interface AnalyzerCache { version: string; asset: string; t0: number; nMax: number; ids: string[]; n5: number; digest: string }

/** What the analyzer walk depends on: the bot's TA code (every bot/ta source), this file, the engine, the windows, the
 *  grid's spot bars up to nMax and the other coins' hourly coverage. */
function walkDigest(g: Grid, nMax: number, others: Candle[][]): string {
  const h = crypto.createHash('sha1');
  const dir = path.join(path.dirname(new URL(import.meta.url).pathname), '..', 'bot', 'ta');
  for (const f of fs.readdirSync(dir).filter((x) => x.endsWith('.ts')).sort()) h.update(f).update(fs.readFileSync(path.join(dir, f)));
  h.update(fs.readFileSync(new URL(import.meta.url).pathname));
  h.update(`${taEngine()}|${JSON.stringify(W)}|${JSON.stringify(TFS)}|${others.map((o) => `${o.length}:${o[0]?.ts}:${o[o.length - 1]?.ts}`).join(',')}`);
  for (const k of ['so', 'sh', 'sl', 'sc', 'sv', 'stb'] as const) { const a = g.c[k]; h.update(Buffer.from(a.buffer, a.byteOffset, Math.min(a.length, nMax) * 4)); }
  return h.digest('hex');
}

function analyzerWalk(g: Grid, nMax: number, others: Candle[][], log: (m: string) => void): { ids: string[]; s: Int8Array[]; net: Float32Array } {
  const prevExtras = process.env.TA_LIB_EXTRAS;
  process.env.TA_LIB_EXTRAS = 'false'; // the rules never read the TA-Lib extras (only the trained networks do): 10x faster
  const cs = Object.fromEntries(TFS.map(([tf, m]) => [tf, aggregate(g, m, nMax)])) as Record<Timeframe, Candle[]>;
  const d1All = [cs['1d'], ...others.map((o) => dailyOf(o))];
  const n5 = cs['5m'].length;
  const ids: string[] = [], idx = new Map<string, number>(), s: Int8Array[] = [];
  const put = (id: string, k: number, d: number) => { let j = idx.get(id); if (j === undefined) { j = ids.length; idx.set(id, j); ids.push(id); s.push(new Int8Array(n5)); } s[j][k] = d; };
  const net = new Float32Array(n5).fill(NaN);
  const latest: Partial<Record<Timeframe, TfState>> = {}, lastJ: Partial<Record<Timeframe, number>> = {};
  let dayK = -1, breadth: ReturnType<typeof breadthOf>;
  const t0 = Date.now();
  for (let k = 29; k < n5; k++) {
    const end = (k + 1) * 5, t = g.t0 + end * MIN;
    for (const [tf, m] of TFS) {
      const j = Math.floor(end / m) - 1;
      if (j < 29 || lastJ[tf] === j) continue;
      lastJ[tf] = j;
      const st = tfState(tf, cs[tf].slice(Math.max(0, j - W[tf] + 1), j + 1));
      if (st) latest[tf] = st; else delete latest[tf];
    }
    const dk = Math.floor(end / 1440);
    if (dk !== dayK) { dayK = dk; breadth = breadthOf(d1All, t); }
    const snap = evaluate(g.asset, latest, t, { asset: g.asset, breadth });
    for (const x of snap.signals) if (x.dir) put(`ta:${x.id}@${x.tf}`, k, x.dir);
    for (const x of snap.book ?? []) if (x.dir) put(`book:${x.id}@${x.tf}`, k, x.dir);
    for (const c of snap.confluences) if (c.score) put(`conf:${c.id}`, k, c.score > 0 ? 1 : -1);
    net[k] = snap.net;
    if (k % 100_000 === 0) log(`analyzer walk ${k}/${n5} five-minute bars (${((Date.now() - t0) / 60000).toFixed(1)} min)`);
  }
  if (prevExtras === undefined) delete process.env.TA_LIB_EXTRAS; else process.env.TA_LIB_EXTRAS = prevExtras;
  log(`analyzer walk: ${n5} five-minute bars, ${ids.length} rule / rule-book / confluence readings in ${((Date.now() - t0) / 60000).toFixed(1)} min`);
  return { ids, s, net };
}

function dailyOf(h1: Candle[]): Candle[] {
  const out: Candle[] = [];
  for (const c of h1) {
    const d = Math.floor(c.ts / 86_400_000) * 86_400_000, last = out[out.length - 1];
    if (last && last.ts === d) { last.h = Math.max(last.h, c.h); last.l = Math.min(last.l, c.l); last.c = c.c; last.v += c.v; }
    else out.push({ ts: d, o: c.o, h: c.h, l: c.l, c: c.c, v: c.v });
  }
  // Only whole days count as closed: a day is readable once its last hour closed (breadthOf reads closed bars by time).
  return out;
}

function cachedAnalyzer(g: Grid, nMax: number, others: Candle[][], dir: string | undefined, log: (m: string) => void): { ids: string[]; s: Int8Array[]; net: Float32Array } {
  const file = dir ? path.join(dir, `${g.asset}-${MODULES_VERSION}-${nMax}.bin`) : undefined;
  const digest = file ? walkDigest(g, nMax, others) : '';
  if (file && fs.existsSync(file)) {
    try {
      const buf = fs.readFileSync(file), nl = buf.indexOf(10);
      const h = JSON.parse(buf.subarray(0, nl).toString()) as AnalyzerCache;
      const whole = buf.length === nl + 1 + h.n5 * 4 + h.n5 * h.ids.length;
      if (!whole) log(`analyzer cache ${file} is truncated: recomputing`);
      else if (h.digest !== digest) log(`analyzer cache ${file} was made from other code or data: recomputing`);
      if (whole && h.digest === digest && h.version === MODULES_VERSION && h.asset === g.asset && h.t0 === g.t0 && h.nMax === nMax) {
        let o = nl + 1;
        const net = new Float32Array(buf.buffer.slice(buf.byteOffset + o, buf.byteOffset + o + h.n5 * 4)); o += h.n5 * 4;
        const s = h.ids.map(() => { const a = new Int8Array(buf.buffer.slice(buf.byteOffset + o, buf.byteOffset + o + h.n5)); o += h.n5; return a; });
        log(`analyzer readings from the cache ${file} (${h.ids.length} readings)`);
        return { ids: h.ids, s, net };
      }
    } catch (e) { log(`analyzer cache unreadable (${String(e)}): recomputing`); }
  }
  const r = analyzerWalk(g, nMax, others, log);
  if (file) {
    fs.mkdirSync(dir!, { recursive: true });
    const n5 = r.net.length;
    const head = Buffer.from(JSON.stringify({ version: MODULES_VERSION, asset: g.asset, t0: g.t0, nMax, ids: r.ids, n5, digest } satisfies AnalyzerCache) + '\n');
    // Written beside, then renamed: an interrupted write never leaves a short file under the cache's name.
    fs.writeFileSync(`${file}.tmp`, Buffer.concat([head, Buffer.from(r.net.buffer), ...r.s.map((a) => Buffer.from(a.buffer))]));
    fs.renameSync(`${file}.tmp`, file);
  }
  return r;
}

// ---------------------------------------------------------------------------------------------------------------
// TA-Lib over full series.

function talibPrims(cs: Candle[], m: number): { prims: Prim[]; ht: Int8Array } {
  const n = cs.length;
  const o = cs.map((c) => c.o), h = cs.map((c) => c.h), l = cs.map((c) => c.l), c = cs.map((x) => x.c), v = cs.map((x) => x.v);
  const ohlc = { open: o, high: h, low: l, close: c }, hlc = { high: h, low: l, close: c }, real = { inReal: c };
  const out: Prim[] = [];
  const add = (id: string, f: (i: number) => number) => { const s = new Int8Array(n); for (let i = 0; i < n; i++) { const x = f(i); s[i] = x > 0 ? 1 : x < 0 ? -1 : 0; } out.push({ id: `${id}@${m}m`, fam: id, m, s }); };
  const netCdl = new Float64Array(n);
  const DIRLESS = new Set(['DOJI', 'DRAGONFLYDOJI', 'GRAVESTONEDOJI', 'SPINNINGTOP']); // TA-Lib returns +100 (or the bar's colour) for these: no direction
  for (const p of KEY_PATTERNS) {
    const r = tl(`CDL${p}`, ohlc).outInteger;
    if (!r) continue;
    if (!DIRLESS.has(p)) for (let i = 0; i < n; i++) netCdl[i] += Math.sign(r[i] || 0);
    add(`cdl_${p.toLowerCase()}`, (i) => r[i] || 0);
  }
  add('cdl_net', (i) => (netCdl[i] >= 2 ? 1 : netCdl[i] <= -2 ? -1 : 0));
  const one = (r: Record<string, number[]>, k = 'outReal') => r[k] ?? new Array<number>(n).fill(NaN);
  const sar = one(tl('SAR', { high: h, low: l }, { optInAcceleration: 0.02, optInMaximum: 0.2 }));
  add('tl_sar', (i) => (fin(sar[i]) ? c[i] - sar[i] : 0));
  const cci = one(tl('CCI', hlc, { optInTimePeriod: 20 }));
  add('tl_cci_rev', (i) => (i > 0 && fin(cci[i - 1]) ? (cci[i - 1] < -100 && cci[i] >= -100 ? 1 : cci[i - 1] > 100 && cci[i] <= 100 ? -1 : 0) : 0));
  const aro = one(tl('AROONOSC', { high: h, low: l }, { optInTimePeriod: 25 }));
  add('tl_aroon', (i) => (aro[i] >= 50 ? 1 : aro[i] <= -50 ? -1 : 0));
  const ult = one(tl('ULTOSC', hlc, { optInTimePeriod1: 7, optInTimePeriod2: 14, optInTimePeriod3: 28 }));
  add('tl_ultosc', (i) => (ult[i] < 30 ? 1 : ult[i] > 70 ? -1 : 0));
  const kama = one(tl('KAMA', real, { optInTimePeriod: 30 }));
  add('tl_kama', (i) => (fin(kama[i]) ? c[i] - kama[i] : 0));
  const srsi = one(tl('STOCHRSI', real, { optInTimePeriod: 14, optInFastK_Period: 5, optInFastD_Period: 3, optInFastD_MAType: 0 }), 'outFastK');
  add('tl_stochrsi', (i) => (srsi[i] < 20 ? 1 : srsi[i] > 80 ? -1 : 0));
  const trix = one(tl('TRIX', real, { optInTimePeriod: 15 }));
  add('tl_trix', (i) => (fin(trix[i]) ? trix[i] : 0));
  const cmo = one(tl('CMO', real, { optInTimePeriod: 14 }));
  add('tl_cmo', (i) => (cmo[i] < -50 ? 1 : cmo[i] > 50 ? -1 : 0));
  const ados = one(tl('ADOSC', { ...hlc, volume: v }, { optInFastPeriod: 3, optInSlowPeriod: 10 }));
  add('tl_adosc', (i) => (fin(ados[i]) ? ados[i] : 0));
  const slope = one(tl('LINEARREG_SLOPE', real, { optInTimePeriod: 14 }));
  add('tl_linreg', (i) => (fin(slope[i]) ? slope[i] : 0));
  const htm = tl('HT_TRENDMODE', real).outInteger ?? [];
  const ht = new Int8Array(n).fill(-1);
  for (let i = 0; i < n; i++) if (fin(htm[i])) ht[i] = htm[i] ? 1 : 0;
  return { prims: out, ht };
}

// ---------------------------------------------------------------------------------------------------------------
// The server's walk-forward forecasts (hourly; the forecast made at the close of the bar opening at ts).

function forecastRows(dir: string | undefined, sub: string, asset: string, notes: string[]): Map<number, number[]> | undefined {
  if (!dir) return undefined;
  const file = path.join(dir, sub, 'forecasts.json');
  let f: { schema: string; assets: Record<string, number[][]> } | undefined;
  try { f = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : undefined; } catch { f = undefined; }
  if (!f) { notes.push(`${sub}: no forecasts file`); return undefined; }
  const rows = f.assets?.[asset];
  if (!rows?.length) { notes.push(`${sub} (${f.schema}): no rows for ${asset}`); return undefined; }
  const m = new Map<number, number[]>();
  for (const r of rows) m.set(r[0], r.slice(1));
  notes.push(`${sub} (${f.schema}): ${rows.length} hourly forecasts for ${asset}, ${new Date(rows[0][0]).toISOString().slice(0, 13)} .. ${new Date(rows[rows.length - 1][0]).toISOString().slice(0, 13)}`);
  return m;
}

/** A forecast series on the hourly grid (NaN where missing), its discovery-period values. */
function hourlySeries(g: Grid, nh: number, rows: Map<number, number[]> | undefined, col: number, discEnd: number): { x: Float64Array; disc: number[] } {
  const x = new Float64Array(nh).fill(NaN), disc: number[] = [];
  if (!rows) return { x, disc };
  for (let k = 0; k < nh; k++) {
    const r = rows.get(g.t0 + k * H);
    const v = r?.[col];
    if (v !== undefined && fin(v)) { x[k] = v; if (g.t0 + (k + 1) * H <= discEnd) disc.push(v); }
  }
  return { x, disc };
}

/** Thresholds from the discovery hours; when the forecasts start after discovery, from their first 2,000 hours
 *  (noted: those hours then saw their own threshold). */
function calib(s: { x: Float64Array; disc: number[] }, name: string, notes: string[]): number[] {
  if (s.disc.length >= 500) return s.disc;
  const first: number[] = [];
  for (let k = 0; k < s.x.length && first.length < 2000; k++) if (fin(s.x[k])) first.push(s.x[k]);
  if (first.length) notes.push(`${name}: ${s.disc.length} discovery hours; thresholds from its first ${first.length} hours instead`);
  return first;
}

function bandPrim(id: string, s: { x: Float64Array; disc: number[] }, center: 'median' | 'zero', p: number, notes: string[]): Prim | undefined {
  const ref = calib(s, id, notes);
  if (ref.length < 100) return undefined;
  const c = center === 'median' ? quant(ref, 0.5) : 0;
  const band = quant(ref.map((v) => Math.abs(v - c)), p);
  const out = new Int8Array(s.x.length);
  for (let k = 0; k < s.x.length; k++) { const d = s.x[k] - c; out[k] = !fin(d) ? 0 : d >= band ? 1 : d <= -band ? -1 : 0; }
  notes.push(`${id}: center ${c.toPrecision(4)}, band ${band.toPrecision(4)}`);
  return { id, fam: id, m: 60, s: out };
}

// ---------------------------------------------------------------------------------------------------------------

export function modulePrims(g: Grid, nMax: number, o: { history?: string; forecasts?: string; cacheDir?: string; discoveryEnd: number; others?: string[]; log?: (m: string) => void }): ModuleOut {
  const log = o.log ?? console.log;
  const notes: string[] = [`TA engine: ${taEngine()}`];
  // The other coins' Binance hourly bars (character correlation, breadth).
  const others: Candle[][] = [];
  for (const a of (o.others ?? ['BTC', 'ETH', 'SOL', 'XRP']).filter((x) => x !== g.asset)) {
    const cs = o.history ? readSeries(seriesPath(o.history, 'binance-1h', a, '1h')) : [];
    if (cs.length) others.push(cs); else notes.push(`no Binance hourly bars for ${a}`);
  }
  notes.push(`other coins' hourly bars: ${others.length}`);
  const prims: Prim[] = [];
  // The analyzer.
  const an = cachedAnalyzer(g, nMax, others, o.cacheDir, log);
  const n5 = an.net.length;
  for (let j = 0; j < an.ids.length; j++) prims.push({ id: an.ids[j], fam: an.ids[j].replace(/@.*$/, ''), m: 5, s: an.s[j] });
  {
    const disc: number[] = [];
    for (let k = 0; k < n5; k++) if (fin(an.net[k]) && g.t0 + (k + 1) * 5 * MIN <= o.discoveryEnd) disc.push(Math.abs(an.net[k]));
    const th = quant(disc, 0.8);
    const s = new Int8Array(n5);
    for (let k = 0; k < n5; k++) { const x = an.net[k]; s[k] = !fin(x) || !(th > 0) ? 0 : x >= th ? 1 : x <= -th ? -1 : 0; }
    prims.push({ id: 'ta_net', fam: 'ta_net', m: 5, s });
    notes.push(`ta_net: |net| >= ${th?.toFixed(3)} (discovery 80th percentile)`);
  }
  // TA-Lib.
  let ht = new Int8Array(0);
  for (const m of [15, 60]) {
    const t = Date.now();
    const r = talibPrims(aggregate(g, m, nMax), m);
    prims.push(...r.prims);
    if (m === 60) ht = r.ht;
    log(`TA-Lib @${m}m: ${r.prims.length} readings in ${((Date.now() - t) / 1000).toFixed(1)} s`);
  }
  // Forecasts.
  const nh = Math.floor(nMax / 60);
  const oos = forecastRows(o.forecasts, '.tanet-oos', g.asset, notes);
  const lib = forecastRows(o.forecasts, '.librarian', g.asset, notes);
  const xg = forecastRows(o.forecasts, '.xgraph', g.asset, notes);
  const pushP = (p: Prim | undefined) => { if (p) prims.push(p); };
  pushP(bandPrim('tanet_up1', hourlySeries(g, nh, oos, 0, o.discoveryEnd), 'median', 0.7, notes));
  pushP(bandPrim('tanet_up4', hourlySeries(g, nh, oos, 1, o.discoveryEnd), 'median', 0.7, notes));
  pushP(bandPrim('lib_net', hourlySeries(g, nh, lib, 4, o.discoveryEnd), 'zero', 0.7, notes));
  pushP(bandPrim('xg_rel4', hourlySeries(g, nh, xg, 0, o.discoveryEnd), 'zero', 0.7, notes));
  pushP(bandPrim('xg_rel24', hourlySeries(g, nh, xg, 1, o.discoveryEnd), 'zero', 0.7, notes));
  pushP(bandPrim('xg_rank', hourlySeries(g, nh, xg, 2, o.discoveryEnd), 'median', 0.6, notes));
  // Hourly conditions.
  const ci = (name: string) => MODULE_CONDS.indexOf(name);
  const char = new Uint8Array(nh).fill(NONE), libC = new Uint8Array(nh).fill(NONE), vol = new Uint8Array(nh).fill(NONE), htC = new Uint8Array(nh).fill(NONE);
  {
    const t = Date.now();
    const h1 = aggregate(g, 60, nMax), d1 = aggregate(g, 1440, nMax);
    const oIdx = others.map(() => 0);
    const CH: Record<string, string> = { calm: 'char_calm', trending: 'char_trending', volatile_idio: 'char_vidio', volatile_systemic: 'char_vsys' };
    for (let k = 159; k < nh; k++) {
      const tEnd = g.t0 + (k + 1) * H;
      const jd = Math.floor((k + 1) / 24) - 1;
      const oth = others.map((cs, q) => { while (oIdx[q] < cs.length && cs[oIdx[q]].ts + H <= tEnd) oIdx[q]++; return cs.slice(Math.max(0, oIdx[q] - 160), oIdx[q]); });
      const c = characterOf(h1.slice(k - 159, k + 1), jd >= 0 ? d1.slice(Math.max(0, jd - 199), jd + 1) : [], oth);
      char[k] = ci(CH[c.cls]);
    }
    log(`character classifier: ${nh} hours in ${((Date.now() - t) / 1000).toFixed(1)} s`);
    const LIBS = ['lib_trend', 'lib_revert', 'lib_breakout', 'lib_flat'];
    const volS = hourlySeries(g, nh, oos, 2, o.discoveryEnd), volRef = calib(volS, 'tanet_vol', notes), volMed = quant(volRef, 0.5);
    for (let k = 0; k < nh; k++) {
      const w = lib?.get(g.t0 + k * H)?.slice(0, 4);
      if (w && w.every(fin)) { let b = 0; for (let q = 1; q < 4; q++) if (w[q] > w[b]) b = q; libC[k] = ci(LIBS[b]); }
      if (fin(volS.x[k]) && fin(volMed)) vol[k] = ci(volS.x[k] >= volMed ? 'tanet_vol_hi' : 'tanet_vol_lo');
      if (k < ht.length && ht[k] >= 0) htC[k] = ci(ht[k] ? 'ht_trend' : 'ht_cycle');
    }
  }
  const counts = (a: Uint8Array) => { const c: Record<string, number> = {}; for (const x of a) if (x !== NONE) c[MODULE_CONDS[x]] = (c[MODULE_CONDS[x]] ?? 0) + 1; return Object.entries(c).map(([k, v]) => `${k} ${(100 * v / Math.max(1, a.length)).toFixed(0)}%`).join(', '); };
  notes.push(`hours by character: ${counts(char)}; Librarian: ${counts(libC) || 'none'}; TA Net vol: ${counts(vol) || 'none'}; HT: ${counts(htC)}`);
  for (const n of notes) log(n);
  return { prims, hourly: { char, lib: libC, vol, ht: htC }, notes };
}
