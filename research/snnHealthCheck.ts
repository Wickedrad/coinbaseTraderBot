// SNN health check (research only): can the crypto SNN's direction head learn a coin-direction label without the mid
// anchor? The head already exists in every crypto column (X-15m, X-60m): p = sigmoid(wf . phi) on the column's state
// features, no anchor, no clip, weights starting at 0, labelled once a minute with y = [index(T+H) > index(T)]. With no
// Kalshi contracts on the replayed days, nothing else learns. This walks one fresh network per coin through Binance spot
// history (index-only replays, no contracts) and, every minute, runs shadow readouts on the head's own features:
//   prodShadow  the production settings: must reproduce the head's p (the max abs difference is reported);
//   nofade      tauC 1e12 (almost all of each update kept; production keeps ~6.7%, half-life ~2.6 h);
//   control     a POSITIVE CONTROL with the production settings and the label y' = [px(T) > px(T-H)], which the
//               inputs nearly determine (ret_h_z encodes the same move from a bar close and a 5 s feature cache; the
//               report gives the sign agreement): a learner that cannot learn this cannot learn anything.
// The verdict rule is pre-registered (snn-lead/HC-preregistration.md): see verdict() and overall() below.
//
//   fetch   --from D --to D --history H --replay R [--assets BTC,ETH,SOL,XRP]
//           downloads (serially: binanceVision.ts writes one shared manifest) and builds ONE 4-coin replay, so
//           USDT.D (driven by BTC's prints) is what live sees in every coin's process.
//   run     --assets A --from D --to D --replay R --out O [--minutes 250] [--seed N] [--stage S5]
//           replays R with the three other coins (and DOGE) skipped; writes O/rows-*.jsonl.gz, O/dir-*.jsonl.gz,
//           O/cum.json, O/weights.json, O/meta.json, chunk by chunk.
//   report  --in DIR --out research/out/snn-health.md [--json F] [--public F] [--decide-from 2026-06-01]
//           [--decide-to 2026-07-31] [--assets BTC,ETH,SOL,XRP]
//
// Public output (this repository is public): stdout of `report` carries the verdict line and headline counts only.
// The markdown, the JSON and the per-coin logs belong on Drive (derived/snn-health/<run>), never in a public artifact.

import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import { loadCalendar } from '../bot/model/calendar';
import { N_BASE, N_POOL, type Column } from '../bot/snn/column';
import { logit } from '../bot/snn/formulas';
import { columnHorizonSec, popSpec, type LeadInputs } from '../bot/snn/inputs';
import type { SnnCheckpoint, SnnNetwork } from '../bot/snn/network';
import type { SnnParams, Stage } from '../bot/snn/params';
import { Readout } from '../bot/snn/readout';
import { downloadBinance } from './history/binanceVision';
import { buildHistoryReplay } from './history/historyReplay';
import { addDays } from './historyWalkState';
import { trainChunks, trainParams } from './snnHistoryTrain';
import { replaySnn } from './snnReplay';
import { rng } from './stats';

export const HC_ASSETS = ['BTC', 'ETH', 'SOL', 'XRP'];
/** Pre-registered rule (snn-lead/HC-preregistration.md, written 2026-11-12 before any run). */
export const RULE = { sdState: 0.05, slopeLo: 0.7, slopeHi: 1.3, aucLo: 0.5, skillLo: 0, minDays: 28, iters: 1000 } as const;
export const DECIDE_FROM = '2026-06-01';
export const DECIDE_TO = '2026-07-31';
/** Research-only override of the nofade shadow: k = 1/tauC + eps ~ eps, so eps/k ~ 1 of each update is kept. */
export const NOFADE_TAU_C = 1e12;

const argOf = (argv: string[], k: string, d = '') => { const i = argv.indexOf(`--${k}`); return i > 0 && argv[i + 1] !== undefined ? argv[i + 1] : d; };
const arg = (k: string, d = '') => argOf(process.argv, k, d);
const dayOf = (t: number) => new Date(t).toISOString().slice(0, 10);
const assetOf = (k: string) => k.slice(0, k.lastIndexOf('-'));
const r7 = (x: number) => Math.round(x * 1e7) / 1e7;
const r4 = (x: number) => Math.round(x * 1e4) / 1e4;

// ---- pure statistics ------------------------------------------------------------------------------------------

/** Quantile with linear interpolation between order statistics (type 7). */
export function quantile(sorted: ArrayLike<number>, q: number): number {
  const n = sorted.length;
  if (!n) return NaN;
  const h = (n - 1) * q, lo = Math.floor(h), hi = Math.ceil(h);
  return sorted[lo] + (h - lo) * (sorted[hi] - sorted[lo]);
}

export interface Spread { n: number; meanAbsPp: number; sd: number; p10: number; p50: number; p90: number; a10: number; a50: number; a90: number }
/** Spread of the predictions: mean |p - 0.5| (pp), the sample sd of p, and the 10/50/90th percentiles of p and of |p - 0.5| (pp). */
export function spreadStats(p: ArrayLike<number>): Spread {
  const n = p.length;
  if (!n) return { n, meanAbsPp: NaN, sd: NaN, p10: NaN, p50: NaN, p90: NaN, a10: NaN, a50: NaN, a90: NaN };
  let s = 0, a = 0;
  for (let i = 0; i < n; i++) { s += p[i]; a += Math.abs(p[i] - 0.5); }
  const m = s / n;
  let v = 0;
  for (let i = 0; i < n; i++) v += (p[i] - m) ** 2;
  const ps = Float64Array.from(p).sort(), as = Float64Array.from(p, (x) => 100 * Math.abs(x - 0.5)).sort();
  return { n, meanAbsPp: (100 * a) / n, sd: n > 1 ? Math.sqrt(v / (n - 1)) : 0, p10: quantile(ps, 0.1), p50: quantile(ps, 0.5), p90: quantile(ps, 0.9), a10: quantile(as, 0.1), a50: quantile(as, 0.5), a90: quantile(as, 0.9) };
}

export interface Ci { est: number; lo: number; hi: number; n: number; days: number }

/** Percentile CI of a ratio of day-summed quantities, resampling whole days (day-block bootstrap). */
function dayRatioCi(num: Map<string, number>, den: Map<string, number>, f: (a: number, b: number) => number, iters: number, seed: number): { lo: number; hi: number } {
  const days = [...den.keys()];
  if (days.length < 2) return { lo: NaN, hi: NaN };
  const A = days.map((d) => num.get(d) ?? 0), B = days.map((d) => den.get(d) ?? 0);
  const r = rng(seed), out: number[] = [];
  for (let it = 0; it < iters; it++) {
    let a = 0, b = 0;
    for (let j = 0; j < days.length; j++) { const k = Math.floor(r() * days.length); a += A[k]; b += B[k]; }
    const v = f(a, b);
    if (Number.isFinite(v)) out.push(v);
  }
  out.sort((x, y) => x - y);
  return { lo: quantile(out, 0.025), hi: quantile(out, 0.975) };
}

export interface SlopeOpts { group?: ArrayLike<string>; day?: ArrayLike<string>; intercept?: boolean; iters?: number; seed?: number }
/** Least-squares slope of e on x. With `intercept` (the default) both are demeaned within each `group` (fixed effects;
 *  one group when none is given); without it the fit goes through the origin. 95% CI from a day-block bootstrap over
 *  `day` (groups must nest in days, e.g. column x day). */
export function slopeB(x: ArrayLike<number>, e: ArrayLike<number>, o: SlopeOpts = {}): Ci {
  const n = x.length, ic = o.intercept !== false;
  const gx = new Map<string, { sx: number; se: number; n: number }>();
  if (ic) for (let i = 0; i < n; i++) { const g = o.group?.[i] ?? ''; const s = gx.get(g) ?? { sx: 0, se: 0, n: 0 }; s.sx += x[i]; s.se += e[i]; s.n++; gx.set(g, s); }
  const sxy = new Map<string, number>(), sxx = new Map<string, number>();
  for (let i = 0; i < n; i++) {
    const g = gx.get(o.group?.[i] ?? ''), d = o.day?.[i] ?? '';
    const xx = ic ? x[i] - g!.sx / g!.n : x[i], ee = ic ? e[i] - g!.se / g!.n : e[i];
    sxy.set(d, (sxy.get(d) ?? 0) + xx * ee); sxx.set(d, (sxx.get(d) ?? 0) + xx * xx);
  }
  let a = 0, b = 0;
  for (const [d, v] of sxx) { b += v; a += sxy.get(d)!; }
  const ci = dayRatioCi(sxy, sxx, (u, v) => (v > 0 ? u / v : NaN), o.iters ?? RULE.iters, o.seed ?? 1);
  return { est: b > 0 ? a / b : NaN, ...ci, n, days: sxx.size };
}

/** Within-group sd: the pooled sd of x around each group's mean (x itself when no group is given). */
export function withinSd(x: ArrayLike<number>, group?: ArrayLike<string>): number {
  const g = new Map<string, { s: number; n: number }>();
  for (let i = 0; i < x.length; i++) { const k = group?.[i] ?? ''; const v = g.get(k) ?? { s: 0, n: 0 }; v.s += x[i]; v.n++; g.set(k, v); }
  let ss = 0;
  for (let i = 0; i < x.length; i++) { const v = g.get(group?.[i] ?? '')!; ss += (x[i] - v.s / v.n) ** 2; }
  const dof = x.length - g.size;
  return dof > 0 ? Math.sqrt(ss / dof) : NaN;
}

/** AUC (Mann-Whitney, ties count half) stratified by `group`: the share of correctly ordered (y=1, y=0) pairs taken
 *  within the same group, so a per-group constant (a bias) carries no credit. 95% CI by day-block bootstrap. */
export function auc(p: ArrayLike<number>, y: ArrayLike<number>, o: { group?: ArrayLike<string>; day?: ArrayLike<string>; iters?: number; seed?: number } = {}): Ci {
  const by = new Map<string, number[]>();
  for (let i = 0; i < p.length; i++) { const g = `${o.day?.[i] ?? ''}\u0000${o.group?.[i] ?? ''}`; let a = by.get(g); if (!a) by.set(g, (a = [])); a.push(i); }
  const C = new Map<string, number>(), P = new Map<string, number>();
  for (const [g, idx] of by) {
    idx.sort((a, b) => p[a] - p[b]);
    let negBelow = 0, c = 0, npos = 0, nneg = 0;
    for (let i = 0; i < idx.length;) {
      let j = i, bp = 0, bn = 0;
      while (j < idx.length && p[idx[j]] === p[idx[i]]) { if (y[idx[j]]) bp++; else bn++; j++; }
      c += bp * negBelow + 0.5 * bp * bn;
      negBelow += bn; npos += bp; nneg += bn; i = j;
    }
    const d = g.slice(0, g.indexOf('\u0000'));
    C.set(d, (C.get(d) ?? 0) + c); P.set(d, (P.get(d) ?? 0) + npos * nneg);
  }
  let c = 0, q = 0;
  for (const [d, v] of P) { q += v; c += C.get(d)!; }
  const ci = dayRatioCi(C, P, (u, v) => (v > 0 ? u / v : NaN), o.iters ?? RULE.iters, o.seed ?? 2);
  return { est: q > 0 ? c / q : NaN, ...ci, n: p.length, days: P.size };
}

/** Brier skill 1 - B(p)/B(base) against a reference forecast, 95% CI by day-block bootstrap. */
export function brierSkill(p: ArrayLike<number>, base: ArrayLike<number>, y: ArrayLike<number>, o: { day?: ArrayLike<string>; iters?: number; seed?: number } = {}): Ci {
  const bp = new Map<string, number>(), bb = new Map<string, number>();
  for (let i = 0; i < p.length; i++) { const d = o.day?.[i] ?? ''; bp.set(d, (bp.get(d) ?? 0) + (p[i] - y[i]) ** 2); bb.set(d, (bb.get(d) ?? 0) + (base[i] - y[i]) ** 2); }
  let a = 0, b = 0;
  for (const [d, v] of bb) { b += v; a += bp.get(d)!; }
  const ci = dayRatioCi(bp, bb, (u, v) => (v > 0 ? 1 - u / v : NaN), o.iters ?? RULE.iters, o.seed ?? 3);
  return { est: b > 0 ? 1 - a / b : NaN, ...ci, n: p.length, days: bb.size };
}

export interface LabelRow { k: string; t: number; y: number }
const horizonMs = (k: string) => columnHorizonSec(k) * 1000;

/** Rows' indices in (column, time) order. */
function byColumnTime(rows: LabelRow[]): Map<string, number[]> {
  const m = new Map<string, number[]>();
  rows.forEach((r, i) => { let a = m.get(r.k); if (!a) m.set(r.k, (a = [])); a.push(i); });
  for (const a of m.values()) a.sort((i, j) => rows[i].t - rows[j].t);
  return m;
}

/** Prequential up-rate per column from a Laplace (1, 2) prior. A label joins the counts only once it has matured
 *  (its tag time + H <= the current tag time): research/snnReplay.ts directionRows counts labels in log order, up to
 *  H after the tag, and must not be used as this baseline. */
export function prequentialBase(rows: LabelRow[], H: (k: string) => number = horizonMs): number[] {
  const out = new Array<number>(rows.length);
  for (const [k, idx] of byColumnTime(rows)) {
    const h = H(k);
    let up = 1, n = 2, q = 0;
    for (const i of idx) {
      while (q < idx.length && rows[idx[q]].t + h <= rows[i].t) { up += rows[idx[q]].y; n++; q++; }
      out[i] = up / n;
    }
  }
  return out;
}

export type PxMap = Map<string, Map<number, number>>;
/** sign(px[t] - px[t - L]) from minute-mark prices; 0 when either is missing or they are equal. */
export function momentumSign(px: PxMap, asset: string, t: number, Lmin: number): -1 | 0 | 1 {
  const m = px.get(asset), a = m?.get(t), b = m?.get(t - Lmin * 60_000);
  if (!(a! > 0) || !(b! > 0) || a === b) return 0;
  return a! > b! ? 1 : -1;
}

/** Prequential conditional up-rate given the sign of the last L minutes' move: p = (up[col,s] + 1) / (n[col,s] + 2) over
 *  matured labels only; s = 0 or a missing price falls back to the prequential base rate. */
export function prequentialMomentum(rows: LabelRow[], px: PxMap, Lmin: number, H: (k: string) => number = horizonMs): number[] {
  const base = prequentialBase(rows, H);
  const out = new Array<number>(rows.length);
  for (const [k, idx] of byColumnTime(rows)) {
    const h = H(k), a = assetOf(k);
    const up = { 1: 0, [-1]: 0 } as Record<number, number>, n = { 1: 0, [-1]: 0 } as Record<number, number>;
    const sg = idx.map((i) => momentumSign(px, a, rows[i].t, Lmin));
    let q = 0;
    idx.forEach((i, j) => {
      while (q < j && rows[idx[q]].t + h <= rows[i].t) { const s = sg[q]; if (s) { up[s] += rows[idx[q]].y; n[s]++; } q++; }
      const s = sg[j];
      out[i] = s ? (up[s] + 1) / (n[s] + 2) : base[i];
    });
  }
  return out;
}

/** Plain sign momentum: predict up iff px[t] > px[t - L]; ties and missing prices excluded. */
export function signMomentumAccuracy(rows: LabelRow[], px: PxMap, Lmin: number): { acc: number; n: number } {
  let hit = 0, n = 0;
  for (const r of rows) { const s = momentumSign(px, assetOf(r.k), r.t, Lmin); if (!s) continue; n++; if ((s > 0 ? 1 : 0) === r.y) hit++; }
  return { acc: n ? hit / n : NaN, n };
}

/** Accuracy of sign(p - 0.5) against y over rows with p != 0.5. */
export function signAccuracy(p: ArrayLike<number>, y: ArrayLike<number>): { acc: number; n: number } {
  let hit = 0, n = 0;
  for (let i = 0; i < p.length; i++) { if (p[i] === 0.5) continue; n++; if ((p[i] > 0.5 ? 1 : 0) === y[i]) hit++; }
  return { acc: n ? hit / n : NaN, n };
}

// ---- channels and dead inputs -----------------------------------------------------------------------------------

/** L0 channel name: 8 delta channels (6, 7 follow the contract mid), then 8 bands per population-coded input. */
export function chanName(i: number, lead?: LeadInputs): string {
  if (i < 8) return `delta${i}`;
  const pop = popSpec('crypto', lead);
  return `${pop[(i - 8) >> 3].name}:b${(i - 8) & 7}`;
}

/** Head features that are zero by design for the direction call (d = 0, tauFrac = 0): entries 1-5, the d-scaled pool
 *  block, and the extras plus padding (proxies / Wilson-Cowan / Izhikevich off in S5). */
export function phiZeroByDesign(nE: number, nL1: number, nFeat: number): Set<number> {
  const s = new Set<number>([1, 2, 3, 4, 5]);
  for (let i = N_BASE + nE + nL1; i < nFeat; i++) s.add(i);
  return s;
}
/** The inverse of twoSpeedStep over dt (bot/snn/formulas.ts): the fast weight before one relaxation, from the pair after it. */
export function unrelaxWf(wf: number, ws: number, tauC: number, eps: number, dt: number): number {
  const k = 1 / tauC + eps, e = Math.exp(-k * dt);
  const d0 = (wf - ws) / e;
  return ws - (eps * d0 * (1 - e)) / k + d0;
}

export const phiBlocks = (nE: number, nL1: number) => ({ E: [N_BASE, N_BASE + nE] as const, L1: [N_BASE + nE, N_BASE + nE + nL1] as const, pool: [N_BASE + nE + nL1, N_BASE + nE + nL1 + N_POOL] as const });

export interface InputStat { n: number; mean: number; m2: number }
export interface DeadClasses {
  /** Dead because the source is absent in the replay (no finite input ever): expected. */
  absent: string[];
  /** Dead with an input that is finite but never varies: unexpected. */
  flatInput: string[];
  /** The input varies but this band never fires: reported, not a failure. */
  unusedBand: string[];
  /** Dead and not explained by an absent source (flat inputs, dead price deltas): the list to look at. */
  unexpected: string[];
  live: number;
  deadInputs: { absent: string[]; flat: string[] };
}
/** Classify dead L0 channels from the data (no fixed list): a channel is dead when it never fired above 1e-4. */
export function classifyDead(chanActive: ArrayLike<number>, inputs: Record<string, InputStat | undefined>, lead?: LeadInputs): DeadClasses {
  const out: DeadClasses = { absent: [], flatInput: [], unusedBand: [], unexpected: [], live: 0, deadInputs: { absent: [], flat: [] } };
  const state = (name: string) => { const s = inputs[name]; return !s || s.n === 0 ? 'absent' : s.n > 1 && s.m2 / (s.n - 1) > 0 ? 'varies' : 'flat'; };
  for (let i = 0; i < chanActive.length; i++) {
    if (chanActive[i] > 0) { out.live++; continue; }
    const name = chanName(i, lead);
    const input = i < 6 ? undefined : i < 8 ? 'mid' : name.slice(0, name.lastIndexOf(':'));
    if (!input) { out.unexpected.push(name); continue; }
    const s = state(input);
    if (s === 'absent') out.absent.push(name);
    else if (s === 'flat') { out.flatInput.push(name); out.unexpected.push(name); }
    else out.unusedBand.push(name);
  }
  for (const p of popSpec('crypto', lead)) { const s = state(p.name); if (s === 'absent') out.deadInputs.absent.push(p.name); else if (s === 'flat') out.deadInputs.flat.push(p.name); }
  return out;
}

// ---- verdict -------------------------------------------------------------------------------------------------------

export interface ArmStats { n: number; sdState: number; slope: Ci; auc: Ci; skill: Ci }
/** Pre-registered: an arm LEARNS iff the state part varies (sd >= 0.05 logits, within column x day), the slope of y on p
 *  with column x day fixed effects is in [0.7, 1.3] with its CI lower bound > 0, the stratified AUC's CI lower bound
 *  > 0.5, and the Brier skill vs the matured base rate has its CI lower bound > 0. */
export function verdict(s: ArmStats): { pass: boolean; fails: string[] } {
  const fails: string[] = [];
  if (!(s.n > 0)) fails.push('no rows');
  if (!(s.sdState >= RULE.sdState)) fails.push(`state sd ${fmt(s.sdState, 3)} < ${RULE.sdState}`);
  if (!(s.slope.est >= RULE.slopeLo && s.slope.est <= RULE.slopeHi)) fails.push(`slope ${fmt(s.slope.est, 2)} outside [${RULE.slopeLo}, ${RULE.slopeHi}]`);
  if (!(s.slope.lo > 0)) fails.push(`slope CI lower ${fmt(s.slope.lo, 2)} <= 0`);
  if (!(s.auc.lo > RULE.aucLo)) fails.push(`AUC CI lower ${fmt(s.auc.lo, 4)} <= 0.5`);
  if (!(s.skill.lo > RULE.skillLo)) fails.push(`skill vs base CI lower ${fmt(s.skill.lo, 5)} <= 0`);
  return { pass: fails.length === 0, fails };
}

export type Overall = 'INCONCLUSIVE' | 'LEARNING BROKEN' | 'CAN LEARN, DIRECTION NOT PREDICTABLE' | 'HEAD LEARNS DIRECTION';
/** Coverage first (any expected column with < 28 decision-window days: INCONCLUSIVE), then the control, then the head. */
export function overall(head: { pass: boolean }, control: { pass: boolean }, coverage: { column: string; days: number }[]): Overall {
  if (!coverage.length || coverage.some((c) => !(c.days >= RULE.minDays))) return 'INCONCLUSIVE';
  if (!control.pass) return 'LEARNING BROKEN';
  return head.pass ? 'HEAD LEARNS DIRECTION' : 'CAN LEARN, DIRECTION NOT PREDICTABLE';
}

const fmt = (x: number, d: number) => (Number.isFinite(x) ? x.toFixed(d) : 'NaN');

// ---- the per-minute sampler (shadow readouts) -------------------------------------------------------------------

export interface SampleRow {
  k: string; t: number; x?: number;
  /** Head p at T (its tag), the prodShadow, nofade and control shadows' p, the control label (absent on a tie). */
  p?: number; s?: number; n?: number; c?: number; yc?: 0 | 1;
  /** Biases at prediction time: the head's own (hb: its wf[0] with the relaxation after T's tag undone), the
   *  prodShadow's, nofade's and the control's; w0 is the head's wf[0] as read at T (after that relaxation). */
  hb?: number; b?: number; nb?: number; cb?: number; w0: number;
  /** The column's ret_h_z input at the tag (the control label's sign agreement). */
  rz?: number;
  G: number; fr: 0 | 1; rc: 0 | 1; fb?: string[]; eta: number;
  /** G's drivers: fSat, rhoHat (rateE / ref - 1), errZ, dBrier; mean E and L1 head features. */
  fs: number; rho: number; ez: number; db: number; rE: number; rL1: number;
}
export interface DirRow { k: string; t: number; p: number; y: 0 | 1 }

interface Pend { phi: Float32Array; s: number; n: number; c: number; yc?: 0 | 1 }
interface Shadows { ps: Readout; nf: Readout; ctl: Readout; pend: Map<number, Pend> }
export interface CumCol {
  minutes: number; chanActive: number[]; chanMean: number[]; chanM2: number[];
  inputs: Record<string, InputStat>; phiN: number; phiMean: number[]; phiM2: number[]; phiMax: number[];
}

const welford = (s: InputStat, v: number) => { s.n++; const d = v - s.mean; s.mean += d / s.n; s.m2 += d * (v - s.mean); };

export class HealthSampler {
  private net?: SnnNetwork;
  private dirIdx = 0;
  private steps0?: number;
  private readonly upd = new Map<string, number>();
  readonly shadows = new Map<string, Shadows>();
  private readonly px = new Map<string, Map<number, number>>();
  rows: SampleRow[] = [];
  dir: DirRow[] = [];
  /** |prodShadow p - head p| over every tag compared. */
  diff = { max: 0, sum: 0, n: 0 };
  /** Head labels the prodShadow and nofade could not take (no pending tag: a tag inside a replay catch-up). */
  skipped = 0;
  readonly cum = new Map<string, CumCol>();

  constructor(readonly p: SnnParams, readonly o: { nofadeTauC?: number; cum?: boolean } = {}) {}

  private opts(tauC: number) {
    return { eta: this.p.dirEta, cap: this.p.dirCap, tauC, eps: this.p.eps, tagsPerContract: 1, maxTagged: 1, traceTauSec: this.p.traceTauSec, useTags: true };
  }

  private ensure(c: Column): Shadows {
    let s = this.shadows.get(c.key);
    if (!s) {
      s = { ps: new Readout(c.nFeat, this.opts(this.p.tauC)), nf: new Readout(c.nFeat, this.opts(this.o.nofadeTauC ?? NOFADE_TAU_C)), ctl: new Readout(c.nFeat, this.opts(this.p.tauC)), pend: new Map() };
      this.shadows.set(c.key, s);
    }
    return s;
  }

  private relax(times: number): void {
    for (let i = 0; i < times; i++) for (const s of this.shadows.values()) for (const r of [s.ps, s.nf, s.ctl]) r.relax(this.p.slowEverySec);
  }

  /** Did the head learn from the labels it took since the last call? (Readout.updates counts learned labels only.) */
  private learnFlags(net: SnnNetwork, fresh: Map<string, number>): Map<string, boolean> {
    const out = new Map<string, boolean>();
    for (const [k, ro] of net.dirReadouts) {
      const d = ro.updates - (this.upd.get(k) ?? ro.updates);
      out.set(k, fresh.get(k) ? d > 0 : !net.learningFrozen);
    }
    return out;
  }

  /** The head's new labels (net.dirLog) go to the prodShadow and nofade shadows, with the head's own label. */
  private labels(net: SnnNetwork, T: number): Map<string, boolean> {
    if (net !== this.net) { this.net = net; this.dirIdx = 0; }
    const log = net.dirLog ?? [];
    const fresh = new Map<string, number>();
    for (let i = this.dirIdx; i < log.length; i++) fresh.set(log[i].key, (fresh.get(log[i].key) ?? 0) + 1);
    const learn = this.learnFlags(net, fresh);
    for (; this.dirIdx < log.length; this.dirIdx++) {
      const e = log[this.dirIdx];
      this.dir.push({ k: e.key, t: e.ts, p: e.p, y: e.y });
      const sh = this.shadows.get(e.key), pd = sh?.pend.get(e.ts), c = net.columns.get(e.key);
      if (!sh || !pd || !c) { this.skipped++; continue; }
      const scale = 1 - this.p.govDelta * c.G, res = e.y ? 'yes' : 'no', L = learn.get(e.key) ?? false;
      sh.ps.tag('dir', 'greater', 'strike', pd.phi, pd.s, e.ts); sh.ps.settle('dir', res, T, scale, L);
      sh.nf.tag('dir', 'greater', 'strike', pd.phi, pd.n, e.ts); sh.nf.settle('dir', res, T, scale, L);
    }
    for (const [k, ro] of net.dirReadouts) this.upd.set(k, ro.updates);
    return learn;
  }

  /** Labels taken after the last sampled minute of a chunk (before its network is dropped). */
  drain(net: SnnNetwork): void { this.labels(net, net.lastTs); }

  /** onProgress(T, net): once a minute, after the network stepped to T. */
  sample(T: number, net: SnnNetwork): void {
    const slow = this.p.slowEverySec, s1 = net.steps;
    // The head's readouts relax every `slow` steps, after that step's labels and tags: the shadows follow the same
    // schedule (the relaxations of the steps before T first, T's own after the tag).
    if (this.steps0 !== undefined) this.relax(Math.max(0, Math.floor((s1 - 1) / slow) - Math.floor(this.steps0 / slow)));
    const learn = this.labels(net, T);
    const frozen = net.learningFrozen;
    const freezeBy = net.health.breaches.filter((b) => b.action === 'freeze').map((b) => b.metric);
    const { E, L1 } = phiBlocks(this.p.nE, this.p.nL1);
    const refE = net.health.ref?.rateE;
    for (const c of net.sortedColumns()) {
      const sh = this.ensure(c), H = c.horizonSec * 1000, price = c.lastSpot;
      const scale = 1 - this.p.govDelta * c.G, L = learn.get(c.key) ?? !frozen;
      let pm = this.px.get(c.asset);
      if (!pm) this.px.set(c.asset, (pm = new Map()));
      if (price > 0) pm.set(T, price);
      // Control labels mature as the head's do (tag + H), with y' fixed at the tag.
      for (const [ts, pd] of sh.pend) {
        if (ts + H > T) break;
        if (pd.yc !== undefined) { sh.ctl.tag('dir', 'greater', 'strike', pd.phi, pd.c, ts); sh.ctl.settle('dir', pd.yc ? 'yes' : 'no', T, scale, L); }
        sh.pend.delete(ts);
      }
      const head = net.dirReadouts.get(c.key)!, tags = net.dirTags.get(c.key) ?? [], tg = tags[tags.length - 1];
      const phi = c.features(0, 0, net.extras(c));
      let eSum = 0, lSum = 0;
      for (let i = E[0]; i < E[1]; i++) eSum += phi[i];
      for (let i = L1[0]; i < L1[1]; i++) lSum += phi[i];
      const row: SampleRow = {
        k: c.key, t: T, ...(price > 0 ? { x: price } : {}), w0: r7(head.wf[0]), G: r4(c.G), fr: frozen ? 1 : 0, rc: frozen && !freezeBy.length ? 1 : 0,
        ...(freezeBy.length ? { fb: freezeBy } : {}), eta: r4(frozen ? 0 : 1 - this.p.govDelta * c.G),
        fs: r4(c.fSat), rho: r4(refE && refE > 0 ? Math.max(0, c.rateE / refE - 1) : 0), ez: r4(c.errZ), db: r4(net.readouts.get(c.key)?.brierDeterioration() ?? 0),
        rE: r7(eSum / (E[1] - E[0])), rL1: r7(lSum / (L1[1] - L1[0])),
      };
      if (tg && tg.ts === T) {
        const s = sh.ps.predict(phi), n = sh.nf.predict(phi), cc = sh.ctl.predict(phi);
        // The head relaxed after this step's tag when s1 is a multiple of slow: undo that one step for its bias at the call.
        const hb = s1 % slow === 0 ? unrelaxWf(head.wf[0], head.ws[0], this.p.tauC, this.p.eps, slow) : head.wf[0];
        const rz = net.inputOf(c).values?.ret_h_z;
        const d = Math.abs(s - tg.p);
        this.diff.max = Math.max(this.diff.max, d); this.diff.sum += d; this.diff.n++;
        const p0 = pm.get(T - H);
        const yc: 0 | 1 | undefined = price > 0 && p0! > 0 && price !== p0 ? (price > p0! ? 1 : 0) : undefined;
        sh.pend.set(T, { phi: Float32Array.from(phi), s, n, c: cc, ...(yc !== undefined ? { yc } : {}) });
        Object.assign(row, { p: r7(tg.p), s: r7(s), n: r7(n), c: r7(cc), ...(yc !== undefined ? { yc } : {}), hb: r7(hb), b: r7(sh.ps.wf[0]), nb: r7(sh.nf.wf[0]), cb: r7(sh.ctl.wf[0]), ...(typeof rz === 'number' && Number.isFinite(rz) ? { rz: r4(rz) } : {}) });
      }
      this.rows.push(row);
      if (this.o.cum !== false) this.accumulate(c, net, phi);
      if (T % 3_600_000 === 0) for (const t of pm.keys()) { if (t < T - 2 * 3_600_000) pm.delete(t); else break; }
    }
    if (s1 % slow === 0) this.relax(1);
    this.steps0 = s1;
  }

  private accumulate(c: Column, net: SnnNetwork, phi: Float64Array): void {
    let a = this.cum.get(c.key);
    const nL0 = c.rate0.length, nF = phi.length;
    if (!a) this.cum.set(c.key, (a = { minutes: 0, chanActive: new Array(nL0).fill(0), chanMean: new Array(nL0).fill(0), chanM2: new Array(nL0).fill(0), inputs: {}, phiN: 0, phiMean: new Array(nF).fill(0), phiM2: new Array(nF).fill(0), phiMax: new Array(nF).fill(0) }));
    a.minutes++;
    for (let i = 0; i < nL0; i++) {
      const v = c.rate0[i];
      if (v > 1e-4) a.chanActive[i]++;
      const d = v - a.chanMean[i]; a.chanMean[i] += d / a.minutes; a.chanM2[i] += d * (v - a.chanMean[i]);
    }
    const vals = net.inputOf(c).values ?? {};
    for (const p of popSpec('crypto', this.p.leadInputs)) {
      const s = (a.inputs[p.name] ??= { n: 0, mean: 0, m2: 0 });
      const v = vals[p.name];
      if (typeof v === 'number' && Number.isFinite(v)) welford(s, v);
    }
    a.phiN++;
    for (let i = 0; i < nF; i++) {
      const v = phi[i], d = v - a.phiMean[i];
      a.phiMean[i] += d / a.phiN; a.phiM2[i] += d * (v - a.phiMean[i]);
      if (Math.abs(v) > a.phiMax[i]) a.phiMax[i] = Math.abs(v);
    }
  }

  take(): { rows: SampleRow[]; dir: DirRow[] } {
    const out = { rows: this.rows, dir: this.dir };
    this.rows = []; this.dir = [];
    return out;
  }
}

// ---- subcommands ---------------------------------------------------------------------------------------------------

function checkDay(d: string, what: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) throw new Error(`--${what} YYYY-MM-DD`);
  return d;
}
const gzLines = (rows: object[]) => zlib.gzipSync(rows.map((r) => JSON.stringify(r)).join('\n') + (rows.length ? '\n' : ''));
function readGz<T>(f: string): T[] {
  return zlib.gunzipSync(fs.readFileSync(f)).toString('utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l) as T);
}

async function fetchCmd() {
  const from = checkDay(arg('from'), 'from'), to = checkDay(arg('to'), 'to');
  const hist = arg('history'), rep = arg('replay');
  if (!hist || !rep) throw new Error('--history and --replay');
  const assets = arg('assets', HC_ASSETS.join(',')).split(',').map((x) => x.trim().toUpperCase()).filter(Boolean);
  if (assets.includes('DOGE')) throw new Error('no DOGE');
  const warm = addDays(from, -1), month = (d: string) => d.slice(0, 7);
  // Serial on purpose: binanceVision.ts keeps one manifest per source, so parallel downloads would race on it.
  const dl = async (intervals: ('1m' | '15m' | '1h' | '1d')[], f: string, source?: string) =>
    (await downloadBinance({ out: hist, assets, intervals, markets: ['spot'], source, fromMonth: month(f), toMonth: month(to), log: () => undefined })).reduce((s, x) => s + x.fetched, 0);
  const n1 = await dl(['1m'], warm, 'binance-1m');
  const n2 = await dl(['15m', '1h'], addDays(warm, -14));
  const n3 = await dl(['1d'], addDays(warm, -310));
  const built = await buildHistoryReplay({ historyDir: hist, outDir: rep, assets, fromDay: warm, toDay: to, synthetic: false, log: () => undefined });
  fs.writeFileSync(path.join(rep, 'health-sources.json'), JSON.stringify({ assets: built.assets, dominance: built.dominance, notes: built.notes, days: built.days, written: built.written }));
  console.log(`[health] fetch: ${n1 + n2 + n3} archive(s) fetched; replay ${built.written} day(s) built, ${built.skipped} kept, ${built.assets.length}/${assets.length} coins`);
}

async function runCmd() {
  const from = checkDay(arg('from'), 'from'), to = checkDay(arg('to'), 'to');
  const A = arg('assets').trim().toUpperCase();
  if (!HC_ASSETS.includes(A)) throw new Error(`--assets one of ${HC_ASSETS.join(',')}`);
  const rep = arg('replay'), out = arg('out');
  if (!rep || !out) throw new Error('--replay and --out');
  const deadline = Date.now() + Number(arg('minutes', '250')) * 60_000;
  const seed = Number(arg('seed', '0')) || undefined;
  const stage = (arg('stage', '') || process.env.SNN_STAGE || 'S5') as Stage;
  const params = trainParams(stage, undefined, false, undefined, seed);
  // One coin per process (its own two columns); the shared replay's other coins and DOGE are skipped. skipAssets
  // replaces the env list, so DOGE stays in it.
  const skipAssets = ['DOGE', ...HC_ASSETS.filter((x) => x !== A)];
  const calendar = loadCalendar(path.resolve('params/calendar.json'));
  fs.mkdirSync(out, { recursive: true });
  const sampler = new HealthSampler(params, { nofadeTauC: NOFADE_TAU_C });
  const meta: Record<string, unknown> & { chunks: { a: string; b: string; labels: number; minutes: number }[] } = {
    asset: A, from, to, stage, leadInputs: params.leadInputs ?? null, nE: params.nE, nL1: params.nL1, seed: params.seed, arms: { prodShadow: { tauC: params.tauC }, nofade: { tauC: NOFADE_TAU_C }, control: { tauC: params.tauC, label: "y' = [px(T) > px(T-H)]" } },
    note: 'per-coin network (lateral inhibition and freezing over this coin\'s two columns only), not live', chunks: [],
  };
  let checkpoint: SnnCheckpoint | undefined, timeUp = false, labels = 0;
  const all = trainChunks(from, to);
  for (const [a, b] of all) {
    if (Date.now() > deadline) { timeUp = true; console.log(`[health] ${A}: time is up before ${a}`); break; }
    const t0 = Date.now();
    const res = await replaySnn(rep, { params, from: Date.parse(`${a}T00:00:00Z`), to: Date.parse(`${b}T23:59:59Z`), fromDay: addDays(a, -1), toDay: b, calendar, domain: 'crypto', checkpoint, skipModel: true, skipAssets, onProgress: (ts, net) => sampler.sample(ts, net) });
    sampler.drain(res.net);
    checkpoint = res.net.serialize();
    const { rows, dir } = sampler.take();
    fs.writeFileSync(path.join(out, `rows-${a}.jsonl.gz`), gzLines(rows));
    fs.writeFileSync(path.join(out, `dir-${a}.jsonl.gz`), gzLines(dir));
    fs.writeFileSync(path.join(out, 'cum.json'), JSON.stringify(Object.fromEntries(sampler.cum)));
    const norm = (x: ArrayLike<number>, y?: ArrayLike<number>) => { let s = 0; for (let i = 0; i < x.length; i++) s += (x[i] - (y ? y[i] : 0)) ** 2; return Math.sqrt(s); };
    fs.writeFileSync(path.join(out, 'weights.json'), JSON.stringify(Object.fromEntries([...res.net.dirReadouts].map(([k, r]) => {
      const sh = sampler.shadows.get(k);
      const w = (q: Readout) => ({ wf: norm(q.wf), ws: norm(q.ws), div: norm(q.wf, q.ws), wf0: q.wf[0], updates: q.updates, history: q.history.length });
      return [k, { head: w(r), ...(sh ? { prodShadow: w(sh.ps), nofade: w(sh.nf), control: w(sh.ctl) } : {}) }];
    }))));
    labels += dir.length;
    const frozen = rows.length ? (100 * rows.filter((r) => r.fr).length) / rows.length : 0;
    const ps = rows.filter((r) => r.p !== undefined).map((r) => r.p!);
    const min = (Date.now() - t0) / 60_000;
    meta.chunks.push({ a, b, labels: dir.length, minutes: +min.toFixed(2) });
    Object.assign(meta, { timeUp, diff: { max: sampler.diff.max, mean: sampler.diff.n ? sampler.diff.sum / sampler.diff.n : NaN, n: sampler.diff.n }, skippedLabels: sampler.skipped, done: meta.chunks.length, of: all.length });
    fs.writeFileSync(path.join(out, 'meta.json'), JSON.stringify(meta, null, 1));
    // Drive-only log line (the workflow keeps this log off the public output).
    console.log(`[health] ${A} ${a}..${b}: ${dir.length} labels, mean|p-.5| ${spreadStats(ps).meanAbsPp.toFixed(2)}pp, frozen ${frozen.toFixed(1)}%, prodShadow max diff ${sampler.diff.max.toExponential(1)}, ${min.toFixed(1)} min/chunk`);
  }
  Object.assign(meta, { timeUp });
  fs.writeFileSync(path.join(out, 'meta.json'), JSON.stringify(meta, null, 1));
  console.log(`[health] ${A} done: ${meta.chunks.length}/${all.length} chunks, ${labels} labels${timeUp ? ', stopped by the time limit' : ''}`);
}

// ---- report ----------------------------------------------------------------------------------------------------------

interface Joined { k: string; t: number; day: string; y: number; p: number; sp: number; base: number; m5: number; m15: number }

export interface ArmReport extends ArmStats {
  days: number; upRate: number; spread: Spread; sdStateRaw: number; b05: Ci; bBase: Ci; skillHalf: Ci; skillM5: Ci; skillM15: Ci;
  acc: { acc: number; n: number }; accM5: { acc: number; n: number }; accM15: { acc: number; n: number };
}

/** Every statistic of one arm on one set of rows (each row: its p, label, state part and baselines). */
export function armReport(rows: Joined[], px: PxMap, iters: number = RULE.iters): ArmReport {
  const p = rows.map((r) => r.p), y = rows.map((r) => r.y), day = rows.map((r) => r.day), grp = rows.map((r) => `${r.k}|${r.day}`);
  const base = rows.map((r) => r.base), sp = rows.map((r) => r.sp);
  const o = { day, iters };
  return {
    n: rows.length, days: new Set(day).size, upRate: y.reduce((a, b) => a + b, 0) / Math.max(1, y.length), spread: spreadStats(p),
    sdState: withinSd(sp, grp), sdStateRaw: withinSd(sp, rows.map((r) => r.k)),
    slope: slopeB(p, y, { ...o, group: grp, intercept: true }),
    b05: slopeB(p.map((x) => x - 0.5), y.map((x) => x - 0.5), { ...o, intercept: false }),
    bBase: slopeB(p.map((x, i) => x - base[i]), y.map((x, i) => x - base[i]), { ...o, intercept: false }),
    auc: auc(p, y, { ...o, group: grp }),
    skill: brierSkill(p, base, y, o), skillHalf: brierSkill(p, p.map(() => 0.5), y, o),
    skillM5: brierSkill(p, rows.map((r) => r.m5), y, o), skillM15: brierSkill(p, rows.map((r) => r.m15), y, o),
    acc: signAccuracy(p, y), accM5: signMomentumAccuracy(rows, px, 5), accM15: signMomentumAccuracy(rows, px, 15),
  };
}

/** Rows of one arm with its matured baselines (computed over the arm's whole range, in time order). */
function withBaselines(rows: Omit<Joined, 'base' | 'm5' | 'm15'>[], px: PxMap): Joined[] {
  const base = prequentialBase(rows), m5 = prequentialMomentum(rows, px, 5), m15 = prequentialMomentum(rows, px, 15);
  return rows.map((r, i) => ({ ...r, base: base[i], m5: m5[i], m15: m15[i] }));
}

type ProcMeta = { asset?: string; stage?: Stage; leadInputs?: LeadInputs | null; nE?: number; nL1?: number; diff?: { max: number; mean: number; n: number }; skippedLabels?: number; timeUp?: boolean; done?: number; of?: number };

/** report: argv as on the command line (only the flags are read). Exported for the end-to-end test. */
export function reportCmd(argv: string[] = process.argv): void {
  const arg = (k: string, d = '') => argOf(argv, k, d);
  const dir = arg('in', 'research/out/health'), outMd = arg('out', 'research/out/snn-health.md');
  const outJson = arg('json', path.join(dir, 'snn-health.json')), outPublic = arg('public', path.join(dir, 'public-summary.md'));
  const dFrom = checkDay(arg('decide-from', DECIDE_FROM), 'decide-from'), dTo = checkDay(arg('decide-to', DECIDE_TO), 'decide-to');
  const assets = arg('assets', HC_ASSETS.join(',')).split(',').map((x) => x.trim().toUpperCase()).filter(Boolean);
  const expected = assets.flatMap((a) => [`${a}-15m`, `${a}-60m`]);
  const samples: SampleRow[] = [], dirs: DirRow[] = [];
  const metas: Record<string, ProcMeta> = {};
  const cums: Record<string, CumCol> = {}, cumMeta: Record<string, ProcMeta> = {};
  const procs = fs.existsSync(dir) ? fs.readdirSync(dir).filter((d) => fs.existsSync(path.join(dir, d, 'meta.json'))).sort() : [];
  for (const d of procs) {
    const p = path.join(dir, d);
    metas[d] = JSON.parse(fs.readFileSync(path.join(p, 'meta.json'), 'utf8'));
    if (fs.existsSync(path.join(p, 'cum.json'))) {
      const cc = JSON.parse(fs.readFileSync(path.join(p, 'cum.json'), 'utf8')) as Record<string, CumCol>;
      Object.assign(cums, cc);
      for (const k of Object.keys(cc)) cumMeta[k] = metas[d];
    }
    for (const f of fs.readdirSync(p).sort()) {
      if (/^rows-.*\.jsonl\.gz$/.test(f)) for (const r of readGz<SampleRow>(path.join(p, f))) samples.push(r);
      else if (/^dir-.*\.jsonl\.gz$/.test(f)) for (const r of readGz<DirRow>(path.join(p, f))) dirs.push(r);
    }
  }
  // Minute-mark prices per coin (the momentum baselines and the control's label read the same prints).
  const px: PxMap = new Map();
  for (const r of samples) if (r.x! > 0) { const a = assetOf(r.k); let m = px.get(a); if (!m) px.set(a, (m = new Map())); m.set(r.t, r.x!); }
  // Join the head's labels to the sampled minutes on (column, t); drop the unmatched (a tag inside a catch-up).
  const byKey = new Map<string, SampleRow>();
  for (const r of samples) if (r.p !== undefined) byKey.set(`${r.k}|${r.t}`, r);
  let unmatched = 0, pMismatch = 0, noHb = 0, shadowOff = 0, hbMaxDiff = 0;
  const prod: Omit<Joined, 'base' | 'm5' | 'm15'>[] = [], nofade: typeof prod = [], shadow: typeof prod = [];
  for (const d of dirs) {
    const s = byKey.get(`${d.k}|${d.t}`);
    if (!s) { unmatched++; continue; }
    if (Math.abs(s.p! - d.p) > 1e-6) pMismatch++;
    const day = dayOf(d.t), b = s.b ?? 0;
    // Rule 1 on the deciding arm uses the head's own bias at the call (hb); the prodShadow's only for rows without it.
    if (s.hb === undefined) noHb++;
    else if (s.b !== undefined) hbMaxDiff = Math.max(hbMaxDiff, Math.abs(s.hb - s.b));
    if (s.s !== undefined && Math.abs(s.s - s.p!) > 1e-6) shadowOff++;
    prod.push({ k: d.k, t: d.t, day, y: d.y, p: d.p, sp: logit(d.p) - (s.hb ?? b) });
    nofade.push({ k: d.k, t: d.t, day, y: d.y, p: s.n!, sp: logit(s.n!) - (s.nb ?? 0) });
    shadow.push({ k: d.k, t: d.t, day, y: d.y, p: s.s!, sp: logit(s.s!) - b });
  }
  const control: typeof prod = samples.filter((r) => r.c !== undefined && r.yc !== undefined).map((r) => ({ k: r.k, t: r.t, day: dayOf(r.t), y: r.yc!, p: r.c!, sp: logit(r.c!) - (r.cb ?? 0) }));
  const arms = { prod: withBaselines(prod, px), nofade: withBaselines(nofade, px), prodShadow: withBaselines(shadow, px), control: withBaselines(control, px) };
  const inWin = (r: { day: string }) => r.day >= dFrom && r.day <= dTo;
  const win = Object.fromEntries(Object.entries(arms).map(([k, v]) => [k, v.filter(inWin)])) as typeof arms;
  const coverage = expected.map((column) => ({ column, days: new Set(win.prod.filter((r) => r.k === column).map((r) => r.day)).size }));
  const head = armReport(win.prod, px), ctl = armReport(win.control, px);
  const vh = verdict(head), vc = verdict(ctl), line = overall(vh, vc, coverage);
  const vn = verdict(armReport(win.nofade, px));
  const covered = coverage.filter((c) => c.days >= RULE.minDays).length, minDays = Math.min(...coverage.map((c) => c.days));
  const diffMax = Math.max(0, ...Object.values(metas).map((m) => m.diff?.max ?? 0));
  const skippedLabels = Object.values(metas).reduce((a, m) => a + (m.skippedLabels ?? 0), 0);
  // How far the control's label is from its input: sign(ret_h_z) at the tag against y' (window rows, rz != 0).
  let agreeN = 0, agree = 0;
  for (const r of samples) {
    if (r.yc === undefined || !r.rz || r.c === undefined) continue;
    const day = dayOf(r.t);
    if (day < dFrom || day > dTo) continue;
    agreeN++; if ((r.rz > 0 ? 1 : 0) === r.yc) agree++;
  }
  const ctlAgree = agreeN ? agree / agreeN : NaN;

  // ---- the full report (Drive only)
  const L: string[] = [];
  const ci = (c: Ci, d = 3) => `${fmt(c.est, d)} [${fmt(c.lo, d)}, ${fmt(c.hi, d)}]`;
  const hdr = '| slice | n | days | up-rate | mean abs(p-.5) pp | p90 abs(p-.5) pp | state sd (col x day) | slope FE [CI] | b0.5 | b_base | AUC strat. [CI] | skill vs base [CI] | vs mom5 | vs mom15 | acc head | acc sign-mom5 | acc sign-mom15 |';
  const sep = '|' + '---|'.repeat(17);
  const rowOf = (name: string, s: ArmReport) => `| ${name} | ${s.n} | ${s.days} | ${fmt(s.upRate, 3)} | ${fmt(s.spread.meanAbsPp, 2)} | ${fmt(s.spread.a90, 2)} | ${fmt(s.sdState, 3)} | ${ci(s.slope, 2)} | ${fmt(s.b05.est, 2)} | ${fmt(s.bBase.est, 2)} | ${ci(s.auc, 4)} | ${ci(s.skill, 5)} | ${fmt(s.skillM5.est, 5)} | ${fmt(s.skillM15.est, 5)} | ${fmt(s.acc.acc, 4)} | ${fmt(s.accM5.acc, 4)} | ${fmt(s.accM15.acc, 4)} |`;
  const table = (title: string, rows: Joined[], slicers: [string, (r: Joined) => string][]) => {
    L.push(`### ${title}`, '', hdr, sep);
    for (const [label, f] of slicers) {
      const groups = new Map<string, Joined[]>();
      for (const r of rows) { const g = f(r); let a = groups.get(g); if (!a) groups.set(g, (a = [])); a.push(r); }
      for (const [g, rs] of [...groups].sort((a, b) => a[0].localeCompare(b[0]))) L.push(rowOf(`${label}${g}`, armReport(rs, px, 300)));
    }
    L.push('');
  };
  L.push(`# SNN health check: does the direction head learn coin direction?`, '');
  L.push(`**Verdict (pre-registered, decision window ${dFrom}..${dTo} UTC, prod arm pooled over columns): ${line}**`, '');
  L.push(`- head (prod): ${vh.pass ? 'PASS' : 'FAIL'}${vh.fails.length ? ` (${vh.fails.join('; ')})` : ''}`);
  L.push(`- positive control (y' = [px(T) > px(T-H)], production settings): ${vc.pass ? 'PASS' : 'FAIL'}${vc.fails.length ? ` (${vc.fails.join('; ')})` : ''}`);
  L.push(`- nofade shadow (tauC ${NOFADE_TAU_C}), same rule, diagnostic only: ${vn.pass ? 'PASS' : 'FAIL'}${vn.fails.length ? ` (${vn.fails.join('; ')})` : ''}`);
  L.push(`- coverage: ${covered}/${expected.length} columns with >= ${RULE.minDays} decision-window days (min ${minDays}); ${coverage.map((c) => `${c.column} ${c.days}`).join(', ')}`);
  L.push(`- joined head labels: ${prod.length} (unmatched dropped: ${unmatched}; dirLog p differing from the sampled tag p: ${pMismatch}); control labels: ${control.length}`);
  L.push(`- prodShadow reproduces the head's p to max abs diff ${diffMax.toExponential(2)} (${Object.entries(metas).map(([k, m]) => `${k} ${m.diff ? m.diff.max.toExponential(1) : 'NaN'}`).join(', ')}); joined calls with the prodShadow's p off by > 1e-6: ${shadowOff}; head labels the shadows skipped (no pending tag): ${skippedLabels}`);
  L.push(`- the head's state part (rule 1) uses the head's own bias at the call; max abs(head bias - prodShadow bias) ${hbMaxDiff.toExponential(2)}${noHb ? `; ${noHb} rows without it used the prodShadow's` : ''}`);
  L.push(`- control label vs its input: sign(ret_h_z) at the tag agrees with y' on ${fmt(100 * ctlAgree, 2)}% of ${agreeN} window rows (ret_h_z uses a bar close and a 5 s feature cache, y' the minute-mark prints)`);
  L.push(`- processes: ${Object.entries(metas).map(([k, m]) => `${k} ${m.done ?? 0}/${m.of ?? '?'} chunks${m.timeUp ? ' (time up)' : ''}`).join(', ')}`);
  L.push(`- frozen %, G and freezing come from per-coin networks (2 columns each), not the live 8-column network.`, '');
  L.push('Rule: an arm LEARNS iff state sd (logit(p) - bias, within column x day) >= 0.05 AND the slope of y on p with column x day fixed effects is in [0.7, 1.3] with its 95% CI lower bound > 0 AND the column x day stratified AUC CI lower bound > 0.5 AND the Brier skill vs the matured prequential base rate has CI lower bound > 0. CIs: day-block bootstrap, 1000 resamples (tables below: 300).', '');
  L.push('## Decision window', '');
  L.push('### Arms, pooled over columns', '', hdr, sep);
  for (const [k, rs] of Object.entries(win)) L.push(rowOf(k, armReport(rs, px)));
  L.push('');
  const slicers: [string, (r: Joined) => string][] = [['coin ', (r) => assetOf(r.k)], ['column ', (r) => r.k], ['month ', (r) => r.day.slice(0, 7)]];
  table('prod by coin, column and month', win.prod, slicers);
  table('nofade by coin and column', win.nofade, slicers.slice(0, 2));
  table('control by coin and column', win.control, slicers.slice(0, 2));
  L.push('## Full range (diagnostic; learning starts at zero weights)', '');
  table('prod by coin, column and month', arms.prod, slicers);
  table('nofade by column and month', arms.nofade, slicers.slice(1));
  table('control by column and month', arms.control, slicers.slice(1));
  // Learning summary from the sampled minutes.
  L.push('## Learning (sampled minutes)', '', '| range | minutes | frozen % | recovering % | mean G | G>=0.9 % | mean eta/dirEta | eta<0.5 % | mean fSat | mean rhoHat | mean errZ | mean dBrier | mean E feature | mean L1 feature | abs(p-.5)>0.45 % |', '|' + '---|'.repeat(15));
  for (const [label, rs] of [['decision window', samples.filter((r) => { const d = dayOf(r.t); return d >= dFrom && d <= dTo; })], ['full range', samples]] as const) {
    const n = Math.max(1, rs.length), m = (f: (r: SampleRow) => number) => rs.reduce((a, r) => a + f(r), 0) / n;
    const withP = rs.filter((r) => r.p !== undefined);
    L.push(`| ${label} | ${rs.length} | ${fmt(100 * m((r) => r.fr), 1)} | ${fmt(100 * m((r) => r.rc), 1)} | ${fmt(m((r) => r.G), 3)} | ${fmt(100 * m((r) => (r.G >= 0.9 ? 1 : 0)), 1)} | ${fmt(m((r) => r.eta), 3)} | ${fmt(100 * m((r) => (r.eta < 0.5 ? 1 : 0)), 1)} | ${fmt(m((r) => r.fs), 4)} | ${fmt(m((r) => r.rho), 3)} | ${fmt(m((r) => r.ez), 3)} | ${fmt(m((r) => r.db), 4)} | ${fmt(m((r) => r.rE), 5)} | ${fmt(m((r) => r.rL1), 5)} | ${fmt((100 * withP.filter((r) => Math.abs(r.p! - 0.5) > 0.45).length) / Math.max(1, withP.length), 2)} |`);
  }
  const fb = new Map<string, number>();
  for (const r of samples) for (const x of r.fb ?? []) fb.set(x, (fb.get(x) ?? 0) + 1);
  L.push('', `Frozen minutes by freeze metric (full range): ${[...fb].map(([k, v]) => `${k} ${v}`).join(', ') || 'none'}; recovering = frozen with no freeze breach (the 1800 s recovery). Weight saturation is constant in S5 (plasticity off: no column weight learns), so fSat cannot move G.`, '');
  // Channels and features.
  L.push('## Dead channels and head features', '');
  for (const [k, c] of Object.entries(cums).sort()) {
    // The stage (and lead inputs) each process ran with, from its meta.json (S5 for a meta without the field).
    const m = cumMeta[k] ?? {}, sp = trainParams(m.stage ?? 'S5', undefined, false, undefined, undefined, m.leadInputs ?? undefined);
    const lead = m.leadInputs ?? sp.leadInputs, nE = m.nE ?? sp.nE, nL1 = m.nL1 ?? sp.nL1;
    const dc = classifyDead(c.chanActive, c.inputs, lead);
    const zero = phiZeroByDesign(nE, nL1, c.phiMean.length);
    const zv = c.phiM2.map((m2, i) => (m2 <= 0 && !zero.has(i) && i !== 0 ? i : -1)).filter((i) => i >= 0);
    const { E, L1 } = phiBlocks(nE, nL1);
    const blockZero = (b: readonly [number, number]) => zv.filter((i) => i >= b[0] && i < b[1]).length;
    L.push(`- ${k} (stage ${m.stage ?? 'S5'}): ${c.minutes} min; live L0 channels ${dc.live}/${c.chanActive.length}; dead because the source is absent ${dc.absent.length} (inputs ${dc.deadInputs.absent.join(', ') || 'none'}); UNEXPECTEDLY dead ${dc.unexpected.length}${dc.unexpected.length ? ` (${dc.unexpected.join(', ')})` : ''}; unused bands ${dc.unusedBand.length}; flat inputs ${dc.deadInputs.flat.join(', ') || 'none'}; zero-variance head features outside the by-design set: ${zv.length} (E block ${blockZero(E)}, L1 block ${blockZero(L1)}); max phi ${fmt(Math.max(...c.phiMax), 4)} (dw cap reachable only if dirEta * max phi > dirCap); mean E-block feature ${fmt(c.phiMean.slice(E[0], E[1]).reduce((a, b) => a + b, 0) / (E[1] - E[0]), 5)}, L1 ${fmt(c.phiMean.slice(L1[0], L1[1]).reduce((a, b) => a + b, 0) / (L1[1] - L1[0]), 5)}`);
  }
  L.push('', 'Known differences from live: one coin per network (lateral inhibition and freezing over that coin\'s two columns only); no contracts (contract channels dead by construction); proxies off in S5 (extras 0).');
  fs.mkdirSync(path.dirname(outMd), { recursive: true });
  fs.writeFileSync(outMd, L.join('\n') + '\n');
  fs.writeFileSync(outJson, JSON.stringify({ verdict: line, head: { ...vh, stats: head }, control: { ...vc, stats: ctl }, nofade: vn, coverage, unmatched, pMismatch, diffMax, shadowOff, skippedLabels, hbMaxDiff, noHb, controlInputAgreement: { rate: ctlAgree, n: agreeN }, window: [dFrom, dTo], metas }, null, 1));
  // ---- public: the verdict line and headline counts only
  const pub = [
    `[health] VERDICT: ${line}`,
    `[health] head ${vh.pass ? 'PASS' : 'FAIL'}, control ${vc.pass ? 'PASS' : 'FAIL'}; ${covered}/${expected.length} columns with >= ${RULE.minDays} decision days; ${win.prod.length} head and ${win.control.length} control labels in the window; ${unmatched} unmatched dropped`,
  ];
  fs.writeFileSync(outPublic, pub.join('\n\n') + '\n');
  for (const l of pub) console.log(l.slice(0, 260));
}

async function main() {
  const cmd = process.argv[2];
  if (cmd === 'fetch') await fetchCmd();
  else if (cmd === 'run') await runCmd();
  else if (cmd === 'report') reportCmd();
  else throw new Error('usage: snnHealthCheck.ts fetch|run|report ...');
}

if (process.argv[1] && /snnHealthCheck\.ts$/.test(process.argv[1])) main().catch((e) => { console.error(`health check failed: ${e instanceof Error ? e.stack : e}`); process.exit(1); });
