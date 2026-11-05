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
// ETH and one of SOL / XRP, no month holding more than half the gain, and still above 0 at +3 bps per side.

import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import crypto from 'crypto';
import {
  readGrid, buildPrims, triggers, stateAt, outcomes, atrUnit, conditions, folds, POLICIES, CONDS, NZ, KALSHI_COSTS,
  type Grid, type Prim, type Costs, type Candidate,
} from './perpTaSweep';
import { modulePrims, MODULE_CONDS } from './perpTaModules';

const MIN = 60_000;
const DAY = 86_400_000;
const fin = Number.isFinite;

export interface FrozenCand { id: string; a: string; group: string; rule: string; mode: 'follow' | 'fade'; pol: string; side: 'long' | 'short'; cond: string; disc: { n: number; mean: number; t: number; exc: number; tExc: number } }
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
  const fz = pick.map((c, k): FrozenCand => ({
    id: `c${k + 1}`, a: c.a, group: c.group, rule: c.rule, mode: c.mode, pol: c.pol, side: c.side, cond: c.cond,
    disc: { n: c.disc.n, mean: c.disc.mean, t: c.disc.t, exc: c.disc.exc, tExc: c.disc.tExc },
  }));
  const key = JSON.stringify({ seal: o.seal, validFrom: o.validFrom, costs: o.costs, cands: fz.map(({ a, rule, mode, pol, side, cond }) => ({ a, rule, mode, pol, side, cond })) });
  return { schema: 'perpta-frozen1', run: o.run, sha: o.sha, at: new Date().toISOString(), seal: o.seal, validFrom: o.validFrom, costs: o.costs, passing: pass.length, hash: crypto.createHash('sha1').update(key).digest('hex').slice(0, 16), cands: fz };
}

export interface SealedStats { n: number; mean: number; t: number; exc: number; tExc: number; hit: number; holdMin: number; over480: number; perDay: number; usdPerHourPer1k: number; stress6: number }
export interface CoinOut {
  schema: 'perpta-blind1'; asset: string; hash: string; sealFrom: string; sealTo: string; sealDays: number;
  replication: Array<{ id: string; ok: boolean; n: number; frozenN: number; mean: number; frozenMean: number }>;
  /** Only when every candidate of the coin replicated: the sealed stats and the rulebook signals (decision ts, net bps,
   *  exit ts, hold minutes) of each candidate. */
  cands?: Array<{ id: string; sealed: SealedStats; signals: Array<[number, number, number, number]> }>;
  notes: string[];
}

function resolveRule(rule: string, byId: Map<string, Prim>): [Prim, Prim | undefined] | undefined {
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

/** One coin: replicate every frozen candidate's discovery trades, then (only if all match) its sealed trades. */
export function blindCoin(g: Grid, fz: Frozen, o: { modules?: false | { history?: string; forecasts?: string; cacheDir?: string }; log?: (m: string) => void }): CoinOut {
  const log = o.log ?? console.log;
  const cands = fz.cands.filter((c) => c.a === g.asset);
  const seal = Date.parse(fz.seal), validFrom = Date.parse(fz.validFrom);
  const nFull = g.n, iSeal = Math.round((seal - g.t0) / MIN);
  const res: CoinOut = { schema: 'perpta-blind1', asset: g.asset, hash: fz.hash, sealFrom: fz.seal, sealTo: new Date(g.t0 + nFull * MIN).toISOString(), sealDays: +(Math.max(0, nFull - iSeal) / 1440).toFixed(2), replication: [], notes: [] };
  if (!cands.length) { res.notes.push('no frozen candidate on this coin'); res.cands = []; return res; }
  if (iSeal >= nFull - 1440) { res.notes.push('less than a day of history after the seal'); return res; }
  const quiet = () => undefined;
  const prims = buildPrims(g, nFull, quiet);
  let byId = new Map(prims.map((p) => [p.id, p]));
  const needMod = cands.some((c) => !resolveRule(c.rule, byId)) || cands.some((c) => MODULE_CONDS.includes(c.cond));
  const mod = needMod && o.modules !== false ? modulePrims(g, nFull, { ...(o.modules || {}), discoveryEnd: validFrom, log }) : undefined;
  if (mod) { prims.push(...mod.prims); byId = new Map(prims.map((p) => [p.id, p])); res.notes.push(...mod.notes.map((n) => `modules: ${n}`)); }
  const unit = atrUnit(g, nFull), out = outcomes(g, nFull, unit, fz.costs), cond = conditions(g, nFull, mod), fo = folds(g, nFull, validFrom);
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
  type Tr = { i: number; x: number; e: number; vb: number; ex: number; hd: number };
  const plans = cands.map((c) => {
    const rr = resolveRule(c.rule, byId);
    if (!rr) return undefined;
    const [tp, fp] = rr, tr = triggers(tp, g.c.valid, nFull);
    const idx: number[] = [], dir: number[] = [];
    for (let q = 0; q < tr.idx.length; q++) { const i = tr.idx[q]; if (!fp || stateAt(fp, i) === tr.dir[q]) { idx.push(i); dir.push(tr.dir[q]); } }
    return { c, idx, dir, mode: c.mode === 'fade' ? 1 : 0, p: POLICIES.findIndex((x) => x.id === c.pol), side: c.side === 'short' ? 1 : 0, ci: CONDS.indexOf(c.cond) };
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
      if (x !== x) continue;
      const ex = out.exit[k][i];
      nextFree = ex;
      if (i < from || i >= to) continue;
      if (purge && fo.of[ex] !== fo.of[i]) continue;
      if ((sd > 0 ? 0 : 1) !== pl.side || !inCond(i, pl.ci)) continue;
      const b = baseline(k, pl.ci), mo = monthOf[i];
      outT.push({ i, x, e: x - b.m[mo], vb: b.v[mo], ex, hd: out.hold[k][i] });
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
  res.cands = cands.map((c, k) => {
    const pl = plans[k]!;
    const tr = cellTrades(pl, iSeal, nFull, false);
    const s = stats(tr.map((t) => t.x), tr.map((t) => t.e), tr.map((t) => t.vb));
    const sum = tr.reduce((a, t) => a + t.x, 0);
    const sealed: SealedStats = {
      n: s.n, mean: +s.mean.toFixed(2), t: +s.t.toFixed(3), exc: +s.exc.toFixed(2), tExc: +s.tExc.toFixed(3), hit: +s.hit.toFixed(3),
      holdMin: tr.length ? +(tr.reduce((a, t) => a + t.hd, 0) / tr.length).toFixed(1) : 0, over480: tr.filter((t) => t.hd > 480).length,
      perDay: +(s.n / (hours / 24)).toFixed(3), usdPerHourPer1k: +((sum / 1e4) * 1000 / hours).toFixed(4), stress6: +(s.mean - 6).toFixed(2),
    };
    const signals: Array<[number, number, number, number]> = [];
    for (let q = 0; q < pl.idx.length; q++) {
      const i = pl.idx[q];
      if (i < iSeal || !g.c.valid[i] || i + 1 >= nFull || !g.c.valid[i + 1]) continue;
      const sd = pl.dir[q];
      if ((sd > 0 ? 0 : 1) !== pl.side || !inCond(i, pl.ci)) continue;
      const td = pl.mode === 0 ? sd : -sd, kk = pl.p * 2 + (td > 0 ? 0 : 1), x = out.net[kk][i];
      if (x !== x) continue;
      signals.push([g.t0 + i * MIN, +x.toFixed(2), g.t0 + out.exit[kk][i] * MIN, out.hold[kk][i]]);
    }
    return { id: c.id, sealed, signals };
  });
  return res;
}

// ---------------------------------------------------------------------------------------------------------------
// The report: per-candidate verdicts and the rulebook.

function rng(seed: number): () => number { let a = seed >>> 0; return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

export interface Book { members: string[]; trades: number; skippedBusy: number; skippedCap: number; usd: number; usdPerHour: number; lb90: number; stressUsdPerHour: number; byCoin: Record<string, number>; bestMonthShare: number; months: Record<string, number>; over480: number; pass: boolean; why: string[] }

export function rulebook(fz: Frozen, coins: CoinOut[], members: string[], o: { perPos?: number; cap?: number; resamples?: number } = {}): Book {
  const perPos = o.perPos ?? 500, cap = o.cap ?? 1000, maxOpen = Math.floor(cap / perPos);
  const rank = new Map(fz.cands.map((c, k) => [c.id, k]));
  const coinOf = new Map(fz.cands.map((c) => [c.id, c.a]));
  const sig: Array<{ t: number; x: number; te: number; hd: number; a: string; r: number }> = [];
  for (const co of coins) for (const c of co.cands ?? []) if (members.includes(c.id)) for (const [t, x, te, hd] of c.signals) sig.push({ t, x, te, hd, a: coinOf.get(c.id)!, r: rank.get(c.id)! });
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
  const seal = Date.parse(fz.seal), end = Math.max(seal + DAY, ...coins.map((c) => Date.parse(c.sealTo)));
  const hours = (end - seal) / 3_600_000, nDays = Math.max(1, Math.round((end - seal) / DAY));
  const daily = new Float64Array(nDays), byCoin: Record<string, number> = {}, months: Record<string, number> = {};
  let usd = 0, stress = 0;
  for (const s of taken) {
    const v = (s.x / 1e4) * perPos, d = Math.min(nDays - 1, Math.max(0, Math.floor((s.te - seal) / DAY)));
    daily[d] += v; usd += v; stress += ((s.x - 6) / 1e4) * perPos;
    byCoin[s.a] = (byCoin[s.a] ?? 0) + v;
    const mo = new Date(s.te).toISOString().slice(0, 7); months[mo] = (months[mo] ?? 0) + v;
  }
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
  return {
    members, trades: taken.length, skippedBusy, skippedCap, usd: +usd.toFixed(2), usdPerHour: +(usd / hours).toFixed(4), lb90: +lb90.toFixed(4), stressUsdPerHour: +(stress / hours).toFixed(4),
    byCoin: Object.fromEntries(Object.entries(byCoin).map(([k, v]) => [k, +v.toFixed(2)])), bestMonthShare: +share.toFixed(3), months: Object.fromEntries(Object.entries(months).sort().map(([k, v]) => [k, +v.toFixed(2)])),
    over480: taken.filter((s) => s.hd > 480).length, pass: why.length === 0, why,
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
  const span = coins.length ? `${fz.seal.slice(0, 10)} .. ${coins.map((c) => c.sealTo.slice(0, 10)).sort().pop()}` : 'no coin';
  const fmtB = (b: Book) => `${b.trades} trades (skipped: coin busy ${b.skippedBusy}, cap full ${b.skippedCap}); $${b.usd} = **$${b.usdPerHour}/h** per $1k (bootstrap 90% lower bound $${b.lb90}/h; at +3 bps per side $${b.stressUsdPerHour}/h); by coin ${Object.entries(b.byCoin).map(([k, v]) => `${k} $${v}`).join(', ') || 'none'}; best month ${b.bestMonthShare}; held > 480 min ${b.over480}. ${b.pass ? '**PASS**' : `fails: ${b.why.join('; ')}`}${b.pass && b.usdPerHour < 4.5 ? ' (below the $4.50/h target)' : ''}`;
  const md = [
    `## Perp TA blind test: frozen set ${fz.hash} from sweep run ${fz.run} (${fz.cands.length} of ${fz.passing} passing candidates), sealed ${span}`,
    '',
    failedRep.length ? `**Replication failed** for ${failedRep.map((r) => `${r.id} (${r.a}: n ${r.n} vs ${r.frozenN}, mean ${r.mean} vs ${r.frozenMean})`).join(', ')}: those coins' sealed blocks were not read.` : `Every candidate replicated its discovery trades exactly before the sealed block was read.`,
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
  return { md, verdict: { hash: fz.hash, run: fz.run, candidates: fz.cands.length, replicationFailed: failedRep.length, perCandidatePass: passers.length, rulebook: all, passersRulebook: chosen ?? null } };
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
    const r = blindCoin(g, fz, { modules, log });
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
    const row = { thread: 'perp-ta-rulebook', kind: 'blind-test', run: process.env.GITHUB_RUN_ID ?? 'local', sha: process.env.GITHUB_SHA ?? '', at_utc: now.toISOString(), at_eastern: now.toLocaleString('en-US', { timeZone: 'America/New_York', hour12: false }), frozen_from_run: fz.run, set_hash: fz.hash, n_candidates: fz.cands.length, verdict: r.verdict, doge_excluded: true, prereg: '/mnt/project-files/perp-ta/preregistration.md' };
    fs.writeFileSync(path.join(outDir, 'registry.jsonl'), JSON.stringify(row) + '\n');
    console.log(r.md);
    return;
  }
  console.log('usage: perpTaBlind.ts freeze|coin|report (see the header)');
  process.exitCode = 1;
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) main().catch((e) => { console.error(e); process.exitCode = 1; });
