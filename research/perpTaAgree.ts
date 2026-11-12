// Coinbase vs Binance signal agreement for the perp TA rulebook (thread "Build a TA rulebook for perpetuals"; Steven asked
// Nov 5 2026 at 3:14 PM EST / 20:14 UTC whether the TA reads spot: it does, but the sweep's history is Binance spot while
// the live setups trader draws its levels from Coinbase spot candles). Before any rule goes live, every primitive the sweep
// reads is computed twice over the same minutes: once on Binance spot (the sweep's grid) and once with the spot columns
// replaced by Coinbase's 1-minute candles (perp columns, funding and open interest unchanged). Per primitive:
//   trigger recall     share of Binance trigger bars (a new nonzero reading at a bar close) that Coinbase also fires, the
//                      same way, within one bar of the primitive's timeframe
//   trigger precision  share of Coinbase trigger bars that Binance also fires (same rule)
//   state agreement    share of bars, among those where either venue reads nonzero, where both read the same
// The window is before the seal (2025-07-01): the sealed block is not read. Coinbase's candles carry no taker-buy split, so
// the taker-flow readings (tflow*, and anything built on taker-buy volume) cannot agree and are listed apart.
//
//   coin    node --import tsx research/perpTaAgree.ts coin --data data/perp-ta/BTC.bin --coinbase data/history
//           [--from 2024-12-01 --to 2025-07-01 --warmup-days 45] [--modules false] --out out/agree-BTC.json
//   report  node --import tsx research/perpTaAgree.ts report --in out --out report

import fs from 'fs';
import path from 'path';
import { readGrid, buildPrims, triggers, sourceOf, COLS, type Grid, type Prim } from './perpTaSweep';
import { modulePrims } from './perpTaModules';
import { readSeries, seriesPath } from './history/candles';
import type { Candle } from '../bot/ta/indicators';

const MIN = 60_000, DAY = 86_400_000;
const fin = Number.isFinite;

/** Minutes [from, to) of a grid as a grid of its own (t0 kept on the original bar boundaries when from is a UTC midnight). */
export function subGrid(g: Grid, from: number, to: number): Grid {
  const i0 = Math.max(0, Math.round((from - g.t0) / MIN)), i1 = Math.min(g.n, Math.round((to - g.t0) / MIN));
  if (!(i1 > i0)) throw new Error(`subGrid: no minutes in ${new Date(from).toISOString()} .. ${new Date(to).toISOString()}`);
  const c = Object.fromEntries(COLS.map((k) => [k, g.c[k].slice(i0, i1)])) as Grid['c'];
  return { asset: g.asset, t0: g.t0 + i0 * MIN, n: i1 - i0, c, fundRaw: g.fundRaw.slice(i0, i1) };
}

/** The grid with its spot columns from another venue's 1-minute candles. Coinbase sends no candle for a minute without a
 *  trade: such a minute is a flat bar at the last close with no volume, up to maxGap minutes; a longer hole (an outage) is
 *  not valid. Taker-buy volume is NaN unless the candles carry it. */
export function withSpot(g: Grid, cs: Candle[], maxGap = 60): { g: Grid; matched: number; flat: number; holes: number } {
  const c = Object.fromEntries(COLS.map((k) => [k, g.c[k].slice()])) as Grid['c'];
  const at = new Map<number, Candle>();
  for (const x of cs) if (x.ts >= g.t0 && x.ts < g.t0 + g.n * MIN) at.set(Math.round((x.ts - g.t0) / MIN), x);
  let last = NaN, since = Infinity, matched = 0, flat = 0, holes = 0;
  for (let i = 0; i < g.n; i++) {
    const x = at.get(i);
    if (x && fin(x.c) && x.c > 0) {
      c.so[i] = x.o; c.sh[i] = x.h; c.sl[i] = x.l; c.sc[i] = x.c; c.sv[i] = x.v; c.stb[i] = fin(x.tb as number) ? (x.tb as number) : NaN;
      last = x.c; since = 0; matched++;
      continue;
    }
    since++;
    if (fin(last) && since <= maxGap) { c.so[i] = c.sh[i] = c.sl[i] = c.sc[i] = last; c.sv[i] = 0; c.stb[i] = NaN; flat++; }
    else { c.valid[i] = 0; if (fin(last)) { c.so[i] = c.sh[i] = c.sl[i] = c.sc[i] = last; } c.sv[i] = 0; c.stb[i] = NaN; holes++; }
  }
  return { g: { ...g, c }, matched, flat, holes };
}

export interface PrimAgree { id: string; source: string; m: number; nB: number; nC: number; recall: number | null; precision: number | null; state: number | null; stateBars: number; taker: boolean }

/** Bars of p's timeframe whose close falls in minutes [i0, i1). */
const barRange = (m: number, i0: number, i1: number): [number, number] => [Math.max(1, Math.ceil((i0 + 1) / m) - 1), Math.floor((i1 + 1) / m) - 1];

/** Agreement of one primitive computed on two grids over the same minutes [i0, i1). */
export function agreeOne(pb: Prim, pc: Prim, vb: Float32Array, vc: Float32Array, n: number, i0: number, i1: number): Omit<PrimAgree, 'source' | 'taker'> {
  const tb = triggers(pb, vb, n), tc = triggers(pc, vc, n), tol = pb.m;
  const inWin = (t: { idx: Int32Array; dir: Int8Array }) => { const idx: number[] = [], dir: number[] = []; for (let q = 0; q < t.idx.length; q++) if (t.idx[q] >= i0 && t.idx[q] < i1) { idx.push(t.idx[q]); dir.push(t.dir[q]); } return { idx, dir }; };
  const B = inWin(tb), C = inWin(tc);
  const hits = (a: { idx: number[]; dir: number[] }, b: { idx: number[]; dir: number[] }): number => {
    let h = 0, lo = 0;
    for (let q = 0; q < a.idx.length; q++) {
      const i = a.idx[q];
      while (lo < b.idx.length && b.idx[lo] < i - tol) lo++;
      for (let r = lo; r < b.idx.length && b.idx[r] <= i + tol; r++) if (b.dir[r] === a.dir[q]) { h++; break; }
    }
    return h;
  };
  const [k0, k1] = barRange(pb.m, i0, i1);
  let either = 0, same = 0;
  for (let k = k0; k <= k1 && k < pb.s.length && k < pc.s.length; k++) { const a = pb.s[k], b = pc.s[k]; if (a !== 0 || b !== 0) { either++; if (a === b) same++; } }
  return {
    id: pb.id, m: pb.m, nB: B.idx.length, nC: C.idx.length,
    recall: B.idx.length ? +(hits(B, C) / B.idx.length).toFixed(4) : null,
    precision: C.idx.length ? +(hits(C, B) / C.idx.length).toFixed(4) : null,
    state: either ? +(same / either).toFixed(4) : null, stateBars: either,
  };
}

/** Readings built on taker-buy volume (Coinbase candles have none). */
export const isTaker = (id: string) => /^tflow|taker|^cvd|obv_tb|flow_imb/i.test(id);

export interface CoinAgree { schema: 'perpta-agree1'; asset: string; from: string; to: string; warmupDays: number; minutes: number; coinbase: { matched: number; flat: number; holes: number }; prims: PrimAgree[]; notes: string[] }

export function agreeCoin(g: Grid, cs: Candle[], o: { from: number; to: number; warmupDays?: number; modules?: false | { cacheDir?: string }; log?: (m: string) => void }): CoinAgree {
  const log = o.log ?? console.log, warm = o.warmupDays ?? 45;
  const start = o.from - warm * DAY;
  if (new Date(start).getUTCHours() || new Date(start).getUTCMinutes()) throw new Error('--from less the warm-up must be a UTC midnight (keeps the 4h bar boundaries)');
  const gb = subGrid(g, start, o.to);
  const sp = withSpot(gb, cs);
  const gc = sp.g, n = gb.n, i0 = Math.round((o.from - gb.t0) / MIN), i1 = n;
  log(`${g.asset}: ${n} minutes (${warm} warm-up days), Coinbase bars ${sp.matched}, flat (no trade) ${sp.flat}, holes ${sp.holes}`);
  const notes: string[] = [];
  const pb = buildPrims(gb, n, () => {}), pcs = buildPrims(gc, n, () => {});
  if (o.modules !== false) {
    // The analyzer, rule book, confluences, TA-Lib and conviction on each venue's bars; the server's forecasts are the
    // same for both venues (they do not read these bars), so they are left out.
    const mb = modulePrims(gb, n, { cacheDir: o.modules?.cacheDir, discoveryEnd: o.from, log: () => {} });
    const mc = modulePrims(gc, n, { cacheDir: o.modules?.cacheDir, discoveryEnd: o.from, log: () => {} });
    const keep = (p: Prim) => sourceOf(p.id) !== 'TA Net / Librarian / cross graph';
    pb.push(...mb.prims.filter(keep)); pcs.push(...mc.prims.filter(keep));
    notes.push(...mb.notes.filter((x) => !/forecast/i.test(x)).slice(0, 3));
  }
  const byId = new Map(pcs.map((p) => [p.id, p]));
  const prims: PrimAgree[] = [];
  for (const p of pb) {
    const q = byId.get(p.id);
    if (!q) { notes.push(`${p.id}: not built on Coinbase bars`); continue; }
    prims.push({ ...agreeOne(p, q, gb.c.valid, gc.c.valid, n, i0, i1), source: sourceOf(p.id), taker: isTaker(p.id) });
  }
  return { schema: 'perpta-agree1', asset: g.asset, from: new Date(o.from).toISOString(), to: new Date(o.to).toISOString(), warmupDays: warm, minutes: i1 - i0, coinbase: { matched: sp.matched, flat: sp.flat, holes: sp.holes }, prims, notes };
}

const median = (x: number[]) => { if (!x.length) return NaN; const s = [...x].sort((a, b) => a - b), k = s.length >> 1; return s.length % 2 ? s[k] : (s[k - 1] + s[k]) / 2; };
const pct = (v: number) => (fin(v) ? `${(100 * v).toFixed(0)}%` : '-');

export function agreeReport(coins: CoinAgree[]): { md: string; summary: Record<string, unknown> } {
  const rows: string[] = [];
  const bySrc: Record<string, { r: number[]; p: number[]; s: number[]; n: number }> = {};
  for (const c of coins) for (const p of c.prims) {
    if (p.taker) continue;
    const b = (bySrc[p.source] ??= { r: [], p: [], s: [], n: 0 });
    b.n++;
    if (p.recall !== null && p.nB >= 30) b.r.push(p.recall);
    if (p.precision !== null && p.nC >= 30) b.p.push(p.precision);
    if (p.state !== null && p.stateBars >= 30) b.s.push(p.state);
  }
  const all = coins.flatMap((c) => c.prims.filter((p) => !p.taker).map((p) => ({ ...p, a: c.asset })));
  const worst = all.filter((p) => p.recall !== null && p.nB >= 30).sort((x, y) => (x.recall as number) - (y.recall as number)).slice(0, 15);
  const taker = coins.flatMap((c) => c.prims.filter((p) => p.taker).map((p) => `${c.asset} ${p.id}`));
  rows.push(
    `### Perp TA: do the signals fire the same on Coinbase spot as on Binance spot?`,
    '',
    `Every primitive the sweep reads, computed on each venue's 1-minute spot bars over the same minutes (perp prices, funding and open interest the same), ${coins.map((c) => `${c.asset} ${c.from.slice(0, 10)} .. ${c.to.slice(0, 10)} (Coinbase bars ${c.coinbase.matched}, no-trade minutes ${c.coinbase.flat}, holes ${c.coinbase.holes})`).join('; ')}. Trigger recall: share of Binance trigger bars Coinbase also fires the same way within one bar; precision: the reverse; state: share of bars, where either reads nonzero, that read the same. Medians over primitives with at least 30 events.`,
    '',
    '| source | primitives | trigger recall | trigger precision | state agreement |',
    '|---|---|---|---|---|',
    ...Object.entries(bySrc).sort((a, b) => b[1].n - a[1].n).map(([k, v]) => `| ${k} | ${v.n} | ${pct(median(v.r))} | ${pct(median(v.p))} | ${pct(median(v.s))} |`),
    `| **all** | ${all.length} | ${pct(median(all.filter((p) => p.recall !== null && p.nB >= 30).map((p) => p.recall as number)))} | ${pct(median(all.filter((p) => p.precision !== null && p.nC >= 30).map((p) => p.precision as number)))} | ${pct(median(all.filter((p) => p.state !== null && p.stateBars >= 30).map((p) => p.state as number)))} |`,
    '',
    '**Least agreeing primitives** (trigger recall, at least 30 Binance triggers)',
    '',
    '| coin | primitive | source | Binance triggers | Coinbase triggers | recall | precision | state |',
    '|---|---|---|---|---|---|---|---|',
    ...worst.map((p) => `| ${p.a} | ${p.id} | ${p.source} | ${p.nB} | ${p.nC} | ${pct(p.recall as number)} | ${pct(p.precision ?? NaN)} | ${pct(p.state ?? NaN)} |`),
    '',
    taker.length ? `Not comparable (built on taker-buy volume, which Coinbase candles do not split): ${taker.join(', ')}.` : '',
    ...coins.flatMap((c) => c.notes.map((x) => `- ${c.asset}: ${x}`)),
  );
  return { md: rows.join('\n'), summary: { coins: coins.map((c) => ({ asset: c.asset, from: c.from, to: c.to, coinbase: c.coinbase, prims: c.prims.length })), bySource: Object.fromEntries(Object.entries(bySrc).map(([k, v]) => [k, { prims: v.n, recall: median(v.r), precision: median(v.p), state: median(v.s) }])) } };
}

async function main() {
  const mode = process.argv[2];
  const arg = (k: string, d?: string) => { const i = process.argv.indexOf(`--${k}`); return i >= 0 ? process.argv[i + 1] : d; };
  const log = (m: string) => console.log(`[perp-ta-agree] ${m}`);
  if (mode === 'coin') {
    const g = readGrid(arg('data')!);
    const from = Date.parse(`${arg('from', '2024-12-01')}T00:00:00Z`), to = Date.parse(`${arg('to', '2025-07-01')}T00:00:00Z`);
    if (!(from < to)) throw new Error('--from must be before --to');
    if (to > Date.UTC(2025, 6, 1)) throw new Error('--to after the seal (2025-07-01): the sealed block is not read here');
    const cs = readSeries(seriesPath(arg('coinbase', 'data/history')!, 'coinbase', g.asset, '1m'));
    if (!cs.length) throw new Error(`no Coinbase 1m candles for ${g.asset} under ${arg('coinbase', 'data/history')}`);
    const r = agreeCoin(g, cs, { from, to, warmupDays: +arg('warmup-days', '45')!, modules: arg('modules', 'true') === 'false' ? false : { cacheDir: arg('module-cache') }, log });
    const out = arg('out')!;
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, JSON.stringify(r));
    log(`${g.asset}: ${r.prims.length} primitives compared; wrote ${out}`);
    return;
  }
  if (mode === 'report') {
    const dir = arg('in')!, outDir = arg('out', 'report')!;
    const coins = fs.readdirSync(dir, { recursive: true }).map(String).filter((f) => /agree-[A-Z0-9]+\.json$/.test(f)).map((f) => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')) as CoinAgree);
    if (!coins.length) throw new Error('no agree-<coin>.json in --in');
    const r = agreeReport(coins);
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(path.join(outDir, 'summary.md'), r.md + '\n');
    fs.writeFileSync(path.join(outDir, 'summary.json'), JSON.stringify(r.summary, null, 1));
    console.log(r.md);
    return;
  }
  throw new Error('usage: perpTaAgree.ts coin|report ...');
}

if (process.argv[1] && /perpTaAgree\.(ts|js)$/.test(process.argv[1])) main().catch((e) => { console.error(e); process.exit(1); });
