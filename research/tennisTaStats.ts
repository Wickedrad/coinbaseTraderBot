// Tennis TA rulebook trial: statistics and the discovery report (pre-registration section 6,
// /mnt/project-files/tennis-ta/preregistration.md).
//
//   clusteredT   cluster-robust (match-day clusters) t of the per-entry mean, C/(C-1) small-sample factor, df = C - 1
//   tSf          one-sided Student-t tail from a regularized incomplete beta that takes x and 1 - x separately, so the
//                far tail keeps its relative accuracy (BH over tens of thousands of B cells cuts near p = 1e-6)
//   pairedZ      day-paired difference against the placebo arm
//   bhReject     Benjamini-Hochberg step-up over the family's full design size (untested cells count as p = 1)
//   cscvPbo      CSCV probability of backtest overfitting over monthly folds (Bailey, Borwein, Lopez de Prado, Zhu 2015)
//   discoverB    the family B funnel: size, mean > 0, BH, monthly folds, F2 stress, breaches, placebo; one cell per group
//   discoverA    the same funnel for the production rulebook grid, A1 sensitivity, pairwise heat tables, the A2 knob pick
//
// bhReject, tSf and the CSCV logit rule are ported from the perp TA thread (origin/claude/project-thread-9040i4,
// research/perpTaSweep.ts bhReject / tSf / pbo) and research/stats.ts pbo (average rank for ties).
// Realized profit after fees is the only score: every number here is net $ (the simulators charge bot/fees.ts orderFee
// per fill, rounded up to the cent).

import { lgamma, maxOf } from '../bot/util/num';
import { rng } from './stats';
import { emptyStats, type CellResult, type ClusterStats, type ConfigDay, type ConfigRun, type PairDiff } from './tennisTaTypes';

// ---------------------------------------------------------------------------------------------------------------------
// Core statistics

export function meanOf(s: ClusterStats): number {
  return s.n > 0 ? s.sum / s.n : NaN;
}

/** Cluster-robust (match-day clusters) standard error of the per-entry mean and the t statistic against mu0:
 *  V = (cSumSq - 2 m cNSum + m^2 cNSq) / n^2 * C/(C-1), m = sum/n; t = (m - mu0)/sqrt(V); df = C - 1. */
export function clusteredT(s: ClusterStats, mu0 = 0): { mean: number; se: number; t: number; df: number } {
  const C = s.clusters, df = Math.max(0, C - 1);
  if (!(s.n > 0)) return { mean: NaN, se: NaN, t: NaN, df };
  const m = s.sum / s.n;
  if (C < 2) return { mean: m, se: NaN, t: NaN, df };
  // sum over clusters of (S_c - m N_c)^2; cancellation can leave a tiny negative, clamp at 0.
  const ss = Math.max(0, s.cSumSq - 2 * m * s.cNSum + m * m * s.cNSq);
  const V = (ss / (s.n * s.n)) * (C / (C - 1));
  const se = Math.sqrt(V);
  const d = m - mu0;
  const t = se > 0 ? d / se : d === 0 ? 0 : d > 0 ? Infinity : -Infinity;
  return { mean: m, se, t, df };
}

/** Continued fraction of I_x(a, b) (modified Lentz, Numerical Recipes 6.4). Converges in O(sqrt(max(a, b))) steps
 *  on the branch it is called on (x < (a + 1)/(a + b + 2)). */
function betacf(x: number, a: number, b: number): number {
  const TINY = 1e-300, EPS = 1e-16;
  const qab = a + b, qap = a + 1, qam = a - 1;
  let c = 1, d = 1 - (qab * x) / qap;
  if (Math.abs(d) < TINY) d = TINY;
  d = 1 / d;
  let h = d;
  for (let m = 1; m <= 200_000; m++) {
    const m2 = 2 * m;
    let aa = (m * (b - m) * x) / ((qam + m2) * (a + m2));
    d = 1 + aa * d; if (Math.abs(d) < TINY) d = TINY;
    c = 1 + aa / c; if (Math.abs(c) < TINY) c = TINY;
    d = 1 / d; h *= d * c;
    aa = (-(a + m) * (qab + m) * x) / ((a + m2) * (qap + m2));
    d = 1 + aa * d; if (Math.abs(d) < TINY) d = TINY;
    c = 1 + aa / c; if (Math.abs(c) < TINY) c = TINY;
    d = 1 / d;
    const del = d * c;
    h *= del;
    if (Math.abs(del - 1) < EPS) break;
  }
  return h;
}

/** Regularized incomplete beta I_x(a, b) with y = 1 - x passed exactly (no 1 - x cancellation near x = 1). */
function ibeta(x: number, y: number, a: number, b: number): number {
  if (x <= 0) return 0;
  if (y <= 0) return 1;
  const lfront = a * Math.log(x) + b * Math.log(y) + lgamma(a + b) - lgamma(a) - lgamma(b);
  if (x < (a + 1) / (a + b + 2)) return (Math.exp(lfront) * betacf(x, a, b)) / a;
  return 1 - (Math.exp(lfront) * betacf(y, b, a)) / b;
}

/** One-sided p-value P(T >= t) for Student t with df degrees of freedom (accurate incomplete-beta implementation). */
export function tSf(t: number, df: number): number {
  if (Number.isNaN(t) || !(df > 0)) return NaN;
  if (t === Infinity) return 0;
  if (t === -Infinity) return 1;
  const t2 = t * t;
  // P(|T| >= |t|) = I_{df/(df+t^2)}(df/2, 1/2); both x and 1 - x formed without subtraction.
  const twoSided = ibeta(df / (df + t2), t2 / (df + t2), df / 2, 0.5);
  return t >= 0 ? 0.5 * twoSided : 1 - 0.5 * twoSided;
}

/** Paired day-difference z (one-sided): mean daily difference / its standard error. */
export function pairedZ(d: PairDiff): { z: number; days: number; meanPerDay: number } {
  const D = d.clusters;
  if (!(D > 0)) return { z: NaN, days: 0, meanPerDay: NaN };
  const m = d.sum / D;
  if (D < 2) return { z: NaN, days: D, meanPerDay: m };
  const v = Math.max(0, (d.sumSq - D * m * m) / (D - 1));
  const se = Math.sqrt(v / D);
  const z = se > 0 ? m / se : m === 0 ? 0 : m > 0 ? Infinity : -Infinity;
  return { z, days: D, meanPerDay: m };
}

/** Benjamini-Hochberg: indices of hypotheses rejected at level q given p-values and the total design size m >= p.length
 *  (untested cells count as p = 1). Non-finite p-values count as 1. */
export function bhReject(p: number[], q: number, m = p.length): Set<number> {
  const M = Math.max(m, p.length);
  const ord = p.map((v, i) => [Number.isFinite(v) ? v : 1, i] as const).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  let kMax = 0;
  for (let k = 0; k < ord.length; k++) if (ord[k][0] <= (q * (k + 1)) / M) kMax = k + 1; // step-up: the largest k
  return new Set(ord.slice(0, kMax).map(([, i]) => i));
}

/** The BH cutoff a p-value had to meet: q k / m with k the number rejected (q / m when nothing was). */
const bhCutoff = (q: number, rejected: number, m: number) => (q * Math.max(1, rejected)) / m;

function* combinations(n: number, k: number, start = 0, acc: number[] = []): Generator<number[]> {
  if (acc.length === k) { yield acc.slice(); return; }
  for (let i = start; i <= n - (k - acc.length); i++) {
    acc.push(i);
    yield* combinations(n, k, i + 1, acc);
    acc.pop();
  }
}

function choose(n: number, k: number): number {
  let r = 1;
  for (let i = 1; i <= k; i++) r = (r * (n - k + i)) / i;
  return Math.round(r);
}

/** CSCV probability of backtest overfitting (Bailey et al.): perf[config][fold] (e.g. mean net per entry or per day),
 *  S even folds blocks (combine adjacent folds into S blocks), at most maxCombos combinations sampled with a seeded RNG.
 *
 *  Each block's score is the mean of its folds' values (a non-finite fold counts as 0: no trades, no profit); a split's
 *  in-sample score is the mean over its in-sample folds, so every month weighs the same. The in-sample best config's
 *  out-of-sample rank w = rank / (N + 1) (average rank for ties, 1 = worst) gives the logit ln(w / (1 - w)); PBO is the
 *  share of splits with a negative logit (a logit of exactly 0 counts half). Default S: every fold its own block, at
 *  most 16, rounded down to even. When C(S, S/2) <= maxCombos every split is used. */
export function cscvPbo(perf: number[][], S?: number, maxCombos = 2000, seed = 20261105): { pbo: number; combos: number; logits: number[] } {
  const N = perf.length;
  const T = N ? maxOf(perf, (r) => r.length) : 0;
  let s = Math.min(S ?? Math.min(T, 16), T);
  if (s % 2) s--;
  if (N < 2 || s < 2) return { pbo: NaN, combos: 0, logits: [] };
  // Blocks of adjacent folds, sizes differing by at most one: block b holds folds [floor(bT/s), floor((b+1)T/s)).
  const blockSum = new Float64Array(N * s);
  const blockCnt = new Float64Array(s);
  for (let b = 0; b < s; b++) {
    const lo = Math.floor((b * T) / s), hi = Math.floor(((b + 1) * T) / s);
    blockCnt[b] = hi - lo;
    for (let i = 0; i < N; i++) {
      let acc = 0;
      for (let f = lo; f < hi; f++) { const v = perf[i][f]; acc += Number.isFinite(v) ? v : 0; }
      blockSum[i * s + b] = acc;
    }
  }
  const half = s / 2;
  const total = choose(s, half);
  let splits: number[][];
  if (total <= maxCombos) splits = [...combinations(s, half)];
  else {
    const r = rng(seed), seen = new Set<string>(), idx = Array.from({ length: s }, (_, i) => i);
    splits = [];
    for (let tries = 0; splits.length < maxCombos && tries < maxCombos * 50; tries++) {
      for (let i = 0; i < half; i++) { const j = i + Math.floor(r() * (s - i)); [idx[i], idx[j]] = [idx[j], idx[i]]; }
      const pick = idx.slice(0, half).sort((a, b) => a - b), key = pick.join(',');
      if (!seen.has(key)) { seen.add(key); splits.push(pick); }
    }
  }
  const logits: number[] = [];
  let below = 0;
  const oos = new Float64Array(N);
  for (const is of splits) {
    const inIs = new Uint8Array(s);
    for (const b of is) inIs[b] = 1;
    let best = 0, bestV = -Infinity;
    for (let i = 0; i < N; i++) {
      let a = 0, o = 0;
      for (let b = 0; b < s; b++) { const v = blockSum[i * s + b]; if (inIs[b]) a += v; else o += v; }
      oos[i] = o;
      if (a > bestV) { bestV = a; best = i; }
    }
    let less = 0, ties = 0;
    for (let i = 0; i < N; i++) { if (oos[i] < oos[best]) less++; else if (i !== best && oos[i] === oos[best]) ties++; }
    const w = (less + 1 + ties / 2) / (N + 1);
    const lg = Math.log(w / (1 - w));
    logits.push(lg);
    if (lg < -1e-12) below++;
    else if (Math.abs(lg) <= 1e-12) below += 0.5;
  }
  return { pbo: logits.length ? below / logits.length : NaN, combos: logits.length, logits };
}

/** $/h over 24 h: pnl / wall-clock hours of the span [fromDay, toDay] inclusive (every hour counts). */
export function perHour24(pnl: number, fromDay: string, toDay: string): number {
  const a = Date.parse(`${fromDay}T00:00:00Z`), b = Date.parse(`${toDay}T00:00:00Z`);
  if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) return NaN;
  return pnl / ((b - a) / 3_600_000 + 24);
}

// ---------------------------------------------------------------------------------------------------------------------
// The discovery funnel shared by both families

interface Defaults { q: number; minN: number; minDays: number; minFoldShare: number; minFoldN: number }
const defaults = (o: Partial<Defaults> = {}): Defaults => ({
  q: o.q ?? 0.1, minN: o.minN ?? 100, minDays: o.minDays ?? 30, minFoldShare: o.minFoldShare ?? 0.6, minFoldN: o.minFoldN ?? 10,
});

/** Share of monthly folds holding minFoldN+ entries whose net is positive (0 when no fold qualifies). */
function foldShareOf(folds: Record<string, ClusterStats>, minFoldN: number): { share: number; qualified: number; positive: number } {
  let qualified = 0, positive = 0;
  for (const f of Object.values(folds)) if (f.n >= minFoldN) { qualified++; if (f.sum > 0) positive++; }
  return { share: qualified ? positive / qualified : 0, qualified, positive };
}

interface Judged {
  n: number; days: number; mean: number; t: number; p: number; df: number;
  sized: boolean; bh: boolean; foldShare: number; foldsQ: number; foldsPos: number;
  stressMean: number; hasStress: boolean; placeboZ: number; hasPlacebo: boolean; breaches: number;
  rules: Array<{ rule: string; ok: boolean; msg: string }>;
  pass: boolean;
  /** Runs the config still needs before it can be flagged (stress, placebo), when every rule it has passes. */
  needs: string[];
}

const RULES = ['size', 'mean', 'BH', 'folds', 'F2', 'breaches', 'placebo'] as const;

function judge(x: Omit<Judged, 'rules' | 'pass' | 'needs'>, d: Defaults, bhCut: number): Judged {
  const rules: Judged['rules'] = [];
  const add = (rule: string, ok: boolean, msg: string) => rules.push({ rule, ok, msg: `${rule} ${ok ? 'ok' : 'FAIL'}: ${msg}` });
  add('size', x.sized, `${x.n} entries on ${x.days} days (need ${d.minN} on ${d.minDays})`);
  add('mean', x.mean > 0, `${fmt(x.mean, 4)} $/entry`);
  add('BH', x.bh, x.sized ? `t ${fmt(x.t, 2)} df ${x.df} p ${fmtP(x.p)} vs cutoff ${fmtP(bhCut)}` : 'untested (counts as p = 1)');
  add('folds', x.foldShare >= d.minFoldShare && x.foldsQ > 0, `${x.foldsPos}/${x.foldsQ} months with ${d.minFoldN}+ entries positive (need ${Math.round(d.minFoldShare * 100)}%)`);
  add('F2', x.hasStress && x.stressMean > 0, x.hasStress ? `stress ${fmt(x.stressMean, 4)} $/entry` : 'no F2 run');
  add('breaches', x.breaches === 0, `${x.breaches} settlement breaches`);
  add('placebo', x.hasPlacebo && x.placeboZ > 0, x.hasPlacebo ? `paired z ${fmt(x.placeboZ, 2)}` : 'no placebo run');
  const pass = rules.every((r) => r.ok);
  const others = rules.filter((r) => r.rule !== 'F2' && r.rule !== 'placebo').every((r) => r.ok)
    && (!x.hasStress || x.stressMean > 0) && (!x.hasPlacebo || x.placeboZ > 0);
  const needs = !pass && others ? [...(x.hasStress ? [] : ['F2']), ...(x.hasPlacebo ? [] : ['placebo'])] : [];
  return { ...x, rules, pass, needs };
}

function funnelCounts(js: Judged[]): string {
  let alive = js;
  const parts = [`${js.length} evaluated`];
  for (const r of RULES) {
    alive = alive.filter((j) => j.rules.find((x) => x.rule === r)?.ok);
    parts.push(`${r} ${alive.length}`);
  }
  return parts.join(' -> ');
}

// ---------------------------------------------------------------------------------------------------------------------
// Formatting

function fmt(x: number, d = 2): string {
  if (!Number.isFinite(x)) return Number.isNaN(x) ? '-' : x > 0 ? '+inf' : '-inf';
  return (x >= 0 ? '+' : '') + x.toFixed(d);
}
function fmtP(p: number): string {
  if (!Number.isFinite(p)) return '-';
  return p !== 0 && p < 1e-3 ? p.toExponential(1) : p.toFixed(3);
}
/** A markdown table cell: backslashes first, then the pipes. */
const cell = (s: string) => s.replace(/\\/g, '\\\\').replace(/\|/g, '\\|');

// ---------------------------------------------------------------------------------------------------------------------
// Family B

/** The id of the same cell traded the other way (follow <-> fade), for the reversed-direction column. */
function reversedId(id: string): string | undefined {
  const seg = id.split('|');
  const i = seg.findIndex((s) => s === 'follow' || s === 'fade');
  if (i < 0) return undefined;
  seg[i] = seg[i] === 'follow' ? 'fade' : 'follow';
  return seg.join('|');
}

/** Family B discovery funnel per pre-registration section 6: inputs cells + designSize; returns flagged cells with the
 *  reason each rule passed or failed, one representative per group (best clustered t), and a markdown table.
 *
 *  Cells with fewer than minN entries or minDays match-days get no p-value: they count as p = 1 in the BH design size
 *  (a cluster-robust t on a handful of days is anti-conservative, and a cell that small cannot be flagged anyway).
 *  The placebo comparison is the day-paired z (cell.pairDiff); without it, an unpaired z of the two clustered means. */
export function discoverB(cells: CellResult[], designSize: number, o: { q?: number; minN?: number; minDays?: number; minFoldShare?: number; minFoldN?: number } = {}): {
  flagged: Array<{ cell: CellResult; t: number; p: number; foldShare: number; stressMean: number; placeboZ: number; why: string[] }>;
  tested: number; markdown: string; pbo: { pbo: number; combos: number };
} {
  const d = defaults(o);
  const m = Math.max(designSize, cells.length);
  const base = cells.map((c) => {
    const ct = clusteredT(c.total);
    const sized = c.total.n >= d.minN && c.total.clusters >= d.minDays;
    const p = sized ? (Number.isNaN(ct.t) ? 1 : tSf(ct.t, ct.df)) : 1;
    return { ct, sized, p };
  });
  const testedIdx = base.map((b, i) => (b.sized ? i : -1)).filter((i) => i >= 0);
  const rej = bhReject(testedIdx.map((i) => base[i].p), d.q, m);
  const bhSet = new Set([...rej].map((k) => testedIdx[k]));
  const cut = bhCutoff(d.q, bhSet.size, m);
  const judged = cells.map((c, i) => {
    const { ct, sized, p } = base[i];
    const fs = foldShareOf(c.folds, d.minFoldN);
    let placeboZ = NaN, hasPlacebo = false;
    if (c.pairDiff && c.pairDiff.clusters > 0) { placeboZ = pairedZ(c.pairDiff).z; hasPlacebo = true; }
    else if (c.placebo && c.placebo.n > 0) {
      const a = clusteredT(c.total), b = clusteredT(c.placebo);
      placeboZ = (a.mean - b.mean) / Math.sqrt(a.se * a.se + b.se * b.se);
      hasPlacebo = true;
    }
    return judge({
      n: c.total.n, days: c.total.clusters, mean: ct.mean, t: ct.t, p, df: ct.df, sized, bh: bhSet.has(i),
      foldShare: fs.share, foldsQ: fs.qualified, foldsPos: fs.positive,
      stressMean: c.stress ? meanOf(c.stress) : NaN, hasStress: !!c.stress, placeboZ, hasPlacebo, breaches: c.breaches,
    }, d, cut);
  });

  // One representative per group: the best clustered t among the group's cells that pass every rule.
  const repByGroup = new Map<string, number>();
  judged.forEach((j, i) => {
    if (!j.pass) return;
    const cur = repByGroup.get(cells[i].group);
    if (cur === undefined || j.t > judged[cur].t) repByGroup.set(cells[i].group, i);
  });
  const flaggedIdx = [...repByGroup.values()].sort((a, b) => judged[b].t - judged[a].t);
  const flagged = flaggedIdx.map((i) => ({
    cell: cells[i], t: judged[i].t, p: judged[i].p, foldShare: judged[i].foldShare, stressMean: judged[i].stressMean,
    placeboZ: judged[i].placeboZ, why: judged[i].rules.map((r) => r.msg),
  }));

  // CSCV over the cells the selection chose from (the sized ones), monthly folds, mean net per entry (0 without entries).
  const months = [...new Set(testedIdx.flatMap((i) => Object.keys(cells[i].folds)))].sort();
  const pbo = testedIdx.length >= 2 && months.length >= 2
    ? cscvPbo(testedIdx.map((i) => months.map((mo) => { const f = cells[i].folds[mo]; return f && f.n > 0 ? f.sum / f.n : 0; })))
    : { pbo: NaN, combos: 0, logits: [] };

  const byId = new Map(cells.map((c, i) => [c.id, i]));
  const revCol = (i: number) => {
    const rid = reversedId(cells[i].id), k = rid === undefined ? undefined : byId.get(rid);
    return k === undefined ? '-' : `${fmt(judged[k].mean, 4)} (t ${fmt(judged[k].t, 1)})`;
  };
  const row = (i: number) => {
    const j = judged[i], c = cells[i];
    const marks = j.rules.map((r) => (r.ok ? r.rule : `~~${r.rule}~~`)).join(' ');
    return `| ${cell(c.id)} | ${j.n} | ${j.days} | ${fmt(j.mean, 4)} | ${fmt(c.gross, 2)} | ${fmt(c.fees, 2)} | ${fmt(j.t, 2)} | ${fmtP(j.p)} | ${j.foldsPos}/${j.foldsQ} | ${fmt(j.stressMean, 4)} | ${j.breaches} | ${fmt(j.placeboZ, 2)} | ${revCol(i)} | ${marks} |`;
  };
  const head = '| cell | entries | days | $/entry | gross $ | fees $ | t | p | folds+ | F2 $/entry | breaches | placebo z | reversed $/entry | rules |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|';
  // Near misses: each group's best-t sized cell, top 25 groups, with every rule marked (struck through = failed).
  const bestSized = new Map<string, number>();
  judged.forEach((j, i) => {
    if (!j.sized || Number.isNaN(j.t)) return;
    const cur = bestSized.get(cells[i].group);
    if (cur === undefined || j.t > judged[cur].t) bestSized.set(cells[i].group, i);
  });
  const near = [...bestSized.values()].filter((i) => !judged[i].pass).sort((a, b) => judged[b].t - judged[a].t).slice(0, 25);
  const md = [
    '## Family B discovery (H-DISC, F1)',
    '',
    `Design size m = ${m}, BH q = ${d.q}; tested (>= ${d.minN} entries on >= ${d.minDays} match-days): ${testedIdx.length}; BH rejections ${bhSet.size} (cutoff p <= ${fmtP(cut)}).`,
    `Funnel (sequential): ${funnelCounts(judged)}. Groups flagged: ${flagged.length}.`,
    `CSCV PBO over ${months.length} discovery months (tested cells, mean net $/entry per month): ${Number.isNaN(pbo.pbo) ? '-' : pbo.pbo.toFixed(3)} (${pbo.combos} splits).`,
    'Placebo z is reported; the hard placebo threshold (paired z >= 2.13) applies at the blind test.',
    '',
    '### Flagged (one per group, best clustered t)',
    '',
    flagged.length ? [head, ...flaggedIdx.map(row)].join('\n') : '_none_',
    '',
    '### Best cell of each group that did not pass (top 25 by t; struck-through rules failed)',
    '',
    near.length ? [head, ...near.map(row)].join('\n') : '_none_',
    '',
  ].join('\n');
  return { flagged, tested: testedIdx.length, markdown: md, pbo: { pbo: pbo.pbo, combos: pbo.combos } };
}

// ---------------------------------------------------------------------------------------------------------------------
// Family A

/** The A1 knobs in pre-registered order (section 5: ties in the A2 pick go to the earlier knob), with env names. */
const A1_KNOBS: Array<{ name: string; env: RegExp }> = [
  { name: 'confWindowSec', env: /^TENNIS_CONF_WINDOW_SEC$/ },
  { name: 'confMomentumCents', env: /^TENNIS_CONF_MOMENTUM_CENTS$/ },
  { name: 'confFlow', env: /^TENNIS_CONF_FLOW$/ },
  { name: 'confOpponentCents', env: /^TENNIS_CONF_OPPONENT_CENTS$/ },
  { name: 'entryMinSignalsPre', env: /^TENNIS_ENTRY_MIN_SIGNALS_PRE$/ },
  { name: 'entryMinSignalsLive', env: /^TENNIS_ENTRY_MIN_SIGNALS_LIVE$/ },
  { name: 'favEntryMinSignals', env: /^TENNIS_FAV_ENTRY_MIN_SIGNALS$/ },
  { name: 'huntMinSignals', env: /^TENNIS_HUNT_MIN_SIGNALS$/ },
  { name: 'underdogMax', env: /^TENNIS_UNDERDOG_MAX$/ },
  { name: 'underdogMin', env: /^TENNIS_UNDERDOG_MIN$/ },
  { name: 'takeProfitPct', env: /^TENNIS_TP_PCT$/ },
  { name: 'takeProfitCents', env: /^TENNIS_TP_CENTS$/ },
  { name: 'favMin', env: /^TENNIS_FAV_MIN$/ },
  { name: 'favMax', env: /^TENNIS_FAV_MAX$/ },
  { name: 'favMinProgress', env: /^TENNIS_FAV_MIN_PROGRESS$/ },
  { name: 'huntMaxSec', env: /^TENNIS_HUNT_MAX_SEC$/ },
  { name: 'huntTrailTicks', env: /^TENNIS_HUNT_TRAIL_TICKS$/ },
  { name: 'trail', env: /^TENNIS_TRAIL$/ },
  { name: 'underdogLateProgress', env: /^TENNIS_UNDERDOG_LATE_PROGRESS$/ },
  { name: 'underdogCutProgress', env: /^TENNIS_UNDERDOG_CUT_PROGRESS$/ },
  { name: 'maxSpread', env: /^TENNIS_MAX_SPREAD$/ },
  { name: 'exitFloor', env: /^TENNIS_EXIT_FLOOR_FEES$/ },
  { name: 'loserStop', env: /LOSER_STOP/ },
];
/** Swept on R only and reported as a lead (section 5): never an A2 knob. */
const R_ONLY = /^(TENNIS_CONF_DEPTH|confDepth)$/;

const knobIndex = (key: string) => {
  const i = A1_KNOBS.findIndex((k) => k.env.test(key) || k.name === key);
  return i < 0 ? A1_KNOBS.length : i;
};
const knobName = (key: string) => { const i = knobIndex(key); return i < A1_KNOBS.length ? A1_KNOBS[i].name : key; };

type Ov = Record<string, string | number | boolean>;
const ovKey = (o: Ov) => JSON.stringify(Object.keys(o).sort().map((k) => [k, String(o[k])]));

interface MergedRun { id: string; overrides: Ov; fill: ConfigRun['fill']; placebo?: 'coin'; stratum: ConfigRun['stratum']; days: Map<string, ConfigDay> }

function mergeRuns(runs: ConfigRun[]): MergedRun[] {
  const by = new Map<string, MergedRun>();
  for (const r of runs) {
    const key = `${r.stratum}|${r.fill}|${r.placebo ?? ''}|${r.id}`;
    let m = by.get(key);
    if (!m) by.set(key, (m = { id: r.id, overrides: r.overrides, fill: r.fill, placebo: r.placebo, stratum: r.stratum, days: new Map() }));
    for (const d of r.days) {
      const cur = m.days.get(d.day);
      if (!cur) { m.days.set(d.day, { ...d, legs: { ...d.legs } }); continue; }
      cur.matches += d.matches; cur.traded += d.traded; cur.entries += d.entries; cur.pnl += d.pnl; cur.gross += d.gross;
      cur.fees += d.fees; cur.breaches += d.breaches; cur.unresolved += d.unresolved;
      for (const [k, v] of Object.entries(d.legs)) cur.legs[k] = (cur.legs[k] ?? 0) + v;
    }
  }
  return [...by.values()];
}

/** Day clusters of one config: unit = entry (or match), each day's pnl spread evenly over its units. */
function dayStats(days: Iterable<ConfigDay>, unit: (d: ConfigDay) => number): { total: ClusterStats; folds: Record<string, ClusterStats> } {
  const total = emptyStats(), folds: Record<string, ClusterStats> = {};
  for (const d of days) {
    const k = unit(d);
    if (!(k > 0) && d.pnl === 0) continue;
    for (const s of [total, (folds[d.day.slice(0, 7)] ??= emptyStats())]) {
      s.n += k; s.sum += d.pnl; s.sumSq += k > 0 ? (d.pnl * d.pnl) / k : 0;
      s.clusters++; s.cSumSq += d.pnl * d.pnl; s.cNSq += k * k; s.cNSum += k * d.pnl;
    }
  }
  return { total, folds };
}

/** Day-paired difference of two runs over the days both cover, where either traded. */
function pairDays(a: Map<string, ConfigDay>, b: Map<string, ConfigDay>): PairDiff {
  const out: PairDiff = { clusters: 0, sum: 0, sumSq: 0 };
  for (const [day, x] of a) {
    const y = b.get(day);
    if (!y || (!(x.entries > 0) && !(y.entries > 0) && x.pnl === 0 && y.pnl === 0)) continue;
    const diff = x.pnl - y.pnl;
    out.clusters++; out.sum += diff; out.sumSq += diff * diff;
  }
  return out;
}

const sortLevels = (ls: string[]) => {
  const rest = ls.filter((l) => l !== 'prod');
  const numeric = rest.every((l) => Number.isFinite(Number(l)));
  rest.sort((a, b) => (numeric ? Number(a) - Number(b) : a.localeCompare(b)));
  return [...(ls.includes('prod') ? ['prod'] : []), ...rest];
};

/** Family A: aggregate ConfigRun[] (several slices of the same config id are merged by id) into per-config ClusterStats
 *  where each DAY is a cluster and the unit is one entry (day pnl spread over its entries: n = entries, sum = pnl,
 *  cluster sums from ConfigDay); folds = months. Then the same funnel as B: placebo = the config run with placebo 'coin'
 *  and the same overrides (paired by day), stress = the same config under fill F2. Also report A1 one-at-a-time
 *  sensitivity per knob (range of mean net per match across its levels) and the pairwise matrices as markdown heat
 *  tables (mean net $ per match, with clustered t), and pick the 6 most sensitive knobs by the pre-registered rule.
 *
 *  Choices beyond the spec: the analysis runs on one stratum (o.stratum, default H when any H run is present: strata are
 *  never pooled). An override every primary run carries with the same value (e.g. TENNIS_TRAIL_RATCHET=false on H) is
 *  context, not a knob: it is ignored when finding the baseline and each config's knob. The baseline is the level
 *  'prod' of every knob. The BH design size defaults to the number of primary (F1, no placebo) configs. A config with
 *  no F2 or placebo run cannot be flagged; `needs` names the missing runs when everything else passes. TENNIS_CONF_DEPTH
 *  (R only) is never an A2 knob. */
export function discoverA(runs: ConfigRun[], o: { q?: number; minN?: number; minDays?: number; baselineId?: string; minFoldShare?: number; minFoldN?: number; designSize?: number; stratum?: 'H' | 'R' } = {}): {
  perConfig: Array<{ id: string; overrides: Record<string, unknown>; matches: number; entries: number; pnl: number; perMatch: number; perHour24: number; t: number; p: number; foldShare: number; breaches: number; stressPnl?: number; placeboZ?: number; flagged: boolean; why: string[]; tMatch: number; days: number; needs: string[] }>;
  sensitivity: Array<{ knob: string; range: number; levels: Array<{ level: string; perMatch: number; t: number }> }>;
  top6: string[]; markdown: string; baselineId?: string; pbo: { pbo: number; combos: number };
} {
  const d = defaults(o);
  const merged = mergeRuns(runs);
  const stratum = o.stratum ?? (merged.some((r) => r.stratum === 'H') ? 'H' : 'R');
  const inS = merged.filter((r) => r.stratum === stratum);
  const primary = inS.filter((r) => r.fill === 'F1' && !r.placebo);
  const stressBy = new Map<string, MergedRun>(), placeboBy = new Map<string, MergedRun>();
  for (const r of inS) {
    if (r.fill === 'F2' && !r.placebo && !stressBy.has(ovKey(r.overrides))) stressBy.set(ovKey(r.overrides), r);
    if (r.fill === 'F1' && r.placebo === 'coin' && !placeboBy.has(ovKey(r.overrides))) placeboBy.set(ovKey(r.overrides), r);
  }

  // Overrides shared by every primary run (same value) are context, not knobs.
  const common = new Set<string>();
  if (primary.length >= 2) {
    for (const [k, v] of Object.entries(primary[0].overrides)) if (primary.every((r) => k in r.overrides && String(r.overrides[k]) === String(v))) common.add(k);
  }
  const knobsOf = (r: MergedRun): Ov => Object.fromEntries(Object.entries(r.overrides).filter(([k]) => !common.has(k)));

  const m = Math.max(o.designSize ?? 0, primary.length);
  const rows = primary.map((r) => {
    const days = [...r.days.values()].sort((a, b) => a.day.localeCompare(b.day));
    const e = dayStats(days, (x) => x.entries), pm = dayStats(days, (x) => x.matches);
    const ct = clusteredT(e.total), cm = clusteredT(pm.total);
    const sized = e.total.n >= d.minN && e.total.clusters >= d.minDays;
    const p = sized ? (Number.isNaN(ct.t) ? 1 : tSf(ct.t, ct.df)) : 1;
    const matches = days.reduce((a, x) => a + x.matches, 0), pnl = e.total.sum;
    const st = stressBy.get(ovKey(r.overrides)), pl = placeboBy.get(ovKey(r.overrides));
    const stressPnl = st ? [...st.days.values()].reduce((a, x) => a + x.pnl, 0) : undefined;
    const stressEntries = st ? [...st.days.values()].reduce((a, x) => a + x.entries, 0) : 0;
    const placeboZ = pl ? pairedZ(pairDays(r.days, pl.days)).z : undefined;
    return {
      r, e, ct, cm, sized, p, matches, pnl, stressPnl, stressEntries, placeboZ,
      breaches: days.reduce((a, x) => a + x.breaches, 0),
      perHour: days.length ? perHour24(pnl, days[0].day, days[days.length - 1].day) : NaN,
      knobs: knobsOf(r),
    };
  });
  const testedIdx = rows.map((x, i) => (x.sized ? i : -1)).filter((i) => i >= 0);
  const rej = bhReject(testedIdx.map((i) => rows[i].p), d.q, m);
  const bhSet = new Set([...rej].map((k) => testedIdx[k]));
  const cut = bhCutoff(d.q, bhSet.size, m);
  const judged = rows.map((x, i) => {
    const fs = foldShareOf(x.e.folds, d.minFoldN);
    return judge({
      n: x.e.total.n, days: x.e.total.clusters, mean: x.ct.mean, t: x.ct.t, p: x.p, df: x.ct.df, sized: x.sized, bh: bhSet.has(i),
      foldShare: fs.share, foldsQ: fs.qualified, foldsPos: fs.positive,
      stressMean: x.stressPnl === undefined ? NaN : x.stressEntries > 0 ? x.stressPnl / x.stressEntries : x.stressPnl,
      hasStress: x.stressPnl !== undefined, placeboZ: x.placeboZ ?? NaN, hasPlacebo: x.placeboZ !== undefined, breaches: x.breaches,
    }, d, cut);
  });
  const perConfig = rows.map((x, i) => ({
    id: x.r.id, overrides: x.r.overrides as Record<string, unknown>, matches: x.matches, entries: x.e.total.n, pnl: x.pnl,
    perMatch: x.matches > 0 ? x.pnl / x.matches : NaN, perHour24: x.perHour, t: x.ct.t, p: x.p, foldShare: judged[i].foldShare,
    breaches: x.breaches, stressPnl: x.stressPnl, placeboZ: x.placeboZ, flagged: judged[i].pass, why: judged[i].rules.map((r) => r.msg),
    tMatch: x.cm.t, days: x.e.total.clusters, needs: judged[i].needs,
  }));

  // Baseline: the named id, else the primary run without (non-context) overrides.
  const bIdx = o.baselineId !== undefined ? rows.findIndex((x) => x.r.id === o.baselineId) : rows.findIndex((x) => Object.keys(x.knobs).length === 0);
  const baseline = bIdx >= 0 ? rows[bIdx] : undefined;
  const cellOf = (x: (typeof rows)[number]) => ({ perMatch: x.matches > 0 ? x.pnl / x.matches : NaN, t: x.cm.t });

  // A1 one-at-a-time sensitivity: levels of each single-override config plus the baseline as 'prod'.
  const byKnob = new Map<string, Map<string, { perMatch: number; t: number }>>();
  rows.forEach((x, i) => {
    if (i === bIdx) return;
    const ks = Object.keys(x.knobs);
    if (ks.length !== 1) return;
    const lv = byKnob.get(ks[0]) ?? new Map();
    byKnob.set(ks[0], lv);
    if (!lv.has(String(x.knobs[ks[0]]))) lv.set(String(x.knobs[ks[0]]), cellOf(x));
  });
  const sensitivity = [...byKnob.entries()].map(([knob, lv]) => {
    if (baseline) lv.set('prod', cellOf(baseline));
    const levels = sortLevels([...lv.keys()]).map((level) => ({ level, ...lv.get(level)! }));
    const vals = levels.map((l) => l.perMatch).filter(Number.isFinite);
    return { knob, range: vals.length >= 2 ? Math.max(...vals) - Math.min(...vals) : NaN, levels };
  }).sort((a, b) => {
    const ra = Number.isNaN(a.range) ? -Infinity : a.range, rb = Number.isNaN(b.range) ? -Infinity : b.range;
    if (Math.abs(ra - rb) > 1e-12 && ra !== rb) return rb - ra;
    return knobIndex(a.knob) - knobIndex(b.knob) || a.knob.localeCompare(b.knob);
  });
  const top6 = sensitivity.filter((s) => !R_ONLY.test(s.knob) && Number.isFinite(s.range)).slice(0, 6).map((s) => s.knob);

  // Pairwise heat tables: two-override configs, completed with the one-at-a-time configs (the other knob at 'prod').
  const pairKeys = new Map<string, [string, string]>();
  for (const x of rows) {
    const ks = Object.keys(x.knobs);
    if (ks.length !== 2) continue;
    const [k1, k2] = ks.sort((a, b) => knobIndex(a) - knobIndex(b) || a.localeCompare(b));
    pairKeys.set(`${k1}|${k2}`, [k1, k2]);
  }
  const heat: string[] = [];
  for (const [k1, k2] of [...pairKeys.values()].sort((a, b) => knobIndex(a[0]) - knobIndex(b[0]) || knobIndex(a[1]) - knobIndex(b[1]))) {
    const grid = new Map<string, { perMatch: number; t: number }>();
    const put = (a: string, b: string, v: { perMatch: number; t: number }) => { if (!grid.has(`${a}|${b}`)) grid.set(`${a}|${b}`, v); };
    rows.forEach((x, i) => {
      const ks = Object.keys(x.knobs);
      if (ks.length === 2 && k1 in x.knobs && k2 in x.knobs) put(String(x.knobs[k1]), String(x.knobs[k2]), cellOf(x));
      else if (ks.length === 1 && ks[0] === k1) put(String(x.knobs[k1]), 'prod', cellOf(x));
      else if (ks.length === 1 && ks[0] === k2) put('prod', String(x.knobs[k2]), cellOf(x));
      else if (i === bIdx) put('prod', 'prod', cellOf(x));
    });
    const rl = sortLevels([...new Set([...grid.keys()].map((k) => k.split('|')[0]))]);
    const cl = sortLevels([...new Set([...grid.keys()].map((k) => k.split('|')[1]))]);
    let best = -Infinity;
    for (const v of grid.values()) if (Number.isFinite(v.perMatch) && v.perMatch > best) best = v.perMatch;
    heat.push(`#### ${knobName(k1)} (rows) x ${knobName(k2)} (columns): mean net $ per match (clustered t); † = t >= 1.64, bold = best`, '');
    heat.push(`| ${knobName(k1)} \\ ${knobName(k2)} | ${cl.join(' | ')} |`, `|---|${cl.map(() => '---').join('|')}|`);
    for (const a of rl) {
      heat.push(`| ${a} | ${cl.map((b) => {
        const v = grid.get(`${a}|${b}`);
        if (!v) return '';
        const s = `${fmt(v.perMatch, 3)} (${fmt(v.t, 1)})${v.t >= 1.64 ? '†' : ''}`;
        return v.perMatch === best ? `**${s}**` : s;
      }).join(' | ')} |`);
    }
    heat.push('');
  }

  // CSCV over the discovery months: net $ per match of each primary config per month (0 without matches).
  const months = [...new Set(rows.flatMap((x) => [...x.r.days.keys()].map((k) => k.slice(0, 7))))].sort();
  const perf = rows.map((x) => months.map((mo) => {
    let pnl = 0, n = 0;
    for (const [day, v] of x.r.days) if (day.startsWith(mo)) { pnl += v.pnl; n += v.matches; }
    return n > 0 ? pnl / n : 0;
  }));
  const pbo = rows.length >= 2 && months.length >= 2 ? cscvPbo(perf) : { pbo: NaN, combos: 0, logits: [] };

  // Markdown
  const order = rows.map((_, i) => i).sort((a, b) => Number(judged[b].pass) - Number(judged[a].pass) || (Number.isNaN(rows[b].ct.t) ? -Infinity : rows[b].ct.t) - (Number.isNaN(rows[a].ct.t) ? -Infinity : rows[a].ct.t));
  const shown = order.filter((i, k) => judged[i].pass || k < 30 || i === bIdx);
  const ovText = (x: Ov) => Object.entries(x).map(([k, v]) => `${knobName(k)}=${v}`).join(', ') || 'production';
  const cfgRow = (i: number) => {
    const x = rows[i], j = judged[i], pc = perConfig[i];
    const fails = j.rules.filter((r) => !r.ok).map((r) => r.msg).join('; ') || 'all rules pass';
    return `| ${cell(x.r.id)}${i === bIdx ? ' (baseline)' : ''} | ${cell(ovText(x.knobs))} | ${x.matches} | ${x.e.total.n} | ${x.e.total.clusters} | ${fmt(pc.perMatch, 3)} | ${fmt(x.ct.mean, 4)} | ${fmt(x.perHour, 3)} | ${fmt(x.ct.t, 2)} | ${fmtP(x.p)} | ${j.foldsPos}/${j.foldsQ} | ${x.breaches} | ${x.stressPnl === undefined ? '-' : fmt(x.stressPnl, 2)} | ${fmt(x.placeboZ ?? NaN, 2)} | ${j.pass ? 'FLAG' : j.needs.length ? `needs ${j.needs.join('+')}` : ''} | ${cell(fails)} |`;
  };
  const b = baseline;
  const md = [
    `## Family A discovery (${stratum}, F1)`,
    '',
    b ? `Baseline ${b.r.id}: ${b.matches} matches, ${b.e.total.n} entries on ${b.e.total.clusters} days, net ${fmt(b.pnl, 2)} $ (${fmt(b.matches ? b.pnl / b.matches : NaN, 3)} $/match, ${fmt(b.perHour, 3)} $/h over 24 h), clustered t ${fmt(b.ct.t, 2)}.` : 'Baseline: no primary run without overrides.',
    ...(common.size ? [`Context overrides on every run (not knobs): ${[...common].map((k) => `${k}=${primary[0].overrides[k]}`).join(', ')}.`] : []),
    `Design size m = ${m}, BH q = ${d.q}; tested (>= ${d.minN} entries on >= ${d.minDays} match-days): ${testedIdx.length}; BH rejections ${bhSet.size} (cutoff p <= ${fmtP(cut)}).`,
    `Funnel (sequential): ${funnelCounts(judged)}.`,
    `CSCV PBO over ${months.length} months (net $ per match per month, all primary configs): ${Number.isNaN(pbo.pbo) ? '-' : pbo.pbo.toFixed(3)} (${pbo.combos} splits).`,
    '',
    '### Configs (flagged first, then by clustered t; top 30 and the baseline)',
    '',
    '| config | knobs | matches | entries | days | $/match | $/entry | $/h 24h | t | p | folds+ | breaches | F2 $ | placebo z | flag | failed rules |',
    '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|',
    ...shown.map(cfgRow),
    '',
    '### A1 one-at-a-time sensitivity (range of mean net $ per match across levels; prod = the baseline)',
    '',
    '| # | knob | range $/match | levels: $/match (clustered t) |',
    '|---|---|---|---|',
    ...sensitivity.map((s, k) => `| ${k + 1} | ${knobName(s.knob)} | ${Number.isNaN(s.range) ? '-' : s.range.toFixed(4)} | ${s.levels.map((l) => `${l.level}: ${fmt(l.perMatch, 3)} (${fmt(l.t, 1)})`).join('; ')} |`),
    '',
    `**A2 knobs (6 largest ranges, ties to the earlier pre-registered knob${byKnob.has('TENNIS_CONF_DEPTH') ? '; confDepth is R-only and excluded' : ''}):** ${top6.map(knobName).join(', ') || '-'}`,
    '',
    '### Pairwise heat tables',
    '',
    ...(heat.length ? heat : ['_no two-knob configs_', '']),
  ].filter((l, k, a) => !(l === '' && a[k - 1] === '')).join('\n');

  return { perConfig, sensitivity, top6, markdown: md, baselineId: baseline?.r.id, pbo: { pbo: pbo.pbo, combos: pbo.combos } };
}
