// Perp TA round 4, PTA-H1-decay-v2: the institutional thread's diagnostic of the round 1-3 losers (thread "Build a TA
// rulebook for perpetuals"). Pre-registered in /mnt/project-files/perp-ta/preregistration.md, "Round 4", subsection
// "PTA-H1-decay-v2" (Nov 5 2026, 7:39 PM EST / Nov 6 00:39 UTC). Validation data only: every table stops at the seal
// (2025-07-01), as the sweep's did, so the sealed block and the lockboxes are never read.
//
// Hypothesis: the spot-TA triggers carry a small real excess at entry that is mostly gone within 15 minutes and does not
// grow with the exit horizon. Per round (1 primary: taker entries; 2 and 3 secondary), the 40 strongest non-forecast groups
// as that round's report ranks them (discovery excess t), each group's representative cell, are walked again exactly as the
// sweep walked them (the discovery n and mean must replicate), with the entry moved d = 0, 1, 5, 15, 60 minutes later (the
// exit rules unchanged; the condition is the one at the signal's minute). Excess = net - the random-entry baseline of the
// entry's month and condition with the same exit and side (the sweep's), split into funding received and the rest. The
// placebo: the same triggers shifted by the sweep's 60 whole-day shifts, at every delay. SEs: day-block bootstrap (5-day
// circular blocks, B = 2000) over the validation days, by the signal's day (so delays are paired).
//
//   coin    node --import tsx research/perpTaDecay.ts coin --data data/perp-ta/BTC.bin --round 1:42053618890:in/r1
//           [--round 2:...] --out out/decay-BTC.json [--history data/hist-BTC --forecasts data/server-hist --module-cache dir]
//           (in/r<k>/candidates.json.gz: that run's report candidates; in/r<k>/<A>.header.json: the first line of its
//           <A>.jsonl.gz, with the coin's costs and policies)
//   report  node --import tsx research/perpTaDecay.ts report --in out --out report

import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import {
  readGrid, buildPrims, triggers, stateAt, outcomes, atrUnit, conditions, folds, CONDS, NZ, POLICIES_R1, POLICIES_ALL,
  type Grid, type Costs, type Candidate, type Policy, type Prim,
} from './perpTaSweep';
import { modulePrims } from './perpTaModules';
import { resolveRule } from './perpTaBlind';
import { regRow, runRef, type RegRow } from './perpTaRegistry';

const MIN = 60_000;
const DAY = 86_400_000;
const MPD = 1440;
const fin = Number.isFinite;

export const DECAY = {
  id: 'PTA-H1-decay-v2', delays: [0, 1, 5, 15, 60], top: 40, shifts: 60, bootBlock: 5, boot: 2000,
  seal: Date.UTC(2025, 6, 1), validFrom: Date.UTC(2024, 0, 1),
  /** Walks other than the replicating one (d = 0, no shift) start this long before the validation block (holds are at
   *  most 7 days, so the walk's one-position-at-a-time state is settled by then). */
  warmupDays: 14,
};

export interface RoundIn { round: number; run: string; cands: Candidate[]; header: { costs: Costs; policies?: Policy[]; seal?: string; validFrom?: string } }

/** The round's top groups as its report ranked them: non-forecast representatives by discovery excess t, all coins. */
export function topGroups(cands: Candidate[], top = DECAY.top): Candidate[] {
  return cands.filter((c) => !c.diagnostic).sort((a, b) => b.disc.tExc - a.disc.tExc).slice(0, top);
}

export interface DelaySeries { n: number[]; exc: number[]; fund: number[]; net: number[] }
export interface DecayCell {
  round: number; run: string; key: string; a: string; rule: string; mode: string; pol: string; side: string; cond: string; maxHold: number; entry: string;
  rank: number; discStored: { n: number; mean: number; tExc: number }; discReplicated: { n: number; mean: number }; replicated: boolean;
  valStored?: { n: number; mean: number; exc: number }; notes: string[];
  /** Per delay (DECAY.delays order), per validation day (the signal's day): trades, sum of excess bps, of excess funding
   *  received (bps, vs the random entries'), of net bps. */
  arm: DelaySeries[];
  /** The placebo per delay: the same sums over all whole-day shifts together, and the shift count. */
  placebo: DelaySeries[]; shifts: number;
}
export interface DecayCoin { schema: 'perpta-decay1'; asset: string; dayValid: string; days: number; cells: DecayCell[]; notes: string[] }

const keyOf = (c: { a: string; rule: string; mode: string; pol: string; side: string; cond: string }) => `${c.a}|${c.rule}|${c.mode}|${c.pol}|${c.side}|${c.cond}`;

export function decayCoin(g: Grid, rounds: RoundIn[], o: { modules?: false | { history?: string; forecasts?: string; cacheDir?: string }; log?: (m: string) => void; prims?: Prim[]; cond?: Uint8Array } = {}): DecayCoin {
  const log = o.log ?? console.log, quiet = () => undefined;
  const seal = DECAY.seal, validFrom = DECAY.validFrom;
  for (const r of rounds) {
    const s = r.header.seal ? Date.parse(r.header.seal) : seal, v = r.header.validFrom ? Date.parse(r.header.validFrom) : validFrom;
    if (s !== seal || v !== validFrom) throw new Error(`round ${r.round}: swept with seal ${r.header.seal} / validation ${r.header.validFrom}, not the pre-registered blocks`);
  }
  const nMax = Math.min(g.n, Math.max(0, Math.round((seal - g.t0) / MIN))); // the sweep's own: nothing at or after the seal
  let prims = o.prims, cond = o.cond, mod;
  if (!prims) {
    prims = buildPrims(g, nMax, quiet);
    mod = o.modules === false ? undefined : modulePrims(g, nMax, { ...(o.modules || {}), discoveryEnd: validFrom, log });
    if (mod) prims.push(...mod.prims);
  }
  if (!cond) cond = conditions(g, nMax, mod);
  const byId = new Map(prims.map((p) => [p.id, p]));
  const fo = folds(g, nMax, validFrom);
  const discEnd = fo.discovery < fo.starts.length ? fo.starts[fo.discovery] : nMax;
  const inCond = (i: number, c: number) => { if (c === 0) return true; for (let z = 0; z < NZ; z++) if (cond![i * NZ + z] === c) return true; return false; };
  const dayValid = Math.floor(validFrom / DAY), days = Math.max(0, Math.floor((g.t0 + nMax * MIN) / DAY) - dayValid);
  const monthOf = new Int16Array(nMax), y0 = new Date(g.t0).getUTCFullYear(), m0 = new Date(g.t0).getUTCMonth();
  for (let i = 0; i < nMax; i++) { const d = new Date(g.t0 + i * MIN); monthOf[i] = (d.getUTCFullYear() - y0) * 12 + d.getUTCMonth() - m0; }
  const NM = nMax ? monthOf[nMax - 1] + 1 : 0;
  const nDays = Math.floor(nMax / MPD);
  const shifts = Array.from({ length: DECAY.shifts }, (_, k) => Math.round(7 + (k * (nDays - 14)) / Math.max(1, DECAY.shifts - 1)) * MPD).filter((s) => s > 0 && s < nMax);
  const warm = Math.max(0, discEnd - DECAY.warmupDays * MPD);
  const unit = atrUnit(g, nMax);
  const cells: DecayCell[] = [], notes: string[] = [];
  const D = DECAY.delays;
  const blank = (): DelaySeries => ({ n: new Array(days).fill(0), exc: new Array(days).fill(0), fund: new Array(days).fill(0), net: new Array(days).fill(0) });

  for (const r of rounds) {
    const ranked = topGroups(r.cands);
    const mine = ranked.map((c, rank) => ({ c, rank })).filter((x) => x.c.a === g.asset);
    if (!mine.length) { notes.push(`round ${r.round}: none of its top ${DECAY.top} groups is on ${g.asset}`); continue; }
    const polDefs: Policy[] = r.header.policies?.length ? r.header.policies : r.round === 1 ? POLICIES_R1 : [];
    const polOf = (c: Candidate) => c.policyDef ?? polDefs.find((p) => p.id === c.pol) ?? (r.round === 1 ? POLICIES_ALL.find((p) => p.id === c.pol && !p.entry) : undefined);
    const used: Policy[] = [];
    for (const { c } of mine) { const p = polOf(c); if (p && !used.some((u) => u.id === p.id)) used.push(p); }
    const costs = r.header.costs;
    const t = Date.now();
    const out = outcomes(g, nMax, unit, costs, used);
    log(`${g.asset} round ${r.round}: ${mine.length} cells, ${used.length} exits, outcome tables in ${((Date.now() - t) / 1000).toFixed(0)} s`);
    // The random-entry baselines (net and funding paid) the sweep used, for the (exit, direction, condition) pairs needed.
    const baseOf = new Map<string, { net: Float64Array; fund: Float64Array }>();
    const fundPaid = (kk: number, td: number, i: number) => { const ex = out.exit[kk][i], hd = out.hold[kk][i]; return td * (out.cum[ex] - out.cum[ex - hd + 1]) * 1e4; };
    const baseline = (kk: number, td: number, ci: number) => {
      const k = `${kk}|${ci}`;
      let b = baseOf.get(k);
      if (b) return b;
      const s = new Float64Array(NM), f = new Float64Array(NM), n = new Float64Array(NM), nt = out.net[kk];
      for (let i = 0; i < nMax; i++) { const x = nt[i]; if (x !== x || !inCond(i, ci)) continue; const mo = monthOf[i]; s[mo] += x; f[mo] += fundPaid(kk, td, i); n[mo]++; }
      for (let m = 0; m < NM; m++) { s[m] = n[m] ? s[m] / n[m] : 0; f[m] = n[m] ? f[m] / n[m] : 0; }
      b = { net: s, fund: f }; baseOf.set(k, b); return b;
    };
    // One walk per (rule, mode, exit), delay and shift serves every cell that shares it (as the sweep's and the study's).
    const groups = new Map<string, Array<{ c: Candidate; rank: number }>>();
    for (const x of mine) { const k = `${x.c.rule}\u0001${x.c.mode}\u0001${x.c.pol}`; (groups.get(k) ?? groups.set(k, []).get(k)!).push(x); }
    for (const [gk, xs] of groups) {
      const [rule, mode, pol] = gk.split('\u0001');
      const rr = resolveRule(rule, byId), p = used.findIndex((u) => u.id === pol);
      const W = xs.map(({ c, rank }) => {
        const pd = polOf(c);
        const cell: DecayCell = {
          round: r.round, run: r.run, key: keyOf(c), a: c.a, rule: c.rule, mode: c.mode, pol: c.pol, side: c.side, cond: c.cond, maxHold: pd?.max ?? NaN, entry: pd?.entry ? `${pd.entry.kind}` : 'taker',
          rank, discStored: { n: c.disc.n, mean: c.disc.mean, tExc: c.disc.tExc }, discReplicated: { n: 0, mean: NaN }, replicated: false,
          valStored: c.val ? { n: c.val.n, mean: +c.val.mean.toFixed(2), exc: +c.val.exc.toFixed(2) } : undefined, notes: [],
          arm: D.map(blank), placebo: D.map(blank), shifts: 0,
        };
        cells.push(cell);
        return { cell, side: c.side === 'short' ? 1 : 0, ci: CONDS.indexOf(c.cond), dn: 0, ds: 0 };
      });
      if (!rr || p < 0) { for (const w of W) w.cell.notes.push(!rr ? `rule ${rule} not found` : `exit ${pol} not found`); continue; }
      const [tp, fp] = rr, tr = triggers(tp, g.c.valid, nMax);
      // The filtered entries, at the signal's own minute (the sweep's entriesOf).
      const idx = new Int32Array(tr.idx.length), dir = new Int8Array(tr.idx.length);
      let L = 0;
      for (let q = 0; q < tr.idx.length; q++) { const i = tr.idx[q]; if (!fp || stateAt(fp, i) === tr.dir[q]) { idx[L] = i; dir[L] = tr.dir[q]; L++; } }
      const mo = mode === 'fade' ? 1 : 0;
      for (const w of W) if (w.ci < 0) w.cell.notes.push(`condition ${w.cell.cond} not found`);
      const walk = (d: number, shift: number, into: 'arm' | 'placebo', di: number, from: number) => {
        let nextFree = 0, start = 0;
        if (shift) { const cut = nMax - shift; while (start < L && idx[start] < cut) start++; }
        for (let q0 = 0; q0 < L; q0++) {
          const q = shift ? (start + q0) % L : q0;
          let i0 = idx[q];
          if (shift) { i0 += shift; if (i0 >= nMax) i0 -= nMax; }
          if (i0 < from) continue;
          const i = i0 + d;
          if (i >= nMax) continue;
          if (i < nextFree) continue;
          if (!g.c.valid[i] || i + 1 >= nMax || !g.c.valid[i + 1]) continue;
          const sd = dir[q], td = mo === 0 ? sd : -sd, kk = p * 2 + (td > 0 ? 0 : 1);
          const x = out.net[kk][i];
          if (x !== x) { const c = out.exit[kk][i]; if (c > nextFree) nextFree = c; continue; } // an unfilled maker order rested
          const ex = out.exit[kk][i];
          nextFree = ex;
          if (fo.of[ex] !== fo.of[i]) continue; // purged as in the sweep
          const side = sd > 0 ? 0 : 1, day = Math.floor((g.t0 + i0 * MIN) / DAY) - dayValid;
          for (const w of W) {
            if (w.side !== side || w.ci < 0 || !inCond(i0, w.ci)) continue;
            if (into === 'arm' && d === 0 && i < discEnd) { w.dn++; w.ds += x; }
            if (i0 < discEnd || day < 0 || day >= days) continue;
            const b = baseline(kk, td, w.ci), m = monthOf[i], fb = fundPaid(kk, td, i);
            const s = w.cell[into][di];
            s.n[day]++; s.exc[day] += x - b.net[m]; s.fund[day] += -(fb - b.fund[m]); s.net[day] += x;
          }
        }
      };
      for (let di = 0; di < D.length; di++) {
        walk(D[di], 0, 'arm', di, D[di] === 0 ? 0 : warm);
        for (const s of shifts) walk(D[di], s, 'placebo', di, warm);
      }
      for (const w of W) {
        w.cell.shifts = shifts.length;
        w.cell.discReplicated = { n: w.dn, mean: w.dn ? +(w.ds / w.dn).toFixed(2) : NaN };
        w.cell.replicated = w.dn === w.cell.discStored.n && Math.abs(w.ds / Math.max(1, w.dn) - w.cell.discStored.mean) <= 0.05;
        if (!w.cell.replicated) w.cell.notes.push(`discovery ${w.dn} trades, mean ${(w.ds / Math.max(1, w.dn)).toFixed(2)} vs stored ${w.cell.discStored.n}, ${w.cell.discStored.mean}`);
      }
    }
  }
  const r2 = (a: number[]) => a.map((v) => +v.toFixed(3));
  for (const c of cells) for (const s of [...c.arm, ...c.placebo]) { s.exc = r2(s.exc); s.fund = r2(s.fund); s.net = r2(s.net); }
  log(`${g.asset}: ${cells.length} cells (${cells.filter((c) => c.replicated).length} replicated), ${shifts.length} placebo shifts, ${days} validation days`);
  return { schema: 'perpta-decay1', asset: g.asset, dayValid: new Date(dayValid * DAY).toISOString().slice(0, 10), days, cells, notes };
}

// ---------------------------------------------------------------------------------------------------------------
// The report: pooled per round, day-block bootstrap, the predictions.

function rng(seed: number): () => number { let a = seed >>> 0; return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

/** Circular day-block bootstrap index sets (B of them, each `days` long). */
export function bootIdx(days: number, B = DECAY.boot, block = DECAY.bootBlock, seed = 1): Int32Array[] {
  const r = rng(seed), out: Int32Array[] = [];
  for (let b = 0; b < B; b++) { const ix = new Int32Array(days); let k = 0; while (k < days) { const s = Math.floor(r() * days); for (let j = 0; j < block && k < days; j++, k++) ix[k] = (s + j) % days; } out.push(ix); }
  return out;
}
export interface Est { mean: number; se: number; n: number }
/** Pooled per-trade mean (sum / count over days) and its bootstrap SE; with `minus`, the paired difference. */
export function est(num: number[], den: number[], boots: Int32Array[], minus?: { num: number[]; den: number[] }): Est {
  const m = (nu: number[], de: number[], ix?: Int32Array) => { let s = 0, n = 0; if (ix) for (const j of ix) { s += nu[j]; n += de[j]; } else for (let j = 0; j < nu.length; j++) { s += nu[j]; n += de[j]; } return n ? s / n : NaN; };
  const f = (ix?: Int32Array) => m(num, den, ix) - (minus ? m(minus.num, minus.den, ix) : 0);
  const mean = f(), vs = boots.map((ix) => f(ix)).filter((v) => v === v);
  const mu = vs.reduce((a, b) => a + b, 0) / Math.max(1, vs.length);
  const se = vs.length > 1 ? Math.sqrt(vs.reduce((a, b) => a + (b - mu) ** 2, 0) / (vs.length - 1)) : NaN;
  return { mean: +mean.toFixed(3), se: +se.toFixed(3), n: den.reduce((a, b) => a + b, 0) };
}

export interface RoundReport {
  round: number; run: string; cells: number; replicated: number; coins: string[];
  delays: Array<{ d: number; exc: Est; fund: Est; price: Est; net: Est; placebo: Est }>;
  drop15: Est; drop60: Est; P0: boolean; P1: boolean; P3: boolean; costCleared: string[]; verdict: string;
  byCoin: Record<string, { exc0: Est; net0: Est }>; bySide: Record<string, Est>; byHorizon: Array<{ maxHoldMin: number; cells: number; exc0: Est }>;
  perCell: Array<{ key: string; rank: number; replicated: boolean; exc: number[]; n: number[]; fund0: number; notes: string[] }>;
}

export function decayReport(coins: DecayCoin[]): { rounds: RoundReport[]; md: string } {
  const days = Math.max(0, ...coins.map((c) => c.days));
  const boots = bootIdx(days);
  const D = DECAY.delays;
  const sumOf = (cs: DecayCell[], pick: (c: DecayCell) => DelaySeries, k: keyof DelaySeries) => { const a = new Array(days).fill(0); for (const c of cs) pick(c)[k].forEach((v, j) => { a[j] += v; }); return a; };
  const rounds: RoundReport[] = [];
  const byRound = new Map<number, DecayCell[]>();
  for (const co of coins) for (const c of co.cells) (byRound.get(c.round) ?? byRound.set(c.round, []).get(c.round)!).push(c);
  for (const [round, all] of [...byRound.entries()].sort((a, b) => a[0] - b[0])) {
    const cs = all.filter((c) => c.replicated);
    const delays = D.map((d, di) => {
      const n = sumOf(cs, (c) => c.arm[di], 'n'), exc = sumOf(cs, (c) => c.arm[di], 'exc'), fund = sumOf(cs, (c) => c.arm[di], 'fund'), net = sumOf(cs, (c) => c.arm[di], 'net');
      const price = exc.map((v, j) => v - fund[j]);
      const pn = sumOf(cs, (c) => c.placebo[di], 'n'), pe = sumOf(cs, (c) => c.placebo[di], 'exc');
      return { d, exc: est(exc, n, boots), fund: est(fund, n, boots), price: est(price, n, boots), net: est(net, n, boots), placebo: est(pe, pn, boots) };
    });
    const di15 = D.indexOf(15), di60 = D.indexOf(60);
    const A = (di: number) => ({ num: sumOf(cs, (c) => c.arm[di], 'exc'), den: sumOf(cs, (c) => c.arm[di], 'n') });
    const a0 = A(0), drop15 = est(a0.num, a0.den, boots, A(di15)), drop60 = est(a0.num, a0.den, boots, A(di60));
    const e0 = delays[0].exc, e60 = delays[di60].exc;
    const P0 = e0.mean > 2 * e0.se;
    const P1 = drop15.mean >= 2 * drop15.se && Math.abs(e60.mean) <= e60.se;
    const P3 = delays.every((x) => Math.abs(x.placebo.mean) <= x.placebo.se);
    const coinsIn = [...new Set(cs.map((c) => c.a))].sort();
    const byCoin: RoundReport['byCoin'] = {};
    for (const a of coinsIn) { const cc = cs.filter((c) => c.a === a), n = sumOf(cc, (c) => c.arm[0], 'n'); byCoin[a] = { exc0: est(sumOf(cc, (c) => c.arm[0], 'exc'), n, boots), net0: est(sumOf(cc, (c) => c.arm[0], 'net'), n, boots) }; }
    const costCleared = coinsIn.filter((a) => byCoin[a].net0.mean > 2 * byCoin[a].net0.se);
    const bySide: RoundReport['bySide'] = {};
    for (const s of ['long', 'short']) { const cc = cs.filter((c) => c.side === s); if (cc.length) bySide[s] = est(sumOf(cc, (c) => c.arm[0], 'exc'), sumOf(cc, (c) => c.arm[0], 'n'), boots); }
    const hs = [...new Set(cs.map((c) => c.maxHold))].sort((a, b) => a - b);
    const byHorizon = hs.map((h) => { const cc = cs.filter((c) => c.maxHold === h); return { maxHoldMin: h, cells: cc.length, exc0: est(sumOf(cc, (c) => c.arm[0], 'exc'), sumOf(cc, (c) => c.arm[0], 'n'), boots) }; });
    const why: string[] = [];
    if (!P0) why.push(`P0 fails: d=0 excess ${e0.mean} bps (SE ${e0.se}) is not above 2 SE (no skill at entry: failure (a) confirmed)`);
    if (!P1) why.push(`P1 fails: drop to d=15 ${drop15.mean} (SE ${drop15.se}), d=60 excess ${e60.mean} (SE ${e60.se})`);
    if (!P3) why.push(`P3 fails: placebo excess outside 1 SE at d=${delays.filter((x) => Math.abs(x.placebo.mean) > x.placebo.se).map((x) => x.d).join(',')}`);
    if (costCleared.length >= 3) why.push(`d=0 net clears cost + 2 SE on ${costCleared.join(', ')}: cost, not decay, is the problem`);
    const verdict = round === 1 ? (P0 && P1 && P3 && costCleared.length < 3 ? 'SUPPORTED (P0, P1 and P3 hold)' : `FALSIFIED: ${why.join('; ')}`) : `secondary (round 1 decides): ${why.length ? why.join('; ') : 'P0, P1 and P3 hold'}`;
    const perCell = all.map((c) => ({ key: c.key, rank: c.rank, replicated: c.replicated, n: c.arm.map((s) => s.n.reduce((a, b) => a + b, 0)), exc: c.arm.map((s) => { const n = s.n.reduce((a, b) => a + b, 0); return n ? +(s.exc.reduce((a, b) => a + b, 0) / n).toFixed(2) : NaN; }), fund0: (() => { const n = c.arm[0].n.reduce((a, b) => a + b, 0); return n ? +(c.arm[0].fund.reduce((a, b) => a + b, 0) / n).toFixed(2) : NaN; })(), notes: c.notes }));
    rounds.push({ round, run: all[0].run, cells: all.length, replicated: cs.length, coins: coinsIn, delays, drop15, drop60, P0, P1, P3, costCleared, verdict, byCoin, bySide, byHorizon, perCell });
  }
  const L: string[] = [];
  L.push(`### Perp TA round 4, ${DECAY.id}: does the round 1-3 losers' excess decay within minutes? (validation 2024-01-01 .. 2025-06-30 only)`);
  L.push('Excess = net minus the random-entry baseline (same month, condition, exit and side), bps per trade; SE from a 5-day block bootstrap (B = 2000) by the signal\'s day. Placebo: the same triggers on 60 whole-day shifts. Round 1 (taker entries) decides; rounds 2 and 3 are secondary.');
  for (const r of rounds) {
    L.push('');
    L.push(`**Round ${r.round}** (run ${r.run}): ${r.replicated} of ${r.cells} top cells replicated (${r.coins.join(', ')}). ${r.verdict}.`);
    L.push('');
    L.push('| delay (min) | trades | excess bps (SE) | funding part | price part | net bps | placebo excess (SE) |');
    L.push('|---|---|---|---|---|---|---|');
    for (const x of r.delays) L.push(`| ${x.d} | ${x.exc.n} | ${x.exc.mean} (${x.exc.se}) | ${x.fund.mean} | ${x.price.mean} | ${x.net.mean} | ${x.placebo.mean} (${x.placebo.se}) |`);
    L.push('');
    L.push(`- Drop d=0 to d=15: ${r.drop15.mean} (SE ${r.drop15.se}); to d=60: ${r.drop60.mean} (SE ${r.drop60.se}). P0 ${r.P0 ? 'holds' : 'fails'}, P1 ${r.P1 ? 'holds' : 'fails'}, P3 ${r.P3 ? 'holds' : 'fails'}.`);
    L.push(`- By coin at d=0 (excess / net): ${Object.entries(r.byCoin).map(([a, v]) => `${a} ${v.exc0.mean} / ${v.net0.mean} (SE ${v.net0.se})`).join('; ')}. By side: ${Object.entries(r.bySide).map(([s, v]) => `${s} ${v.mean} (SE ${v.se}, ${v.n} trades)`).join('; ')}.`);
    L.push(`- P2 (descriptive) d=0 excess by the exit's longest hold: ${r.byHorizon.map((h) => `${h.maxHoldMin >= 1440 ? `${(h.maxHoldMin / 1440).toFixed(1)} d` : `${h.maxHoldMin} min`} ${h.exc0.mean} (${h.cells} cells)`).join('; ')}.`);
  }
  return { rounds, md: L.join('\n') };
}

export function decayRegistryRows(rounds: RoundReport[], sha: string, run: string, at = new Date()): RegRow[] {
  const ref = runRef(run), rows: RegRow[] = [], epoch = `perp-ta round 4 decay (${DECAY.id})`;
  for (const r of rounds) {
    for (const x of r.delays) {
      rows.push(regRow({ arm: `r4:decay:r${r.round}:d${x.d}`, role: 'neighbour', round: 4, codeSha: sha, codeEpoch: epoch, ref, at, verdict: `diagnostic: excess ${x.exc.mean} bps (SE ${x.exc.se}), ${x.exc.n} validation trades`, raw: { kind: 'r4-decay', of_round: r.round, of_run: r.run, delay: x.d, ...x } }));
      rows.push(regRow({ arm: `r4:decay:r${r.round}:d${x.d}:placebo`, role: 'placebo', round: 4, codeSha: sha, codeEpoch: epoch, ref, at, verdict: `placebo excess ${x.placebo.mean} bps (SE ${x.placebo.se})`, raw: { kind: 'r4-decay-placebo', of_round: r.round, delay: x.d, placebo: x.placebo } }));
    }
    rows.push(regRow({ arm: `r4:decay:r${r.round}:verdict`, role: 'neighbour', round: 4, codeSha: sha, codeEpoch: epoch, ref, at, verdict: r.verdict, raw: { kind: 'r4-decay-verdict', of_round: r.round, P0: r.P0, P1: r.P1, P3: r.P3, cost_cleared: r.costCleared, drop15: r.drop15, drop60: r.drop60, replicated: r.replicated, cells: r.cells } }));
  }
  return rows;
}

// ---------------------------------------------------------------------------------------------------------------
// CLI.

function arg(k: string, d?: string): string | undefined { const i = process.argv.indexOf(`--${k}`); return i >= 0 && process.argv[i + 1] !== undefined && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : d; }
const args = (k: string) => process.argv.flatMap((v, i) => (v === `--${k}` && process.argv[i + 1] ? [process.argv[i + 1]] : []));

async function main(): Promise<void> {
  const mode = process.argv[2];
  if (mode === 'coin') {
    const g = readGrid(arg('data')!);
    if (g.asset === 'DOGE') throw new Error('DOGE is excluded (Steven, Nov 5)');
    const rounds: RoundIn[] = [];
    for (const spec of args('round')) {
      const [rs, run, dir] = spec.split(':');
      const cf = path.join(dir, 'candidates.json.gz'), hf = path.join(dir, `${g.asset}.header.json`);
      if (!fs.existsSync(cf) || !fs.existsSync(hf)) { console.log(`[perp-ta-decay] round ${rs}: ${!fs.existsSync(cf) ? cf : hf} missing: skipped`); continue; }
      const cands = JSON.parse(zlib.gunzipSync(fs.readFileSync(cf)).toString('utf8')) as Candidate[];
      const header = JSON.parse(fs.readFileSync(hf, 'utf8'));
      if (!header.costs) throw new Error(`${hf}: no costs`);
      rounds.push({ round: +rs, run, cands, header });
    }
    const modules = arg('modules', 'true') === 'false' ? false as const : { history: arg('history'), forecasts: arg('forecasts'), cacheDir: arg('module-cache') };
    const res = decayCoin(g, rounds, { modules, log: (m) => console.log(`[perp-ta-decay] ${m}`) });
    fs.mkdirSync(path.dirname(arg('out')!), { recursive: true });
    fs.writeFileSync(arg('out')!, JSON.stringify(res));
    for (const c of res.cells) console.log(`[perp-ta-decay] r${c.round} #${c.rank} ${c.key}: ${c.replicated ? 'replicated' : `NOT replicated (${c.notes.join('; ')})`}; d=0 validation ${c.arm[0].n.reduce((a, b) => a + b, 0)} trades`);
    return;
  }
  if (mode === 'report') {
    const dir = arg('in', 'in')!, outDir = arg('out', 'report')!;
    const files = fs.readdirSync(dir, { recursive: true }).map(String).filter((f) => /decay-[A-Z0-9]+\.json$/.test(f));
    const coins = files.map((f) => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')) as DecayCoin);
    const { rounds, md } = decayReport(coins);
    fs.mkdirSync(outDir, { recursive: true });
    const sha = process.env.GITHUB_SHA ?? 'local', run = process.env.GITHUB_RUN_ID ?? 'local';
    fs.writeFileSync(path.join(outDir, 'decay.json'), JSON.stringify({ at: new Date().toISOString(), sha, run, coins: coins.map((c) => c.asset), notes: coins.flatMap((c) => c.notes), rounds }, null, 1));
    fs.writeFileSync(path.join(outDir, 'decay.md'), md + '\n');
    fs.writeFileSync(path.join(outDir, 'registry.jsonl'), decayRegistryRows(rounds, sha, run).map((r) => JSON.stringify(r)).join('\n') + '\n');
    console.log(md);
    return;
  }
  throw new Error('usage: perpTaDecay.ts coin|report ...');
}

if (process.argv[1] && /perpTaDecay\.ts$/.test(process.argv[1])) main().catch((e) => { console.error(e); process.exitCode = 1; });
