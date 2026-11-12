// The blind test of the perp TA rulebook (thread "Build a TA rulebook for perpetuals", Nov 5 2026). Pre-registered in
// /mnt/project-files/perp-ta/preregistration.md ("Blind test pass rule" and the change log entry of Nov 5, 10:29 AM EST /
// 15:29 UTC): the frozen candidate set of one sweep run is traded, unchanged, on the sealed block (2025-07-01 to the end
// of Binance history), which the sweep never read. The set is opened once: the workflow logs the opening on Drive before
// any sealed number is computed and refuses a second opening of the same set.
//
//   freeze  node --import tsx research/perpTaBlind.ts freeze --candidates report/candidates.json.gz --run <sweep run> --out frozen.json
//   coin    node --import tsx research/perpTaBlind.ts coin --frozen frozen.json --data data/perp-ta/BTC.bin --out out/blind-BTC.json
//           [--history data/hist-BTC --forecasts data/server-hist --module-cache data/modcache]
//   report  node --import tsx research/perpTaBlind.ts report --frozen frozen.json --in in --out blind-report
//
// Before the sealed block is read, every candidate's discovery trades are recomputed from scratch on the full-length
// history and must match the frozen record (n exactly, mean within 0.05 bps); a mismatch stops the coin with no sealed
// number computed. Per candidate (sealed): n >= 20, net > 0, excess over random entries > 0, net t >= 1 and excess
// t >= 1. The rulebook (every frozen candidate together; $500 a position, $1,000 open at most, one position per coin,
// earliest signal first) passes with a day-block bootstrap 90% one-sided lower bound on $/h above 0, positive on BTC,
// ETH and one of SOL / XRP, no month holding more than half the gain, and still above 0 at +3 bps per side; from round 2
// also above 0 with funding paid x1.5 and received x0.5; from Nov 5 5:30 PM EST / 22:30 UTC (before any round 3 opening)
// also the project's held-out standard HO-1 on the sealed block (ho1Of: 6 day folds, 4 won, none below -$0.50/h; 2 of 3
// regime v1 RV terciles won, none below -$0.50/h; above its random-entry placebo). A round 2 maker order that did not fill holds its coin's slot
// until cancelled (a signal row [ts, 0, cancel ts, 0, 0]) and is not a trade.

import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import crypto from 'crypto';
import { regRow, runRef } from './perpTaRegistry';
import {
  readGrid, buildPrims, triggers, stateAt, outcomes, atrUnit, conditions, folds, POLICIES_ALL, CONDS, NZ, KALSHI_COSTS,
  type Grid, type Prim, type Costs, type Candidate, type Policy,
} from './perpTaSweep';
import { modulePrims, MODULE_CONDS } from './perpTaModules';
import { rvTerciles, spotFromCsv } from './perpTaRegime';

const MIN = 60_000;
const DAY = 86_400_000;
const fin = Number.isFinite;

/** costs / policy: the coin's costs and the exit policy exactly as the sweep ran them (round 2: per-coin half-spread and
 *  funding offset, maker entries); absent on a set frozen before round 2 (the set's costs, and the policy found by id in
 *  any round's policies, POLICIES_ALL: their ids differ). */
export interface FrozenCand { id: string; a: string; group: string; rule: string; mode: 'follow' | 'fade'; pol: string; side: 'long' | 'short'; cond: string; disc: { n: number; mean: number; t: number; exc: number; tExc: number }; costs?: Costs; policy?: Policy }
export interface Frozen { schema: 'perpta-frozen1'; run: string; sha: string; at: string; seal: string; validFrom: string; costs: Costs; passing: number; hash: string; cands: FrozenCand[] }

/** The frozen set: the candidates that passed the sweep's selection (forecast-reading cells never do), at most 20:
 *  one per (coin, trigger, mode, side) (the same trigger under another filter fires mostly the same trades), then the
 *  coins in turn, each coin's best discovery excess t first, so no coin's near-copies take every slot. */
export function freeze(cands: Candidate[], o: { run: string; sha: string; seal: string; validFrom: string; costs: Costs; max?: number }): Frozen {
  const pass = cands.filter((c) => c.why.length === 0 && !c.diagnostic).sort((x, y) => y.disc.tExc - x.disc.tExc);
  const seen = new Set<string>(), byCoin = new Map<string, Candidate[]>();
  for (const c of pass) {
    const key = `${c.a}|${c.rule.split('+')[0]}|${c.mode}|${c.side}`;
    if (seen.has(key)) continue;
    seen.add(key); (byCoin.get(c.a) ?? byCoin.set(c.a, []).get(c.a)!).push(c);
  }
  const queues = [...byCoin.values()].sort((x, y) => y[0].disc.tExc - x[0].disc.tExc), pick: Candidate[] = [];
  for (let r = 0; pick.length < (o.max ?? 20) && queues.some((q) => q.length > r); r++) {
    const round = queues.filter((q) => q.length > r).map((q) => q[r]).sort((x, y) => y.disc.tExc - x.disc.tExc);
    pick.push(...round.slice(0, (o.max ?? 20) - pick.length));
  }
  const fz = pick.map((c, k): FrozenCand => {
    const policy = c.policyDef ?? policyById(c.pol);
    if (!policy) throw new Error(`${c.a} ${c.group}: exit policy ${c.pol} unknown`);
    return {
      id: `c${k + 1}`, a: c.a, group: c.group, rule: c.rule, mode: c.mode, pol: c.pol, side: c.side, cond: c.cond,
      disc: { n: c.disc.n, mean: c.disc.mean, t: c.disc.t, exc: c.disc.exc, tExc: c.disc.tExc }, costs: c.costs ?? o.costs, policy,
    };
  });
  const key = JSON.stringify({ seal: o.seal, validFrom: o.validFrom, costs: o.costs, cands: fz.map(({ a, rule, mode, pol, side, cond, costs, policy }) => ({ a, rule, mode, pol, side, cond, costs, policy })) });
  return { schema: 'perpta-frozen1', run: o.run, sha: o.sha, at: new Date().toISOString(), seal: o.seal, validFrom: o.validFrom, costs: o.costs, passing: pass.length, hash: crypto.createHash('sha1').update(key).digest('hex').slice(0, 16), cands: fz };
}

const policyById = (id: string): Policy | undefined => POLICIES_ALL.find((x) => x.id === id);

export interface SealedStats { n: number; mean: number; t: number; exc: number; tExc: number; hit: number; holdMin: number; over480: number; perDay: number; usdPerHourPer1k: number; stress6: number; fundStress?: number }
export interface CoinOut {
  schema: 'perpta-blind1'; asset: string; hash: string; sealFrom: string; sealTo: string; sealDays: number;
  replication: Array<{ id: string; ok: boolean; n: number; frozenN: number; mean: number; frozenMean: number }>;
  /** Only when every candidate of the coin replicated: the sealed stats and the rulebook signals (decision ts, net bps,
   *  exit ts, hold minutes, funding bps, the random-entry baseline bps of the same exit, side and condition that month,
   *  the regime v1 RV tercile at entry: 0 LOW, 1 MID, 2 HIGH, -1 NA) of each candidate. */
  cands?: Array<{ id: string; sealed: SealedStats; signals: Array<[number, number, number, number, number?, number?, number?]> }>;
  /** Sealed minutes in each regime v1 RV tercile (LOW, MID, HIGH, NA): the hours behind a tercile's $/h (HO-1). */
  terMinutes?: number[];
  notes: string[];
}

export function resolveRule(rule: string, byId: Map<string, Prim>): [Prim, Prim | undefined] | undefined {
  if (byId.has(rule)) return [byId.get(rule)!, undefined];
  for (let k = rule.indexOf('+'); k > 0; k = rule.indexOf('+', k + 1)) {
    const a = byId.get(rule.slice(0, k)), b = byId.get(rule.slice(k + 1));
    if (a && b) return [a, b];
  }
  return undefined;
}

function stats(xs: number[], ex: number[], vb: number[]): { n: number; mean: number; t: number; exc: number; tExc: number; hit: number } {
  const n = xs.length;
  if (n < 2) return { n, mean: n ? xs[0] : NaN, t: NaN, exc: n ? ex[0] : NaN, tExc: NaN, hit: n ? +(xs[0] > 0) : NaN };
  const m = xs.reduce((a, b) => a + b, 0) / n, em = ex.reduce((a, b) => a + b, 0) / n;
  const floor = Math.max(1e-9, vb.reduce((a, b) => a + b, 0) / n);
  const v = Math.max(floor, xs.reduce((a, b) => a + (b - m) ** 2, 0) / (n - 1)), ev = Math.max(floor, ex.reduce((a, b) => a + (b - em) ** 2, 0) / (n - 1));
  return { n, mean: m, t: m / Math.sqrt(v / n), exc: em, tExc: em / Math.sqrt(ev / n), hit: xs.filter((x) => x > 0).length / n };
}

/** The project's lockbox (meta plan thread: L1 Nov 6 05:00 - Nov 13 05:00 UTC, L2 Nov 13 - 20, each opened once): the blind
 *  test reads no minute from the start of the UTC day it opens (Nov 6 00:00 UTC, so no registry row carries a lockbox day)
 *  unless --end moves the cap (once the meta thread has opened the lockbox). */
export const LOCKBOX_FROM = Date.UTC(2026, 10, 6, 0);

/** One coin: replicate every frozen candidate's discovery trades, then (only if all match) its sealed trades, up to endMs
 *  (LOCKBOX_FROM by default). */
export function blindCoin(g: Grid, fz: Frozen, o: { modules?: false | { history?: string; forecasts?: string; cacheDir?: string }; log?: (m: string) => void; endMs?: number; spot?: { has: Uint8Array; close: Float64Array } }): CoinOut {
  const log = o.log ?? console.log;
  const cands = fz.cands.filter((c) => c.a === g.asset);
  const seal = Date.parse(fz.seal), validFrom = Date.parse(fz.validFrom);
  const nFull = Math.min(g.n, Math.max(0, Math.floor(((o.endMs ?? LOCKBOX_FROM) - g.t0) / MIN))), iSeal = Math.round((seal - g.t0) / MIN);
  if (nFull < g.n) log(`${g.asset}: sealed block capped at ${new Date(g.t0 + nFull * MIN).toISOString()} (the lockbox; --end moves it)`);
  const res: CoinOut = { schema: 'perpta-blind1', asset: g.asset, hash: fz.hash, sealFrom: fz.seal, sealTo: new Date(g.t0 + nFull * MIN).toISOString(), sealDays: +(Math.max(0, nFull - iSeal) / 1440).toFixed(2), replication: [], notes: [] };
  if (!cands.length) { res.notes.push('no frozen candidate on this coin'); res.cands = []; return res; }
  if (iSeal >= nFull - 1440) { res.notes.push('less than a day of history after the seal'); return res; }
  const quiet = () => undefined;
  const prims = buildPrims(g, nFull, quiet);
  let byId = new Map(prims.map((p) => [p.id, p]));
  const needMod = cands.some((c) => !resolveRule(c.rule, byId)) || cands.some((c) => MODULE_CONDS.includes(c.cond));
  const mod = needMod && o.modules !== false ? modulePrims(g, nFull, { ...(o.modules || {}), discoveryEnd: validFrom, log }) : undefined;
  if (mod) { prims.push(...mod.prims); byId = new Map(prims.map((p) => [p.id, p])); res.notes.push(...mod.notes.map((n) => `modules: ${n}`)); }
  // The coin's costs and the candidates' policies as the sweep ran them.
  const costs = cands[0].costs ?? fz.costs;
  if (cands.some((c) => JSON.stringify(c.costs ?? fz.costs) !== JSON.stringify(costs))) throw new Error(`${g.asset}: frozen candidates disagree on the coin's costs`);
  const pols: Policy[] = [];
  for (const c of cands) { const p = c.policy ?? policyById(c.pol); if (p && !pols.some((x) => x.id === p.id)) pols.push(p); }
  const unit = atrUnit(g, nFull), out = outcomes(g, nFull, unit, costs, pols), cond = conditions(g, nFull, mod), fo = folds(g, nFull, validFrom);
  const monthOf = new Int16Array(nFull);
  const y0 = new Date(g.t0).getUTCFullYear(), m0 = new Date(g.t0).getUTCMonth();
  for (let i = 0; i < nFull; i++) { const d = new Date(g.t0 + i * MIN); monthOf[i] = (d.getUTCFullYear() - y0) * 12 + d.getUTCMonth() - m0; }
  const NM = monthOf[nFull - 1] + 1;
  const inCond = (i: number, c: number) => { if (c === 0) return true; for (let z = 0; z < NZ; z++) if (cond[i * NZ + z] === c) return true; return false; };
  // The random-entry baseline of one (exit, direction, condition): mean and variance of every tradable minute's result
  // in each calendar month (as in the sweep).
  const baseCache = new Map<string, { m: Float64Array; v: Float64Array }>();
  const baseline = (k: number, c: number) => {
    const key = `${k}|${c}`;
    if (baseCache.has(key)) return baseCache.get(key)!;
    const s = new Float64Array(NM), s2 = new Float64Array(NM), n = new Float64Array(NM), nt = out.net[k];
    for (let i = 0; i < nFull; i++) { const x = nt[i]; if (x !== x || !inCond(i, c)) continue; const mo = monthOf[i]; s[mo] += x; s2[mo] += x * x; n[mo]++; }
    const m = new Float64Array(NM), v = new Float64Array(NM);
    for (let j = 0; j < NM; j++) { m[j] = n[j] ? s[j] / n[j] : 0; v[j] = n[j] > 1 ? Math.max(0, s2[j] / n[j] - m[j] * m[j]) : 0; }
    const r = { m, v }; baseCache.set(key, r); return r;
  };
  type Tr = { i: number; x: number; e: number; vb: number; ex: number; hd: number; fb: number };
  const plans = cands.map((c) => {
    const rr = resolveRule(c.rule, byId);
    if (!rr) return undefined;
    const [tp, fp] = rr, tr = triggers(tp, g.c.valid, nFull);
    const idx: number[] = [], dir: number[] = [];
    for (let q = 0; q < tr.idx.length; q++) { const i = tr.idx[q]; if (!fp || stateAt(fp, i) === tr.dir[q]) { idx.push(i); dir.push(tr.dir[q]); } }
    return { c, idx, dir, mode: c.mode === 'fade' ? 1 : 0, p: pols.findIndex((x) => x.id === c.pol), side: c.side === 'short' ? 1 : 0, ci: CONDS.indexOf(c.cond) };
  });
  // The cell exactly as the sweep walked it: one trade at a time over every entry of the rule (both sides, every
  // condition), a trade kept when its side and condition are the cell's; purged when its exit falls in the next fold.
  const cellTrades = (pl: NonNullable<(typeof plans)[number]>, from: number, to: number, purge: boolean): Tr[] => {
    const outT: Tr[] = [];
    let nextFree = 0;
    for (let q = 0; q < pl.idx.length; q++) {
      const i = pl.idx[q];
      if (i < nextFree) continue;
      if (!g.c.valid[i] || i + 1 >= nFull || !g.c.valid[i + 1]) continue;
      const sd = pl.dir[q], td = pl.mode === 0 ? sd : -sd, k = pl.p * 2 + (td > 0 ? 0 : 1);
      const x = out.net[k][i];
      if (x !== x) { const cx = out.exit[k][i]; if (cx > nextFree) nextFree = cx; continue; } // an unfilled maker order rested (as in the sweep)
      const ex = out.exit[k][i];
      nextFree = ex;
      if (i < from || i >= to) continue;
      if (purge && fo.of[ex] !== fo.of[i]) continue;
      if ((sd > 0 ? 0 : 1) !== pl.side || !inCond(i, pl.ci)) continue;
      const b = baseline(k, pl.ci), mo = monthOf[i], hd = out.hold[k][i];
      outT.push({ i, x, e: x - b.m[mo], vb: b.v[mo], ex, hd, fb: td * (out.cum[ex] - out.cum[ex - hd + 1]) * 1e4 });
    }
    return outT;
  };
  // 1. Replication on discovery (before any sealed number exists).
  const discEnd = fo.discovery < fo.starts.length ? fo.starts[fo.discovery] : iSeal;
  let allOk = true;
  for (let k = 0; k < cands.length; k++) {
    const c = cands[k], pl = plans[k];
    if (!pl || pl.p < 0 || pl.ci < 0) { res.replication.push({ id: c.id, ok: false, n: 0, frozenN: c.disc.n, mean: NaN, frozenMean: c.disc.mean }); allOk = false; res.notes.push(`${c.id}: rule, exit or condition not found (${c.rule} ${c.pol} ${c.cond})`); continue; }
    const d = cellTrades(pl, 0, discEnd, true), s = stats(d.map((t) => t.x), d.map((t) => t.e), d.map((t) => t.vb));
    const ok = s.n === c.disc.n && Math.abs(s.mean - c.disc.mean) <= 0.05;
    res.replication.push({ id: c.id, ok, n: s.n, frozenN: c.disc.n, mean: +s.mean.toFixed(3), frozenMean: c.disc.mean });
    if (!ok) allOk = false;
  }
  if (!allOk) { res.notes.push('replication failed: the sealed block was not read for this coin'); log(`${g.asset}: replication FAILED, sealed block not read`); return res; }
  log(`${g.asset}: ${cands.length} candidates replicate their discovery trades exactly; reading the sealed block`);
  // 2. The sealed block: the cell's own trades (as walked in the sweep, no fold purge inside the block) and its signals
  // for the rulebook (every entry of the right side and condition; the rulebook decides which it can take).
  const hours = (nFull - iSeal) / 60;
  // Regime v1 RV60 terciles of the coin's spot bars over the sealed block (HO-1: the result must hold in 2 of 3).
  // From the coin's Binance spot CSV (float64, every row a bar, as regime.py reads it) when the job has it; else from the
  // grid (Float32 closes; a minute with no spot bar is the previous close at zero volume), noted.
  const sp = o.spot;
  if (!sp) res.notes.push('RV terciles from the grid (no spot CSV): a zero-volume bar without a perp bar counts as a hole');
  const ter = sp ? rvTerciles(g.t0, nFull, (i) => sp.has[i] === 1, (i) => sp.close[i], iSeal, nFull)
    : rvTerciles(g.t0, nFull, (i) => g.c.valid[i] === 1 || g.c.sv[i] > 0, (i) => g.c.sc[i], iSeal, nFull);
  res.terMinutes = [0, 0, 0, 0];
  for (let i = iSeal; i < nFull; i++) res.terMinutes[ter[i] < 0 ? 3 : ter[i]]++;
  res.cands = cands.map((c, k) => {
    const pl = plans[k]!;
    const tr = cellTrades(pl, iSeal, nFull, false);
    const s = stats(tr.map((t) => t.x), tr.map((t) => t.e), tr.map((t) => t.vb));
    const sum = tr.reduce((a, t) => a + t.x, 0);
    const sealed: SealedStats = {
      n: s.n, mean: +s.mean.toFixed(2), t: +s.t.toFixed(3), exc: +s.exc.toFixed(2), tExc: +s.tExc.toFixed(3), hit: +s.hit.toFixed(3),
      holdMin: tr.length ? +(tr.reduce((a, t) => a + t.hd, 0) / tr.length).toFixed(1) : 0, over480: tr.filter((t) => t.hd > 480).length,
      perDay: +(s.n / (hours / 24)).toFixed(3), usdPerHourPer1k: +((sum / 1e4) * 1000 / hours).toFixed(4), stress6: +(s.mean - 6).toFixed(2),
      fundStress: tr.length ? +(s.mean - 0.5 * tr.reduce((a, t) => a + Math.abs(t.fb), 0) / tr.length).toFixed(2) : NaN,
    };
    // [decision ts, net bps, exit ts, hold minutes, funding bps, random-entry baseline bps, RV tercile at entry]; a maker
    // order that did not fill is [ts, 0, cancel ts, 0, 0, 0, -1] (it held the coin's slot and margin until cancelled;
    // nothing is booked).
    const signals: Array<[number, number, number, number, number, number, number]> = [];
    for (let q = 0; q < pl.idx.length; q++) {
      const i = pl.idx[q];
      if (i < iSeal || !g.c.valid[i] || i + 1 >= nFull || !g.c.valid[i + 1]) continue;
      const sd = pl.dir[q];
      if ((sd > 0 ? 0 : 1) !== pl.side || !inCond(i, pl.ci)) continue;
      const td = pl.mode === 0 ? sd : -sd, kk = pl.p * 2 + (td > 0 ? 0 : 1), x = out.net[kk][i], ex = out.exit[kk][i];
      if (x !== x) { if (ex > i) signals.push([g.t0 + i * MIN, 0, g.t0 + ex * MIN, 0, 0, 0, -1]); continue; }
      const hd = out.hold[kk][i], rnd = baseline(kk, pl.ci).m[monthOf[i]];
      signals.push([g.t0 + i * MIN, +x.toFixed(2), g.t0 + ex * MIN, hd, +(td * (out.cum[ex] - out.cum[ex - hd + 1]) * 1e4).toFixed(3), +rnd.toFixed(3), ter[i + 1]]);
    }
    return { id: c.id, sealed, signals };
  });
  return res;
}

// ---------------------------------------------------------------------------------------------------------------
// The report: per-candidate verdicts and the rulebook.

function rng(seed: number): () => number { let a = seed >>> 0; return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

export interface Book { members: string[]; trades: number; skippedBusy: number; skippedCap: number; usd: number; usdPerHour: number; lb90: number; stressUsdPerHour: number; fundStressUsdPerHour: number; unfilled: number; byCoin: Record<string, number>; bestMonthShare: number; months: Record<string, number>; over480: number; ho1: Ho1; pass: boolean; why: string[] ; /** $ per day on the sealed block (exit day, UTC), at perPos a position: the registry's by_day. */ byDay: Record<string, number> }

/** The held-out standard HO-1 (project registry README, Nov 5 2026 5:30 PM EST / 22:30 UTC; Steven: "held out data should be
 *  a large chunk of time"), history tier, on the sealed block: at least 90 held-out days; consecutive folds of HO-1's 16
 *  days (at least 6; about 30 over the ~490-day sealed block, so a 16-day loss cannot hide in a long fold), at least 4 in
 *  6 of them won (above 0, the flat benchmark), none below -$0.50/h; at least 2 of the 3 regime v1 RV terciles (at entry,
 *  each covering at least 100 book hours) won, none covered below -$0.50/h; above its placebo (the same trades entered at
 *  random: the random-entry baseline of each trade's exit, side and condition that month). $/h at $500 a position. */
export interface Ho1 {
  standard: 'HO-1'; tier: 'history'; days: number; folds: number; folds_won: number; worst_fold_per_hour: number;
  terciles_covered: number; terciles_won: number; worst_tercile_per_hour: number | null; beats_placebo: boolean;
  placebo_usd: number | null; fold_usd_per_hour: number[]; tercile_usd_per_hour: Array<number | null>; tercile_hours: number[]; why: string[];
}
export const HO1_RULES = { days: 90, folds: 6, foldDays: 16, foldsWon: 4, worstFold: -0.5, tercileHours: 100, tercilesWon: 2, worstTercile: -0.5 };

/** o.placebo replaces the random-entry placebo with an external one (round 4's circular shifts: the rule's $ priced as its
 *  placebo is, against the placebo's mean). */
export function ho1Of(byDay: Record<string, number>, taken: Array<{ x: number; rnd?: number; ter?: number }>, terHours: number[], perPos: number, o: { placebo?: { usd: number; placeboUsd: number } } = {}): Ho1 {
  const R = HO1_RULES, days = Object.keys(byDay).sort(), N = days.length;
  const foldUsdH: number[] = [], nF = Math.max(R.folds, Math.floor(N / R.foldDays)), need = Math.ceil((nF * R.foldsWon) / R.folds - 1e-9);
  for (let k = 0; k < nF; k++) {
    const a = Math.floor((k * N) / nF), b = Math.floor(((k + 1) * N) / nF);
    let u = 0;
    for (let d = a; d < b; d++) u += byDay[days[d]];
    foldUsdH.push(b > a ? u / ((b - a) * 24) : NaN);
  }
  const won = foldUsdH.filter((v) => v > 0).length, worstF = Math.min(...foldUsdH.map((v) => (v === v ? v : -Infinity)));
  const terUsd = [0, 0, 0];
  let placebo = 0;
  for (const s of taken) {
    if (s.ter !== undefined && s.ter >= 0 && s.ter <= 2) terUsd[s.ter] += (s.x / 1e4) * perPos;
    placebo += s.rnd === undefined || s.rnd === null ? NaN : (s.rnd / 1e4) * perPos;
  }
  const usd = taken.reduce((a, s) => a + (s.x / 1e4) * perPos, 0);
  const covered = [0, 1, 2].filter((k) => terHours[k] >= R.tercileHours);
  const terUsdH = [0, 1, 2].map((k) => (terHours[k] > 0 ? terUsd[k] / terHours[k] : null));
  const tWon = covered.filter((k) => (terUsdH[k] ?? 0) > 0).length;
  const worstT = covered.length ? Math.min(...covered.map((k) => terUsdH[k]!)) : null;
  if (o.placebo) placebo = o.placebo.placeboUsd;
  const beats = placebo === placebo && (o.placebo ? o.placebo.usd : usd) > placebo;
  const why: string[] = [];
  if (N < R.days) why.push(`HO-1: ${N} held-out days < ${R.days}`);
  if (won < need) why.push(`HO-1: ${won} of ${nF} folds won (needs ${need})`);
  if (!(worstF >= R.worstFold)) why.push(`HO-1: worst fold $${worstF.toFixed(3)}/h < $${R.worstFold}/h`);
  if (tWon < R.tercilesWon) why.push(`HO-1: ${tWon} of 3 RV terciles won with ${R.tercileHours}+ h (needs ${R.tercilesWon})`);
  if (worstT !== null && worstT < R.worstTercile) why.push(`HO-1: an RV tercile at $${worstT.toFixed(3)}/h < $${R.worstTercile}/h`);
  if (!beats) why.push(placebo !== placebo ? (o.placebo ? 'HO-1: no placebo (the block is too short for its circular shifts)' : 'HO-1: no placebo (signals without the random-entry baseline)') : o.placebo ? `HO-1: $${o.placebo.usd.toFixed(2)} not above its placebo $${placebo.toFixed(2)} (circular shifts, priced alike)` : `HO-1: $${usd.toFixed(2)} not above its placebo $${placebo.toFixed(2)} (the same trades at random entries)`);
  const r4 = (v: number) => +v.toFixed(4);
  return {
    standard: 'HO-1', tier: 'history', days: N, folds: nF, folds_won: won, worst_fold_per_hour: r4(worstF), terciles_covered: covered.length,
    terciles_won: tWon, worst_tercile_per_hour: worstT === null ? null : r4(worstT), beats_placebo: beats, placebo_usd: placebo === placebo ? +placebo.toFixed(2) : null,
    fold_usd_per_hour: foldUsdH.map(r4), tercile_usd_per_hour: terUsdH.map((v) => (v === null ? null : r4(v))), tercile_hours: terHours.map((h) => +h.toFixed(1)), why,
  };
}

export function rulebook(fz: Frozen, coins: CoinOut[], members: string[], o: { perPos?: number; cap?: number; resamples?: number } = {}): Book {
  const perPos = o.perPos ?? 500, cap = o.cap ?? 1000, maxOpen = Math.floor(cap / perPos);
  const rank = new Map(fz.cands.map((c, k) => [c.id, k]));
  const coinOf = new Map(fz.cands.map((c) => [c.id, c.a]));
  const sig: Array<{ t: number; x: number; te: number; hd: number; fb: number; rnd?: number; ter?: number; a: string; r: number }> = [];
  for (const co of coins) for (const c of co.cands ?? []) if (members.includes(c.id)) for (const [t, x, te, hd, fb, rnd, ter] of c.signals) sig.push({ t, x, te, hd, fb: fb ?? 0, rnd: rnd ?? undefined, ter: ter ?? undefined, a: coinOf.get(c.id)!, r: rank.get(c.id)! });
  sig.sort((p, q) => p.t - q.t || p.r - q.r);
  const busy = new Map<string, number>();
  const taken: typeof sig = [];
  let skippedBusy = 0, skippedCap = 0;
  for (const s of sig) {
    for (const [a, te] of busy) if (te <= s.t) busy.delete(a);
    if (busy.has(s.a)) { skippedBusy++; continue; }
    if (busy.size >= maxOpen) { skippedCap++; continue; }
    busy.set(s.a, s.te); taken.push(s);
  }
  // An unfilled maker order took its slot until cancelled; it is not a trade.
  const unfilled = taken.filter((s) => s.hd === 0).length;
  taken.splice(0, taken.length, ...taken.filter((s) => s.hd > 0));
  const seal = Date.parse(fz.seal), end = Math.max(seal + DAY, ...coins.map((c) => Date.parse(c.sealTo)));
  const hours = (end - seal) / 3_600_000, nDays = Math.max(1, Math.round((end - seal) / DAY));
  const daily = new Float64Array(nDays), byCoin: Record<string, number> = {}, months: Record<string, number> = {};
  let usd = 0, stress = 0, fStress = 0;
  for (const s of taken) {
    const v = (s.x / 1e4) * perPos, d = Math.min(nDays - 1, Math.max(0, Math.floor((s.te - seal) / DAY)));
    daily[d] += v; usd += v; stress += ((s.x - 6) / 1e4) * perPos; fStress += ((s.x - 0.5 * Math.abs(s.fb)) / 1e4) * perPos;
    byCoin[s.a] = (byCoin[s.a] ?? 0) + v;
    const mo = new Date(s.te).toISOString().slice(0, 7); months[mo] = (months[mo] ?? 0) + v;
  }
  // $ per UTC exit day over every sealed calendar day (the registry's by_day; the bootstrap below keeps its own day bins).
  const byDay: Record<string, number> = {};
  for (let t = seal; t < end; t += DAY) byDay[new Date(t).toISOString().slice(0, 10)] = 0;
  for (const s of taken) { const k = new Date(s.te).toISOString().slice(0, 10); byDay[k] = (byDay[k] ?? 0) + (s.x / 1e4) * perPos; }
  // Day-block bootstrap of the mean daily P&L (seeded: the same set gives the same bound).
  const R = o.resamples ?? 10_000, r = rng(parseInt(fz.hash.slice(0, 8), 16) || 1), means = new Float64Array(R);
  for (let b = 0; b < R; b++) { let s = 0; for (let k = 0; k < nDays; k++) s += daily[Math.floor(r() * nDays)]; means[b] = s / nDays; }
  means.sort();
  const lb90 = means[Math.floor(0.1 * R)] / 24;
  const best = Math.max(0, ...Object.values(months));
  const share = usd > 0 ? best / usd : NaN;
  const why: string[] = [];
  if (!(lb90 > 0)) why.push(`bootstrap 90% lower bound ${lb90.toFixed(3)} $/h <= 0`);
  if (!((byCoin.BTC ?? 0) > 0 && (byCoin.ETH ?? 0) > 0 && ((byCoin.SOL ?? 0) > 0 || (byCoin.XRP ?? 0) > 0))) why.push('not positive on BTC, ETH and one of SOL / XRP');
  if (!(usd > 0 && share <= 0.5)) why.push(usd > 0 ? `best month holds ${(share * 100).toFixed(0)}% of the gain` : 'no gain');
  if (!(stress > 0)) why.push('not above 0 at +3 bps per side');
  if (!(fStress > 0)) why.push('not above 0 with funding paid x1.5 and received x0.5');
  // HO-1 book hours per RV tercile: the mean over the book's coins of each coin's sealed minutes in that tercile.
  const bookCoins = coins.filter((co) => co.terMinutes && (co.cands ?? []).some((c) => members.includes(c.id)));
  const terHours = [0, 1, 2].map((k) => (bookCoins.length ? bookCoins.reduce((a, co) => a + co.terMinutes![k], 0) / 60 / bookCoins.length : 0));
  const ho1 = ho1Of(byDay, taken, terHours, perPos);
  why.push(...ho1.why);
  return {
    members, trades: taken.length, skippedBusy, skippedCap, usd: +usd.toFixed(2), usdPerHour: +(usd / hours).toFixed(4), lb90: +lb90.toFixed(4), stressUsdPerHour: +(stress / hours).toFixed(4), fundStressUsdPerHour: +(fStress / hours).toFixed(4), unfilled,
    byCoin: Object.fromEntries(Object.entries(byCoin).map(([k, v]) => [k, +v.toFixed(2)])), bestMonthShare: +share.toFixed(3), months: Object.fromEntries(Object.entries(months).sort().map(([k, v]) => [k, +v.toFixed(2)])),
    over480: taken.filter((s) => s.hd > 480).length, ho1, pass: why.length === 0, why,
    byDay: Object.fromEntries(Object.entries(byDay).map(([k, v]) => [k, +v.toFixed(4)])),
  };
}

export function blindReport(fz: Frozen, coins: CoinOut[]): { md: string; verdict: Record<string, unknown> } {
  const rep = coins.flatMap((c) => c.replication.map((r) => ({ ...r, a: c.asset })));
  const failedRep = rep.filter((r) => !r.ok);
  const per = fz.cands.map((c) => {
    const co = coins.find((x) => x.asset === c.a), s = co?.cands?.find((x) => x.id === c.id)?.sealed;
    const why: string[] = [];
    if (!s) why.push('not read (replication failed or no sealed data)');
    else {
      if (!(s.n >= 20)) why.push(`${s.n} sealed trades`);
      if (!(s.mean > 0)) why.push(`net ${s.mean} bps`);
      if (!(s.exc > 0)) why.push(`excess ${s.exc} bps`);
      if (!(s.t >= 1)) why.push(`net t ${s.t}`);
      if (!(s.tExc >= 1)) why.push(`excess t ${s.tExc}`);
    }
    return { c, s, pass: why.length === 0, why };
  });
  const all = rulebook(fz, coins, fz.cands.map((c) => c.id));
  const passers = per.filter((p) => p.pass).map((p) => p.c.id);
  const chosen = passers.length ? rulebook(fz, coins, passers) : undefined;
  // Every frozen coin must have been read (its job may have crashed, failed replication or had under a day after the
  // seal): a rulebook judged on part of the set fails closed.
  const unread = [...new Set(fz.cands.map((c) => c.a))].filter((a) => !coins.find((x) => x.asset === a)?.cands);
  for (const b of [all, chosen]) if (b && unread.length) { b.pass = false; b.why.unshift(`not read on ${unread.join(', ')}`); }
  const span = coins.length ? `${fz.seal.slice(0, 10)} .. ${coins.map((c) => c.sealTo.slice(0, 10)).sort().pop()}` : 'no coin';
  const fmtB = (b: Book) => `${b.trades} trades (skipped: coin busy ${b.skippedBusy}, cap full ${b.skippedCap}); $${b.usd} = **$${b.usdPerHour}/h** per $1k (bootstrap 90% lower bound $${b.lb90}/h; at +3 bps per side $${b.stressUsdPerHour}/h; funding paid x1.5, received x0.5 $${b.fundStressUsdPerHour}/h; ${b.unfilled} maker orders unfilled); by coin ${Object.entries(b.byCoin).map(([k, v]) => `${k} $${v}`).join(', ') || 'none'}; best month ${b.bestMonthShare}; held > 480 min ${b.over480}; HO-1 over ${b.ho1.days} days: folds won ${b.ho1.folds_won}/${b.ho1.folds} ($/h ${b.ho1.fold_usd_per_hour.join(', ')}), RV terciles LOW/MID/HIGH $/h ${b.ho1.tercile_usd_per_hour.map((v) => v ?? 'n/a').join(' / ')} (${b.ho1.tercile_hours.join(' / ')} h), placebo $${b.ho1.placebo_usd ?? 'n/a'}. ${b.pass ? '**PASS**' : `fails: ${b.why.join('; ')}`}${b.pass && b.usdPerHour < 4.5 ? ' (below the $4.50/h target)' : ''}`;
  const md = [
    `## Perp TA blind test: frozen set ${fz.hash} from sweep run ${fz.run} (${fz.cands.length} of ${fz.passing} passing candidates), sealed ${span}`,
    '',
    failedRep.length ? `**Replication failed** for ${failedRep.map((r) => `${r.id} (${r.a}: n ${r.n} vs ${r.frozenN}, mean ${r.mean} vs ${r.frozenMean})`).join(', ')}: those coins' sealed blocks were not read.` : unread.length ? `**Not read** on ${unread.join(', ')} (no output, or under a day after the seal): the rulebooks fail closed.` : `Every candidate replicated its discovery trades exactly before the sealed block was read.`,
    '',
    `**Rulebook, every frozen candidate** (the judged one): ${fmtB(all)}`,
    '',
    chosen ? `Rulebook of the ${passers.length} candidates that pass one by one (chosen on the sealed block, optimistic): ${fmtB(chosen)}` : 'No candidate passes on its own.',
    '',
    '| id | coin | rule | mode | exit | side | condition | disc n | disc bps | disc exc t | sealed n | sealed bps | sealed exc | net t | exc t | per day | $/h per $1k | hold min | verdict |',
    '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|',
    ...per.map(({ c, s, pass, why }) => `| ${c.id} | ${c.a} | ${c.rule} | ${c.mode} | ${c.pol} | ${c.side} | ${c.cond} | ${c.disc.n} | ${c.disc.mean} | ${c.disc.tExc} | ${s?.n ?? ''} | ${s?.mean ?? ''} | ${s?.exc ?? ''} | ${s?.t ?? ''} | ${s?.tExc ?? ''} | ${s?.perDay ?? ''} | ${s?.usdPerHourPer1k ?? ''} | ${s?.holdMin ?? ''} | ${pass ? 'pass' : why.join('; ')} |`),
    '',
    `Rulebook months (every candidate): ${Object.entries(all.months).map(([k, v]) => `${k} $${v}`).join(', ') || 'none'}`,
    ...coins.flatMap((c) => c.notes.filter((n) => !n.startsWith('modules:')).map((n) => `- ${c.asset}: ${n}`)),
  ].join('\n');
  return { md, verdict: { hash: fz.hash, run: fz.run, candidates: fz.cands.length, replicationFailed: failedRep.length, unread, perCandidatePass: passers.length, rulebook: all, passersRulebook: chosen ?? null } };
}

// ---------------------------------------------------------------------------------------------------------------

function arg(k: string, d?: string): string | undefined { const i = process.argv.indexOf(`--${k}`); return i >= 0 && process.argv[i + 1] !== undefined && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : d; }

async function main(): Promise<void> {
  const mode = process.argv[2];
  const log = (m: string) => console.log(`[perp-ta-blind] ${m}`);
  if (mode === 'freeze') {
    const cands = JSON.parse(zlib.gunzipSync(fs.readFileSync(arg('candidates')!)).toString()) as Candidate[];
    const costs: Costs = { takerBps: +arg('taker', String(KALSHI_COSTS.takerBps))!, makerBps: +arg('maker', String(KALSHI_COSTS.makerBps))!, halfSpreadBps: +arg('half-spread', String(KALSHI_COSTS.halfSpreadBps))!, ttBps: +arg('trade-through', String(KALSHI_COSTS.ttBps))! };
    const fz = freeze(cands, { run: arg('run', 'local')!, sha: arg('sha', '')!, seal: `${arg('seal', '2025-07-01')}T00:00:00.000Z`, validFrom: `${arg('valid-from', '2024-01-01')}T00:00:00.000Z`, costs });
    fs.writeFileSync(arg('out')!, JSON.stringify(fz, null, 1));
    log(`frozen set ${fz.hash}: ${fz.cands.length} of ${fz.passing} passing candidates (${[...new Set(fz.cands.map((c) => c.a))].join(', ') || 'none'})`);
    return;
  }
  if (mode === 'coin') {
    const fz = JSON.parse(fs.readFileSync(arg('frozen')!, 'utf8')) as Frozen;
    const g = readGrid(arg('data')!);
    const modules = arg('modules', 'true') === 'false' ? false as const : { history: arg('history'), forecasts: arg('forecasts'), cacheDir: arg('module-cache') };
    const end = arg('end');
    if (end !== undefined && !Number.isFinite(Date.parse(end))) throw new Error(`--end ${end}: not a time`);
    const hist = arg('history'), spot = hist ? await spotFromCsv(path.join(hist, 'binance-1m', g.asset, '1m.csv'), g.t0, g.n) : undefined;
    const r = blindCoin(g, fz, { modules, log, endMs: end !== undefined ? Date.parse(end) : undefined, spot });
    const file = arg('out')!;
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify(r));
    log(`${g.asset}: wrote ${file} (${r.cands?.length ?? 0} candidates read on the sealed block)`);
    if (r.replication.some((x) => !x.ok)) process.exitCode = 2;
    return;
  }
  if (mode === 'report') {
    const fz = JSON.parse(fs.readFileSync(arg('frozen')!, 'utf8')) as Frozen;
    const dir = arg('in')!, outDir = arg('out', 'blind-report')!;
    const coins = fs.readdirSync(dir, { recursive: true }).map(String).filter((f) => /blind-[A-Z0-9]+\.json$/.test(f)).map((f) => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')) as CoinOut).filter((c) => c.hash === fz.hash);
    const r = blindReport(fz, coins);
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(path.join(outDir, 'summary.md'), r.md + '\n');
    fs.writeFileSync(path.join(outDir, 'verdict.json'), JSON.stringify(r.verdict, null, 1));
    const now = new Date();
    const run = process.env.GITHUB_RUN_ID ?? 'local', sha = process.env.GITHUB_SHA ?? 'local';
    const raw = { thread: 'perp-ta-rulebook', kind: 'blind-test', run, sha, at_utc: now.toISOString(), at_eastern: now.toLocaleString('en-US', { timeZone: 'America/New_York', hour12: false }), frozen_from_run: fz.run, set_hash: fz.hash, n_candidates: fz.cands.length, verdict: r.verdict, doge_excluded: true, prereg: '/mnt/project-files/perp-ta/preregistration.md' };
    // Registry v1 rows: the whole frozen set's rulebook and, if any candidate passed alone, the passers' rulebook, each
    // with its sealed-block $ per day (one position per coin, the rulebook's size), against the sweep run's control.
    // The rulebook is judged against flat (no position: $0 every day), so the paired control is a flat book over the same
    // sealed days. A blind test whose replication failed, or that read no coin, has no daily P&L (counted, not scored).
    const v = r.verdict as { rulebook: Book; passersRulebook: Book | null; replicationFailed: number; unread: string[] };
    const read = v.replicationFailed === 0 && v.unread.length === 0 && coins.some((c) => (c.cands?.length ?? 0) > 0);
    const dayOf = (b: Book) => (read ? b.byDay : {});
    // The registry's HO-1 block (research/registry.py heldout); the rulebook's own fold and tercile detail stays in raw.
    // Only the judged rulebook (every frozen candidate) is held out: the passers' rulebook is chosen on the sealed block,
    // so its row has held_out false and no HO-1 block.
    const hoOf = (b: Book) => {
      if (!read || !b.ho1) return undefined;
      const { fold_usd_per_hour: _f, tercile_usd_per_hour: _t, tercile_hours: _h, placebo_usd: _p, why: _w, worst_tercile_per_hour: wt, ...h } = b.ho1;
      return { ...h, ...(wt === null ? {} : { worst_tercile_per_hour: wt }) };
    };
    const flat = regRow({ arm: `blind:${fz.hash.slice(0, 12)}:flat`, role: 'control', codeSha: sha, codeEpoch: `perp-ta blind of run ${fz.run}`, byDay: Object.fromEntries(Object.keys(dayOf(v.rulebook)).map((d) => [d, 0])), ref: runRef(run), at: now, heldOut: true, verdict: 'flat: no position (the rulebook benchmark)' });
    const rows = [
      flat,
      regRow({ arm: `blind:${fz.hash.slice(0, 12)}:all`, role: 'candidate', control: flat.trial_id, codeSha: sha, codeEpoch: `perp-ta blind of run ${fz.run}`, byDay: dayOf(v.rulebook), fills: v.rulebook.trades, ref: runRef(run), at: now, heldOut: true, heldout: hoOf(v.rulebook), verdict: !read ? 'not read (replication failed or a coin not read)' : v.rulebook.pass ? 'PASS' : v.rulebook.why.join('; '), raw }),
      ...(v.passersRulebook ? [regRow({ arm: `blind:${fz.hash.slice(0, 12)}:passers`, role: 'candidate', control: flat.trial_id, codeSha: sha, codeEpoch: `perp-ta blind of run ${fz.run}`, byDay: dayOf(v.passersRulebook), fills: v.passersRulebook.trades, ref: runRef(run), at: now, verdict: !read ? 'not read (replication failed or a coin not read)' : v.passersRulebook.pass ? 'PASS' : v.passersRulebook.why.join('; '), raw: { kind: 'blind-test-passers', set_hash: fz.hash } })] : []),
    ];
    fs.writeFileSync(path.join(outDir, 'registry.jsonl'), rows.map((x) => JSON.stringify(x)).join('\n') + '\n');
    console.log(r.md);
    return;
  }
  console.log('usage: perpTaBlind.ts freeze|coin|report (see the header)');
  process.exitCode = 1;
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) main().catch((e) => { console.error(e); process.exitCode = 1; });
