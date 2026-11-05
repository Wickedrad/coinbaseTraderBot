// Whole-universe deflation of one perp TA sweep run (thread "Build a TA rulebook for perpetuals", Nov 5 2026; the
// institutional-methods proposals for this thread, /mnt/project-files/institutional-methods/per-thread-changes.json).
// The frozen pre-registered selection (research/perpTaSweep.ts report) is not changed: this reports beside it.
//
//   coin    node --import tsx research/perpTaStudy.ts coin --data data/perp-ta/BTC.bin --cells in/BTC.jsonl.gz
//           --candidates in/candidates.json.gz --out out/study-BTC.json.gz [--top 5000] [--any-blocks: tests only]
//           [--history data/hist-BTC --forecasts data/server-hist --module-cache data/modcache]
//   report  node --import tsx research/perpTaStudy.ts report --in in --out report --run <sweep run> [--n-raw 98793570]
//
// Per coin (never past the seal: every table is built to the sweep's own nMax, so the sealed block is not read):
//   1. the universe: the coin's top cells by discovery excess t (stored by the sweep, t >= 2.5) plus every group
//      representative that passed Benjamini-Hochberg; each cell's trades are recomputed exactly as the sweep walked
//      them and must match its stored discovery n and mean (mismatches are dropped and counted)
//   2. daily net P&L per cell (bps of notional, after fees and signed funding; a trade is booked on its exit day)
//   3. ONC (optimal number of clusters, Lopez de Prado): k-means on the z-scored weekly discovery P&L (correlation
//      distance sqrt((1 - rho) / 2)), k chosen by the silhouette t-statistic, then one pass re-clustering the clusters
//      of below-average quality; N_eff = the number of clusters; each cluster's medoid is kept
// Report (all coins on one calendar):
//   - Hansen's SPA (consistent, lower and upper p) and Romano-Wolf StepM on daily net P&L against flat, stationary
//     bootstrap (mean block 5 days, B = 2000), over the medoids plus the representatives, on the validation block (the
//     test) and on the discovery block (in sample: those series were screened on those same days out of every cell
//     tested, so its p-values do not adjust for that search and are not a test)
//   - the deflated Sharpe ratio of the best discovery cell at N = N_eff and at N = N_raw
// Cells reading the TA Net / Librarian / cross-graph forecasts are left out, as in the sweep's validation family: their
// model selection saw 2024-2026.

import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import {
  readGrid, buildPrims, triggers, stateAt, outcomes, atrUnit, conditions, folds, isDiagnostic, POLICIES, CONDS, NZ,
  type Grid, type Costs, type CellRec, type Candidate,
} from './perpTaSweep';
import { modulePrims } from './perpTaModules';
import { resolveRule } from './perpTaBlind';

const MIN = 60_000;
const DAY = 86_400_000;
const fin = Number.isFinite;

export const keyOf = (c: { a: string; rule: string; mode: string; pol: string; side: string; cond: string }) => `${c.a}|${c.rule}|${c.mode}|${c.pol}|${c.side}|${c.cond}`;

function rng(seed: number): () => number { let a = seed >>> 0; return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

// ---------------------------------------------------------------------------------------------------------------
// ONC on z-scored rows (each row has unit norm, so a dot product is a correlation).

interface Onc { labels: Int32Array; k: number; q: number; kBase: number; qBase: number; redone: number }

function silhouette(idx: number[], lab: Int32Array, k: number, D: Float32Array, n: number): Float64Array {
  const s = new Float64Array(idx.length), size = new Int32Array(k);
  for (let a = 0; a < idx.length; a++) size[lab[a]]++;
  const sum = new Float64Array(k);
  for (let a = 0; a < idx.length; a++) {
    sum.fill(0);
    const row = idx[a] * n;
    for (let b = 0; b < idx.length; b++) if (b !== a) sum[lab[b]] += D[row + idx[b]];
    const own = lab[a];
    if (size[own] <= 1) { s[a] = 0; continue; }
    const ai = sum[own] / (size[own] - 1);
    let bi = Infinity;
    for (let c = 0; c < k; c++) if (c !== own && size[c] > 0) bi = Math.min(bi, sum[c] / size[c]);
    s[a] = fin(bi) && Math.max(ai, bi) > 0 ? (bi - ai) / Math.max(ai, bi) : 0;
  }
  return s;
}

const tstat = (xs: ArrayLike<number>) => { const n = xs.length; if (n < 2) return 0; let m = 0; for (let i = 0; i < n; i++) m += xs[i]; m /= n; let v = 0; for (let i = 0; i < n; i++) v += (xs[i] - m) ** 2; v /= n - 1; return v > 0 ? m / Math.sqrt(v) : 0; };

function kmeans(idx: number[], k: number, X: Float32Array, W: number, D: Float32Array, n: number, r: () => number, iters = 15): Int32Array {
  const m = idx.length, lab = new Int32Array(m);
  // k-means++ seeding on the correlation distance.
  const cent = new Float64Array(k * W), d2 = new Float64Array(m).fill(Infinity);
  let pick = Math.floor(r() * m);
  for (let c = 0; c < k; c++) {
    for (let w = 0; w < W; w++) cent[c * W + w] = X[idx[pick] * W + w];
    let tot = 0;
    for (let a = 0; a < m; a++) { const d = D[idx[pick] * n + idx[a]]; const dd = d * d; if (dd < d2[a]) d2[a] = dd; tot += d2[a]; }
    if (c + 1 < k) { let u = r() * tot; pick = m - 1; for (let a = 0; a < m; a++) { u -= d2[a]; if (u <= 0) { pick = a; break; } } }
  }
  const cnt = new Int32Array(k);
  for (let it = 0; it < iters; it++) {
    let moved = 0;
    for (let a = 0; a < m; a++) {
      const xo = idx[a] * W;
      let best = 0, bd = Infinity;
      for (let c = 0; c < k; c++) {
        let dot = 0, nn = 0;
        const co = c * W;
        for (let w = 0; w < W; w++) { const v = cent[co + w]; dot += X[xo + w] * v; nn += v * v; }
        const d = nn - 2 * dot;
        if (d < bd) { bd = d; best = c; }
      }
      if (it === 0 || lab[a] !== best) { moved++; lab[a] = best; }
    }
    if (it > 0 && moved === 0) break;
    cent.fill(0); cnt.fill(0);
    for (let a = 0; a < m; a++) { const c = lab[a], xo = idx[a] * W, co = c * W; cnt[c]++; for (let w = 0; w < W; w++) cent[co + w] += X[xo + w]; }
    for (let c = 0; c < k; c++) {
      if (cnt[c]) { for (let w = 0; w < W; w++) cent[c * W + w] /= cnt[c]; continue; }
      const a = Math.floor(r() * m); for (let w = 0; w < W; w++) cent[c * W + w] = X[idx[a] * W + w]; // empty: reseed
    }
  }
  // Compact labels (drop empty clusters).
  const map = new Int32Array(k).fill(-1); let kk = 0;
  for (let a = 0; a < m; a++) { if (map[lab[a]] < 0) map[lab[a]] = kk++; lab[a] = map[lab[a]]; }
  return lab;
}

const K_GRID = [2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100, 125, 150];

function oncBase(idx: number[], X: Float32Array, W: number, D: Float32Array, n: number, r: () => number): { lab: Int32Array; k: number; q: number; s: Float64Array } {
  if (idx.length < 4) return { lab: new Int32Array(idx.length), k: 1, q: 0, s: new Float64Array(idx.length) };
  let best = { lab: new Int32Array(idx.length), k: 1, q: -Infinity, s: new Float64Array(idx.length) };
  for (const k0 of K_GRID) {
    if (k0 > Math.floor(idx.length / 2)) break;
    for (let rep = 0; rep < 2; rep++) {
      const lab = kmeans(idx, k0, X, W, D, n, r);
      let k = 0; for (let a = 0; a < lab.length; a++) k = Math.max(k, lab[a] + 1);
      if (k < 2) continue;
      const s = silhouette(idx, lab, k, D, n), q = tstat(s);
      if (q > best.q) best = { lab, k, q, s };
    }
  }
  if (!fin(best.q)) best.q = 0;
  return best;
}

export function onc(X: Float32Array, W: number, n: number, seed = 1): Onc {
  // Correlation distance matrix (rows of X have unit norm).
  const D = new Float32Array(n * n);
  for (let a = 0; a < n; a++) {
    D[a * n + a] = 0;
    for (let b = a + 1; b < n; b++) {
      let dot = 0; const ao = a * W, bo = b * W;
      for (let w = 0; w < W; w++) dot += X[ao + w] * X[bo + w];
      const d = Math.sqrt(Math.max(0, (1 - Math.min(1, dot)) / 2));
      D[a * n + b] = d; D[b * n + a] = d;
    }
  }
  const r = rng(seed), all = Array.from({ length: n }, (_, i) => i);
  const base = oncBase(all, X, W, D, n, r);
  const labels = Int32Array.from(base.lab);
  // One recursive pass: the clusters of below-average quality are clustered again; kept if the whole improves.
  const qk: number[] = [];
  for (let c = 0; c < base.k; c++) { const ss: number[] = []; for (let a = 0; a < n; a++) if (base.lab[a] === c) ss.push(base.s[a]); qk.push(tstat(ss)); }
  const avg = qk.reduce((a, b) => a + b, 0) / Math.max(1, qk.length);
  const redo = qk.map((q, c) => (q < avg ? c : -1)).filter((c) => c >= 0);
  let k = base.k, q = base.q, redone = 0;
  if (redo.length > 1) {
    const sub = all.filter((a) => redo.includes(base.lab[a]));
    const sb = oncBase(sub, X, W, D, n, r);
    const keep = new Map<number, number>(); let next = 0;
    const trial = new Int32Array(n);
    for (let a = 0; a < n; a++) if (!redo.includes(base.lab[a])) { if (!keep.has(base.lab[a])) keep.set(base.lab[a], next++); trial[a] = keep.get(base.lab[a])!; }
    sub.forEach((a, j) => { trial[a] = next + sb.lab[j]; });
    const kt = next + sb.k;
    const qt = tstat(silhouette(all, trial, kt, D, n));
    if (qt > q) { labels.set(trial); k = kt; q = qt; redone = redo.length; }
  }
  return { labels, k, q, kBase: base.k, qBase: base.q, redone };
}

// ---------------------------------------------------------------------------------------------------------------
// Per coin.

export interface StudySeries { key: string; a: string; rule: string; mode: string; pol: string; side: string; cond: string; disc: { n: number; mean: number; tExc: number }; medoid: boolean; rep: boolean; cluster: number; size: number; srDisc: number; day0: number; daily: number[] }
export interface StudyCoin {
  schema: 'perpta-study1'; asset: string; day0: number; dayValid: number; daySeal: number; universe: number; replicated: number; mismatched: number; unresolved: number;
  onc: { n: number; k: number; quality: number; kBase: number; qualityBase: number; redone: number; weeks: number };
  srDiscAll: number[]; series: StudySeries[]; notes: string[];
}

const dailySr = (xs: ArrayLike<number>, from: number, to: number) => { let s = 0, s2 = 0; const n = to - from; for (let i = from; i < to; i++) { s += xs[i]; s2 += xs[i] * xs[i]; } const m = s / n, v = s2 / n - m * m; return v > 0 ? m / Math.sqrt(v) : 0; };

export function studyCoin(g: Grid, cells: CellRec[], header: { seal: string; validFrom: string; costs: Costs }, reps: Set<string>, o: { top?: number; anyBlocks?: boolean; modules?: false | { history?: string; forecasts?: string; cacheDir?: string }; log?: (m: string) => void }): StudyCoin {
  const log = o.log ?? console.log, quiet = () => undefined;
  // The pre-registered blocks (/mnt/project-files/perp-ta/preregistration.md): a sweep run with other blocks is refused.
  if (Date.parse(header.seal) !== Date.parse('2025-07-01T00:00:00Z') || Date.parse(header.validFrom) !== Date.parse('2024-01-01T00:00:00Z')) {
    if (!o.anyBlocks) throw new Error(`cells were swept with seal ${header.seal} / validation from ${header.validFrom}, not the pre-registered 2025-07-01 / 2024-01-01`);
  }
  const seal = Date.parse(header.seal), validFrom = Date.parse(header.validFrom);
  const nMax = Math.min(g.n, Math.max(0, Math.round((seal - g.t0) / MIN))); // exactly the sweep's: the sealed block is never built
  const prims = buildPrims(g, nMax, quiet);
  const mod = o.modules === false ? undefined : modulePrims(g, nMax, { ...(o.modules || {}), discoveryEnd: validFrom, log });
  if (mod) prims.push(...mod.prims);
  const byId = new Map(prims.map((p) => [p.id, p]));
  const unit = atrUnit(g, nMax), out = outcomes(g, nMax, unit, header.costs), cond = conditions(g, nMax, mod), fo = folds(g, nMax, validFrom);
  const discEnd = fo.discovery < fo.starts.length ? fo.starts[fo.discovery] : nMax;
  const inCond = (i: number, c: number) => { if (c === 0) return true; for (let z = 0; z < NZ; z++) if (cond[i * NZ + z] === c) return true; return false; };
  const day0 = Math.floor(g.t0 / DAY), daySeal = Math.floor((g.t0 + nMax * MIN) / DAY), dayValid = Math.floor(validFrom / DAY);
  const nDays = daySeal - day0, dDisc = Math.max(0, Math.min(nDays, dayValid - day0));
  // The universe.
  const top = o.top ?? 5000;
  const clean = cells.filter((c) => !isDiagnostic(c)), nDiag = cells.length - clean.length;
  const sorted = clean.sort((x, y) => y.disc.tExc - x.disc.tExc);
  const uni = sorted.slice(0, top), seen = new Set(uni.map(keyOf));
  for (const c of sorted) { const k = keyOf(c); if (reps.has(k) && !seen.has(k)) { uni.push(c); seen.add(k); } }
  // One walk per (rule, mode, exit) serves every cell of the universe that shares it.
  const groups = new Map<string, CellRec[]>();
  for (const c of uni) { const k = `${c.rule}\u0001${c.mode}\u0001${c.pol}`; (groups.get(k) ?? groups.set(k, []).get(k)!).push(c); }
  const daily = new Map<string, Float32Array>(), nDisc = new Map<string, number>(), sDisc = new Map<string, number>();
  const foldN = new Map<string, Float64Array>(), foldS = new Map<string, Float64Array>();
  let unresolved = 0;
  for (const [gk, cs] of groups) {
    const [rule, mode, pol] = gk.split('\u0001');
    const rr = resolveRule(rule, byId), p = POLICIES.findIndex((x) => x.id === pol);
    if (!rr || p < 0) { unresolved += cs.length; continue; }
    const [tp, fp] = rr, tr = triggers(tp, g.c.valid, nMax);
    const mo = mode === 'fade' ? 1 : 0;
    const want = cs.map((c) => ({ c, key: keyOf(c), side: c.side === 'short' ? 1 : 0, ci: CONDS.indexOf(c.cond), arr: new Float32Array(nDays), n: 0, s: 0, fn: new Float64Array(fo.starts.length), fs: new Float64Array(fo.starts.length) }));
    let nextFree = 0;
    for (let q = 0; q < tr.idx.length; q++) {
      const i = tr.idx[q];
      if (fp && stateAt(fp, i) !== tr.dir[q]) continue;
      if (i < nextFree) continue;
      if (!g.c.valid[i] || i + 1 >= nMax || !g.c.valid[i + 1]) continue;
      const sd = tr.dir[q], td = mo === 0 ? sd : -sd, k = p * 2 + (td > 0 ? 0 : 1);
      const x = out.net[k][i];
      if (x !== x) continue;
      const ex = out.exit[k][i];
      nextFree = ex;
      if (fo.of[ex] !== fo.of[i]) continue; // purged as in the sweep
      const side = sd > 0 ? 0 : 1, d = Math.floor((g.t0 + ex * MIN) / DAY) - day0;
      for (const w of want) {
        if (w.side !== side || w.ci < 0 || !inCond(i, w.ci)) continue;
        if (d >= 0 && d < nDays) w.arr[d] += x;
        if (i < discEnd) { w.n++; w.s += x; }
        const fk = fo.of[i]; if (fk >= 0 && fk < w.fn.length) { w.fn[fk]++; w.fs[fk] += x; }
      }
    }
    for (const w of want) { daily.set(w.key, w.arr); nDisc.set(w.key, w.n); sDisc.set(w.key, w.s); foldN.set(w.key, w.fn); foldS.set(w.key, w.fs); }
  }
  // Replication against the stored discovery record.
  const ok: CellRec[] = [];
  let mismatched = 0;
  for (const c of uni) {
    const k = keyOf(c), n = nDisc.get(k);
    if (n === undefined) continue;
    const mean = n ? sDisc.get(k)! / n : NaN;
    if (n === c.disc.n && Math.abs(mean - c.disc.mean) <= 0.05) ok.push(c); else mismatched++;
  }
  // Validation folds against the sweep's stored record (report only: an input that changed after the sweep, e.g. a
  // Binance month that failed to download then and loads now, changes validation trades without failing discovery).
  let valDrift = 0;
  for (const c of ok) {
    const fn = foldN.get(keyOf(c))!, fs = foldS.get(keyOf(c))!;
    for (let k = fo.discovery; k < Math.min(fn.length, c.f.length); k++) if (fn[k] !== c.f[k][0] || Math.abs(fs[k] - c.f[k][1]) > 0.05 + 1e-6 * Math.abs(c.f[k][1])) { valDrift++; break; }
  }
  const notes: string[] = [];
  if (mismatched) notes.push(`${mismatched} cells did not replicate their stored discovery n / mean and were left out`);
  if (valDrift) notes.push(`${valDrift} replicated cells differ from the sweep's stored validation folds (an input changed after the sweep); the study uses today's inputs`);
  if (nDiag) notes.push(`${nDiag} stored cells read the TA Net / Librarian / cross-graph forecasts and were left out (their model selection saw 2024-2026)`);
  if (unresolved) notes.push(`${unresolved} cells' rules or exits were not found`);
  log(`${g.asset}: universe ${uni.length} (${nDiag} forecast cells left out), replicated ${ok.length}, mismatched ${mismatched}, unresolved ${unresolved}, validation folds differing ${valDrift}`);
  // ONC on the z-scored weekly discovery P&L of the replicated top cells (not the extra representatives).
  const topKeys = new Set(sorted.slice(0, top).map(keyOf));
  const pool = ok.filter((c) => topKeys.has(keyOf(c))); // a prefix of ok: uni lists the top cells first
  const W = Math.max(1, Math.floor(dDisc / 7));
  const rows: number[] = [], X: number[] = [];
  for (let a = 0; a < pool.length; a++) {
    const arr = daily.get(keyOf(pool[a]))!, wk = new Float64Array(W);
    for (let d = 0; d < W * 7; d++) wk[Math.floor(d / 7)] += arr[d];
    let m = 0; for (let w = 0; w < W; w++) m += wk[w]; m /= W;
    let nn = 0; for (let w = 0; w < W; w++) { wk[w] -= m; nn += wk[w] * wk[w]; }
    if (!(nn > 0)) continue;
    const sc = 1 / Math.sqrt(nn);
    rows.push(a); for (let w = 0; w < W; w++) X.push(wk[w] * sc);
  }
  const t = Date.now();
  const res = rows.length >= 4 ? onc(Float32Array.from(X), W, rows.length, 7) : { labels: new Int32Array(rows.length), k: rows.length ? 1 : 0, q: 0, kBase: 1, qBase: 0, redone: 0 };
  log(`${g.asset}: ONC over ${rows.length} cells (${W} weeks): ${res.k} clusters (base ${res.kBase}), quality ${res.q.toFixed(3)} in ${((Date.now() - t) / 1000).toFixed(0)} s`);
  // Medoids: the member with the highest total correlation to its cluster.
  const members = new Map<number, number[]>();
  rows.forEach((a, j) => { const c = res.labels[j]; (members.get(c) ?? members.set(c, []).get(c)!).push(j); });
  const medoid = new Map<number, { j: number; size: number }>();
  const Xf = Float32Array.from(X);
  for (const [c, js] of members) {
    let bj = js[0], bs = -Infinity;
    if (js.length > 2) for (const j of js) { let s = 0; for (const j2 of js) { let dot = 0; for (let w = 0; w < W; w++) dot += Xf[j * W + w] * Xf[j2 * W + w]; s += dot; } if (s > bs) { bs = s; bj = j; } }
    medoid.set(c, { j: bj, size: js.length });
  }
  const isMed = new Map<number, { cluster: number; size: number }>();
  for (const [c, m] of medoid) isMed.set(rows[m.j], { cluster: c, size: m.size });
  const clusterOf = new Map<number, number>(); rows.forEach((a, j) => clusterOf.set(a, res.labels[j]));
  const series: StudySeries[] = [];
  const srDiscAll: number[] = [];
  for (let a = 0; a < ok.length; a++) {
    const c = ok[a], k = keyOf(c), arr = daily.get(k)!;
    const inPool = a < pool.length, med = inPool ? isMed.get(a) : undefined, rep = reps.has(k);
    const sr = dailySr(arr, 0, Math.max(1, dDisc));
    if (med) srDiscAll.push(+sr.toFixed(5));
    if (!med && !rep) continue;
    const cl = inPool ? clusterOf.get(a) ?? -1 : -1;
    series.push({ key: k, a: c.a, rule: c.rule, mode: c.mode, pol: c.pol, side: c.side, cond: c.cond, disc: { n: c.disc.n, mean: c.disc.mean, tExc: c.disc.tExc }, medoid: !!med, rep, cluster: cl, size: med?.size ?? (cl >= 0 ? members.get(cl)?.length ?? 0 : 0), srDisc: +sr.toFixed(5), day0, daily: Array.from(arr, (v) => +v.toFixed(2)) });
  }
  return { schema: 'perpta-study1', asset: g.asset, day0, dayValid, daySeal, universe: uni.length, replicated: ok.length, mismatched, unresolved, onc: { n: rows.length, k: res.k, quality: +res.q.toFixed(4), kBase: res.kBase, qualityBase: +res.qBase.toFixed(4), redone: res.redone, weeks: W }, srDiscAll, series, notes };
}

// ---------------------------------------------------------------------------------------------------------------
// SPA / StepM and the deflated Sharpe ratio.

/** Hansen (2005) SPA and Romano-Wolf (2005) StepM on the columns of `d` (K series of T days, performance against flat),
 *  stationary bootstrap (Politis-Romano) with mean block `block`, B resamples, one index sequence per resample. */
export function spa(d: Float64Array[], T: number, o: { B?: number; block?: number; seed?: number; alphas?: number[] } = {}): { pC: number; pL: number; pU: number; stat: number; best: number; stepm: Record<string, number[]> } {
  const K = d.length, B = o.B ?? 2000, pr = 1 / (o.block ?? 5), r = rng(o.seed ?? 11);
  const pre = d.map((x) => { const c = new Float64Array(T + 1); for (let t = 0; t < T; t++) c[t + 1] = c[t] + x[t]; return c; });
  const mean = pre.map((c) => c[T] / T);
  const bm = new Float64Array(K * B); // bootstrap means
  const seg = (k: number, a: number, len: number) => { const c = pre[k]; if (a + len <= T) return c[a + len] - c[a]; return c[T] - c[a] + c[a + len - T]; };
  for (let b = 0; b < B; b++) {
    // Blocks: start uniform, geometric length (mean 1 / pr), wrapping around.
    const blocks: Array<[number, number]> = [];
    for (let t = 0; t < T;) { const a = Math.floor(r() * T); let len = 1; while (t + len < T && r() > pr) len++; blocks.push([a, len]); t += len; }
    for (let k = 0; k < K; k++) { let s = 0; for (const [a, len] of blocks) { let rem = len, st = a; while (rem > 0) { const l = Math.min(rem, T); s += seg(k, st, l); rem -= l; st = (st + l) % T; } } bm[k * B + b] = s / T; }
  }
  const om = new Float64Array(K); // omega: bootstrap sd of sqrt(T) * mean
  for (let k = 0; k < K; k++) { let s = 0, s2 = 0; for (let b = 0; b < B; b++) { const v = bm[k * B + b]; s += v; s2 += v * v; } const m = s / B; om[k] = Math.sqrt(Math.max(1e-18, (s2 / B - m * m) * T)); }
  const tk = mean.map((m, k) => (Math.sqrt(T) * m) / om[k]);
  let stat = 0, best = -1; for (let k = 0; k < K; k++) if (tk[k] > stat) { stat = tk[k]; best = k; } // -1: no series above 0
  const thr = Math.sqrt(2 * Math.log(Math.log(T)));
  const pFor = (g: (k: number) => number) => {
    let hits = 0;
    for (let b = 0; b < B; b++) { let mx = 0; for (let k = 0; k < K; k++) { const z = (Math.sqrt(T) * (bm[k * B + b] - g(k))) / om[k]; if (z > mx) mx = z; } if (mx >= stat) hits++; }
    return hits / B;
  };
  const pU = pFor((k) => mean[k]);
  const pC = pFor((k) => (Math.sqrt(T) * mean[k] / om[k] >= -thr ? mean[k] : 0));
  const pL = pFor((k) => Math.max(mean[k], 0));
  // StepM (studentized, step-down).
  const stepm: Record<string, number[]> = {};
  for (const al of o.alphas ?? [0.05, 0.1]) {
    let active = Array.from({ length: K }, (_, k) => k); const rej: number[] = [];
    for (;;) {
      const mx = new Float64Array(B);
      for (let b = 0; b < B; b++) { let m = -Infinity; for (const k of active) { const z = (Math.sqrt(T) * (bm[k * B + b] - mean[k])) / om[k]; if (z > m) m = z; } mx[b] = m; }
      const sortedMx = Array.from(mx).sort((x, y) => x - y), c = sortedMx[Math.min(B - 1, Math.ceil((1 - al) * B) - 1)];
      const now = active.filter((k) => tk[k] > c);
      if (!now.length) break;
      rej.push(...now); active = active.filter((k) => !now.includes(k));
      if (!active.length) break;
    }
    stepm[String(al)] = rej;
  }
  return { pC, pL, pU, stat, best, stepm };
}

const erf = (x: number) => { const s = Math.sign(x); x = Math.abs(x); const t = 1 / (1 + 0.3275911 * x); const y = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x); return s * y; };
export const Phi = (z: number) => 0.5 * (1 + erf(z / Math.SQRT2));
/** Inverse normal CDF (Acklam). */
export function PhiInv(p: number): number {
  const a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.357751867269, -30.66479806614716, 2.506628277459239];
  const b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572];
  const c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783];
  const d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416];
  const pl = 0.02425;
  if (p < pl) { const q = Math.sqrt(-2 * Math.log(p)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
  if (p > 1 - pl) { const q = Math.sqrt(-2 * Math.log(1 - p)); return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
  const q = p - 0.5, r = q * q;
  return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
}

/** Deflated Sharpe ratio (Bailey and Lopez de Prado 2014): the probability that the best of N trials' true Sharpe is
 *  above 0, given the variance of the trials' Sharpe ratios, the sample length and the best series' skew and kurtosis. */
export function dsr(x: ArrayLike<number>, N: number, varSr: number): { sr: number; sr0: number; dsr: number; skew: number; kurt: number; T: number } {
  const T = x.length; let m = 0; for (let i = 0; i < T; i++) m += x[i]; m /= T;
  let m2 = 0, m3 = 0, m4 = 0; for (let i = 0; i < T; i++) { const e = x[i] - m; m2 += e * e; m3 += e ** 3; m4 += e ** 4; }
  m2 /= T; m3 /= T; m4 /= T;
  const sd = Math.sqrt(m2), sr = sd > 0 ? m / sd : 0, skew = sd > 0 ? m3 / sd ** 3 : 0, kurt = sd > 0 ? m4 / sd ** 4 : 3;
  const g = 0.5772156649, Nn = Math.max(2, N);
  const sr0 = Math.sqrt(Math.max(0, varSr)) * ((1 - g) * PhiInv(1 - 1 / Nn) + g * PhiInv(1 - 1 / (Nn * Math.E)));
  const den = Math.sqrt(Math.max(1e-12, 1 - skew * sr + ((kurt - 1) / 4) * sr * sr));
  return { sr, sr0, dsr: Phi(((sr - sr0) * Math.sqrt(T - 1)) / den), skew, kurt, T };
}

export function studyReport(coins: StudyCoin[], o: { run: string; nRaw: number; B?: number; block?: number }): { md: string; out: Record<string, unknown> } {
  const all = coins.flatMap((c) => c.series);
  const nEff = coins.reduce((s, c) => s + c.onc.k, 0);
  const D0 = Math.min(...coins.map((c) => c.day0)), Dv = Math.max(...coins.map((c) => c.dayValid)), Ds = Math.min(...coins.map((c) => c.daySeal));
  const Td = Dv - D0, Tv = Ds - Dv;
  const col = (s: StudySeries, from: number, T: number) => { const x = new Float64Array(T); for (let t = 0; t < T; t++) { const di = from + t - s.day0; if (di >= 0 && di < s.daily.length) x[t] = s.daily[di]; } return x; };
  const disc = all.map((s) => col(s, D0, Td)), val = all.map((s) => col(s, Dv, Tv));
  const sd = spa(disc, Td, { B: o.B, block: o.block, seed: 11 }), sv = spa(val, Tv, { B: o.B, block: o.block, seed: 12 });
  const srs = coins.flatMap((c) => c.srDiscAll), mu = srs.reduce((a, b) => a + b, 0) / Math.max(1, srs.length), varSr = srs.reduce((a, b) => a + (b - mu) ** 2, 0) / Math.max(1, srs.length - 1);
  // The best discovery cell by daily Sharpe, on its own coin's discovery days.
  let bi = 0; for (let k = 0; k < all.length; k++) if (all[k].srDisc > all[bi].srDisc) bi = k;
  const bs = all[bi];
  const own = bs ? bs.daily.slice(0, Math.max(1, Dv - bs.day0)) : [];
  const dEff = bs ? dsr(own, nEff, varSr) : undefined, dRaw = bs ? dsr(own, o.nRaw, varSr) : undefined;
  const bv = bs ? val[bi] : new Float64Array(0);
  const vm = bv.length ? bv.reduce((a, b) => a + b, 0) / bv.length : NaN;
  const fmtK = (s?: StudySeries) => (s ? `${s.a} ${s.rule} ${s.mode} ${s.pol} ${s.side} ${s.cond}` : 'none');
  const sumBps = (x: Float64Array) => x.reduce((a, b) => a + b, 0);
  const stepLine = (r: ReturnType<typeof spa>, vs: Float64Array[]) => Object.entries(r.stepm).map(([al, ks]) => `at ${al}: ${ks.length} cell(s)${ks.length ? ` (${ks.slice(0, 5).map((k) => `${fmtK(all[k])}, ${(sumBps(vs[k]) / vs[k].length).toFixed(2)} bps/day`).join('; ')})` : ''}`).join('; ');
  const md = [
    `## Perp TA sweep run ${o.run}: whole-universe check (beside the pre-registered selection, which it does not change)`,
    '',
    `Universe per coin: the top cells by discovery excess t plus every Benjamini-Hochberg group representative, each recomputed and matched to its stored discovery record: ${coins.map((c) => `${c.asset} ${c.replicated}/${c.universe}${c.mismatched ? ` (${c.mismatched} did not replicate)` : ''}`).join(', ')}.`,
    `**N_eff = ${nEff}** clusters (ONC on weekly discovery P&L: ${coins.map((c) => `${c.asset} ${c.onc.k} of ${c.onc.n} cells, quality ${c.onc.quality}`).join(', ')}); N_raw = ${o.nRaw.toLocaleString()} cells tested (run 1 included). The clustered universe is only the top cells, so N_eff is a lower bound on the effective number of trials.`,
    '',
    `**SPA** (Hansen; daily net P&L after fees and funding against flat; stationary bootstrap, mean block ${o.block ?? 5} days, B = ${o.B ?? 2000}) over ${all.length} series (cluster medoids plus representatives):`,
    `- **validation** (${Tv} days, the test): p = ${sv.pC.toFixed(4)} (consistent), ${sv.pL.toFixed(4)} (lower), ${sv.pU.toFixed(4)} (upper); best ${fmtK(all[sv.best])}, t ${sv.stat.toFixed(2)}. StepM ${stepLine(sv, val)}`,
    `- discovery (${Td} days, in sample: these series were screened on these same days out of ${o.nRaw.toLocaleString()} cells, so these p-values do not adjust for that search and are not a test): p = ${sd.pC.toFixed(4)} (consistent), ${sd.pL.toFixed(4)} (lower), ${sd.pU.toFixed(4)} (upper); best ${fmtK(all[sd.best])}, t ${sd.stat.toFixed(2)}. StepM ${stepLine(sd, disc)}`,
    '',
    bs ? `**Deflated Sharpe** of the best discovery cell (${fmtK(bs)}; daily Sharpe ${dEff!.sr.toFixed(4)} over ${dEff!.T} days, skew ${dEff!.skew.toFixed(2)}, kurtosis ${dEff!.kurt.toFixed(1)}; variance of the medoids' Sharpe ${varSr.toExponential(3)}): DSR ${dEff!.dsr.toFixed(4)} at N = N_eff (${nEff}; expected best Sharpe under the null ${dEff!.sr0.toFixed(4)}), ${dRaw!.dsr.toFixed(4)} at N = N_raw (${dRaw!.sr0.toFixed(4)}). Its validation: ${vm.toFixed(2)} bps a day.` : 'No series.',
    ...coins.flatMap((c) => c.notes.map((n) => `- ${c.asset}: ${n}`)),
  ].join('\n');
  const out = { run: o.run, nEff, nRaw: o.nRaw, series: all.length, days: { discovery: Td, validation: Tv }, spaDiscoveryInSample: { ...sd, best: fmtK(all[sd.best]), stepm: Object.fromEntries(Object.entries(sd.stepm).map(([k, v]) => [k, v.map((i) => fmtK(all[i]))])) }, spaValidation: { ...sv, best: fmtK(all[sv.best]), stepm: Object.fromEntries(Object.entries(sv.stepm).map(([k, v]) => [k, v.map((i) => fmtK(all[i]))])) }, dsr: bs ? { cell: fmtK(bs), atNeff: dEff, atNraw: dRaw, varSr, validationBpsPerDay: vm } : null, onc: Object.fromEntries(coins.map((c) => [c.asset, c.onc])) };
  return { md, out };
}

// ---------------------------------------------------------------------------------------------------------------

function arg(k: string, d?: string): string | undefined { const i = process.argv.indexOf(`--${k}`); return i >= 0 && process.argv[i + 1] !== undefined && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : d; }

async function main(): Promise<void> {
  const mode = process.argv[2];
  const log = (m: string) => console.log(`[perp-ta-study] ${m}`);
  if (mode === 'coin') {
    const g = readGrid(arg('data')!);
    const lines = zlib.gunzipSync(fs.readFileSync(arg('cells')!)).toString().split('\n').filter(Boolean);
    const header = JSON.parse(lines[0]) as { seal: string; validFrom: string; costs: Costs; asset: string };
    if (header.asset !== g.asset) throw new Error(`cells are for ${header.asset}, grid is ${g.asset}`);
    const cells = lines.slice(1).map((l) => JSON.parse(l) as CellRec);
    const cands = arg('candidates') ? JSON.parse(zlib.gunzipSync(fs.readFileSync(arg('candidates')!)).toString()) as Candidate[] : [];
    const reps = new Set(cands.filter((c) => c.a === g.asset && !c.diagnostic && !c.why.some((w) => w.startsWith('not a discovery'))).map(keyOf));
    const modules = arg('modules', 'true') === 'false' ? false as const : { history: arg('history'), forecasts: arg('forecasts'), cacheDir: arg('module-cache') };
    const r = studyCoin(g, cells, header, reps, { top: +arg('top', '5000')!, anyBlocks: process.argv.includes('--any-blocks'), modules, log });
    const file = arg('out')!;
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, zlib.gzipSync(JSON.stringify(r)));
    log(`${g.asset}: wrote ${file} (${r.series.length} series, ${r.onc.k} clusters)`);
    return;
  }
  if (mode === 'report') {
    const dir = arg('in')!, outDir = arg('out', 'report')!;
    const coins = fs.readdirSync(dir, { recursive: true }).map(String).filter((f) => /study-[A-Z0-9]+\.json\.gz$/.test(f)).map((f) => JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(dir, f))).toString()) as StudyCoin);
    if (!coins.length) throw new Error('no study-<coin>.json.gz in --in');
    const r = studyReport(coins, { run: arg('run', '?')!, nRaw: +arg('n-raw', '0')!, B: +arg('b', '2000')!, block: +arg('block', '5')! });
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(path.join(outDir, 'summary.md'), r.md + '\n');
    fs.writeFileSync(path.join(outDir, 'study.json'), JSON.stringify(r.out, null, 1));
    const now = new Date();
    const row = { thread: 'perp-ta-rulebook', kind: 'study', run: process.env.GITHUB_RUN_ID ?? 'local', sha: process.env.GITHUB_SHA ?? '', of_sweep_run: r.out.run, at_utc: now.toISOString(), at_eastern: now.toLocaleString('en-US', { timeZone: 'America/New_York', hour12: false }), n_raw: r.out.nRaw, n_eff: r.out.nEff, spa_discovery_p_in_sample_screened: (r.out.spaDiscoveryInSample as { pC: number }).pC, spa_validation_p: (r.out.spaValidation as { pC: number }).pC, dsr: r.out.dsr, doge_excluded: true, blocks: { discovery: '< 2024-01-01', validation: '2024-01-01 .. 2025-06-30', sealed: '>= 2025-07-01 (not read)' } };
    fs.writeFileSync(path.join(outDir, 'registry.jsonl'), JSON.stringify(row) + '\n');
    console.log(r.md);
    return;
  }
  console.log('usage: perpTaStudy.ts coin|report (see the header)');
  process.exitCode = 1;
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) main().catch((e) => { console.error(e); process.exitCode = 1; });
