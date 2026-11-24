// Candidate generation for the depth simulator's calibration sweep (research/historyTwin.ts --stage sweep). Pure functions: no
// files, no clock, no Math.random; every draw comes from a generator seeded by the generation and the population, so the same
// inputs give the same candidates on every runner and on every shard (a shard computes the whole population and takes its slice).
//
//   generation 0   candidate 0 is TODAY'S defaults, the rest a Latin-hypercube sample of DEPTH_PARAM_SPACE (log scale where the
//                  space says so): each parameter's range is cut into n strata and every stratum is used exactly once.
//   generation g>0 a cross-entropy step around the parents: the best 20 percent of the parents file (by loss) give a mean and a
//                  standard deviation per parameter, in the transformed space (log for the log-scaled ones); candidates are
//                  Gaussian around that mean with the sd shrunk (CEM_SHRINK) and floored (CEM_SD_FLOOR of the range, so a
//                  generation never collapses to a point), clipped to the bounds. Candidate 0 is the elite mean itself.
//
// The loss is the judge's (research/historyTwin.ts): the leave-one-day-out adversary AUC over all 13 features, on the FIT days.

import { hashStr } from './historyReplay';
import { DEFAULT_DEPTH_SIM_PARAMS, DEPTH_PARAM_NAMES, DEPTH_PARAM_SPACE, resolveDepthSimParams, type DepthSimParams } from './depthSim';

/** Bumped when the way candidates are drawn changes (it is part of every seed). */
export const SWEEP_VERSION = 'sweep-1';
/** The share of the parents (best loss first) that an elite step is fitted to. */
export const ELITE_FRACTION = 0.2;
/** The elite sd is multiplied by this for the next generation's draws. */
export const CEM_SHRINK = 0.7;
/** The smallest sd of a draw, as a share of the parameter's range in the transformed space. */
export const CEM_SD_FLOOR = 0.02;
/** At least this many parents make an elite (a sd needs two). */
export const MIN_ELITE = 2;

/** One candidate as the sweep judged it (small: this is what lands on Drive and what the next generation reads). */
export interface SweepResult {
  gen: number;
  /** Position in the generation's population (0 .. population - 1). */
  index: number;
  params: DepthSimParams;
  /** The all-feature leave-one-day-out adversary AUC (lower is better). 1 when the candidate left too few twin rows to judge. */
  loss: number;
  /** Each feature's own AUC, and the AUC within each regime (null: too few lives there), as the verdict prints them. */
  features: Record<string, number>;
  regimes: Record<string, number | null>;
  /** The three features that give the twin away most (own AUC farthest from 0.5). */
  top3: Array<{ name: string; auc: number }>;
  realRows: number;
  twinRows: number;
  /** Seconds this candidate took (fill-in, features and judge). */
  seconds: number;
  /** Set when the candidate could not be judged (and its loss is 1). */
  note?: string;
}

/** What one shard writes: its slice of the generation, rewritten after each candidate (`complete` when it is whole). */
export interface SweepShardFile {
  kind: 'sweep-shard';
  version: string;
  gen: number;
  shard: number;
  shards: number;
  perShard: number;
  population: number;
  fitDays: string[];
  /** The days the depth model was fitted on (a sweep's model is fitted on the fit days only). */
  modelDays: string[];
  complete: boolean;
  results: SweepResult[];
}

/** A seeded uniform generator in [0, 1) (mulberry32). */
export function uniform(seed: number): () => number {
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const normalDraw = (u: () => number) => Math.sqrt(-2 * Math.log(Math.max(u(), 1e-12))) * Math.cos(2 * Math.PI * u());
const seedFor = (what: string, gen: number, n: number) => hashStr(`${SWEEP_VERSION}|${what}|gen=${gen}|n=${n}`) >>> 0;

type Name = keyof DepthSimParams;
/** A value in the space the sweep samples in (log for the log-scaled parameters). */
export const toSpace = (name: Name, v: number): number => (DEPTH_PARAM_SPACE[name].scale === 'log' ? Math.log(v) : v);
/** The other way, clipped to the bounds and rounded for the integer parameters. */
export function fromSpace(name: Name, x: number): number {
  const b = DEPTH_PARAM_SPACE[name];
  const lo = toSpace(name, b.lo), hi = toSpace(name, b.hi);
  const v = b.scale === 'log' ? Math.exp(Math.min(hi, Math.max(lo, x))) : Math.min(hi, Math.max(lo, x));
  const r = b.int ? Math.round(v) : v;
  return Math.min(b.hi, Math.max(b.lo, r));
}
const range = (name: Name) => toSpace(name, DEPTH_PARAM_SPACE[name].hi) - toSpace(name, DEPTH_PARAM_SPACE[name].lo);

/** Every parameter inside DEPTH_PARAM_SPACE (integers rounded). */
export function clipParams(p: DepthSimParams): DepthSimParams {
  const out = { ...p };
  for (const n of DEPTH_PARAM_NAMES) out[n] = fromSpace(n, toSpace(n, Math.max(p[n], 1e-12)));
  return out;
}

/** `n` points of a Latin hypercube over DEPTH_PARAM_SPACE: every parameter's range is cut into n equal strata (in the
 *  transformed space) and each stratum holds exactly one point, a seeded permutation per parameter. */
export function latinHypercube(n: number, seed: number): DepthSimParams[] {
  const u = uniform(seed), pts: DepthSimParams[] = Array.from({ length: n }, () => ({ ...DEFAULT_DEPTH_SIM_PARAMS }));
  for (const name of DEPTH_PARAM_NAMES) {
    const perm = Array.from({ length: n }, (_, i) => i);
    for (let i = n - 1; i > 0; i--) { const j = Math.floor(u() * (i + 1)); [perm[i], perm[j]] = [perm[j], perm[i]]; }
    const lo = toSpace(name, DEPTH_PARAM_SPACE[name].lo), r = range(name);
    for (let i = 0; i < n; i++) pts[i][name] = fromSpace(name, lo + ((perm[i] + u()) / n) * r);
  }
  return pts;
}

/** A parent: a candidate that was judged (a sweep's elite.json holds these). */
export interface Parent { params: Partial<DepthSimParams>; loss: number }

/** The best `max(MIN_ELITE, ceil(frac x n))` parents by loss (ties keep file order). `frac` 1 keeps them all. */
export function eliteOf<T extends { loss: number }>(parents: readonly T[], frac = ELITE_FRACTION): T[] {
  const ranked = parents.map((p, i) => [p, i] as const).filter(([p]) => Number.isFinite(p.loss)).sort((a, b) => a[0].loss - b[0].loss || a[1] - b[1]).map(([p]) => p);
  return ranked.slice(0, Math.min(ranked.length, Math.max(MIN_ELITE, Math.ceil(frac * ranked.length))));
}

/** The elite's mean and sd per parameter, in the transformed space. */
export function eliteStats(elite: readonly Parent[]): { mean: Record<Name, number>; sd: Record<Name, number> } {
  const mean = {} as Record<Name, number>, sd = {} as Record<Name, number>;
  const full = elite.map((p) => resolveDepthSimParams(p.params));
  for (const n of DEPTH_PARAM_NAMES) {
    const xs = full.map((p) => toSpace(n, Math.max(p[n], 1e-12)));
    const m = xs.reduce((a, b) => a + b, 0) / xs.length;
    mean[n] = m; sd[n] = Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / xs.length);
  }
  return { mean, sd };
}

/** `n` candidates for the next generation: candidate 0 the elite mean, the rest Gaussian around it (sd shrunk, floored),
 *  all clipped to the bounds. `eliteFrac` 1: the parents are already the elite (a sweep's elite.json). */
export function cemStep(parents: readonly Parent[], n: number, seed: number, eliteFrac = ELITE_FRACTION): DepthSimParams[] {
  const elite = eliteOf(parents, eliteFrac);
  if (!elite.length) throw new Error('the parents hold no judged candidate (a finite loss) to take an elite from');
  const { mean, sd } = eliteStats(elite);
  const u = uniform(seed), out: DepthSimParams[] = [];
  for (let c = 0; c < n; c++) {
    const p = { ...DEFAULT_DEPTH_SIM_PARAMS };
    for (const name of DEPTH_PARAM_NAMES) {
      const s = Math.max(CEM_SHRINK * sd[name], CEM_SD_FLOOR * range(name));
      p[name] = fromSpace(name, c === 0 ? mean[name] : mean[name] + s * normalDraw(u));
    }
    out.push(p);
  }
  return out;
}

/** The whole population of one generation (every shard computes it, then takes its own slice). Generation 0: the defaults and
 *  a Latin hypercube of `population - 1` points; later: a cross-entropy step around `parents` (required). */
export function generationCandidates(gen: number, population: number, parents?: readonly Parent[], eliteFrac = ELITE_FRACTION): DepthSimParams[] {
  if (!Number.isInteger(gen) || gen < 0) throw new Error(`generation must be a whole number of at least 0, got ${gen}`);
  if (!Number.isInteger(population) || population < 1) throw new Error(`a generation needs at least one candidate, got ${population}`);
  if (gen === 0) return [{ ...DEFAULT_DEPTH_SIM_PARAMS }, ...latinHypercube(population - 1, seedFor('lhs', gen, population - 1))];
  if (!parents?.length) throw new Error(`generation ${gen} needs a parents file (the previous generation's elite.json)`);
  return cemStep(parents, population, seedFor('cem', gen, population), eliteFrac);
}

/** The candidates [lo, hi) of shard `shard` of `shards` over `total` (contiguous, every one in exactly one shard). */
export function shardRange(total: number, shards: number, shard: number): [number, number] {
  if (!Number.isInteger(shards) || shards < 1) throw new Error(`shards must be a whole number of at least 1, got ${shards}`);
  if (!Number.isInteger(shard) || shard < 0 || shard >= shards) throw new Error(`shard ${shard} is not in 0..${shards - 1}`);
  return [Math.floor((total * shard) / shards), Math.floor((total * (shard + 1)) / shards)];
}

/** `i/K` as a shard spec (0-based: 0/7 .. 6/7). */
export function parseShard(s: string): { shard: number; shards: number } {
  const m = /^(\d+)\/(\d+)$/.exec(s.trim());
  if (!m) throw new Error(`--shard must look like 0/7 (shard number from 0, then how many shards), got "${s}"`);
  const shard = Number(m[1]), shards = Number(m[2]);
  shardRange(1, shards, shard);
  return { shard, shards };
}

/** Parents from a parents file's JSON: a list of judged candidates (their top 20 percent is the elite), or a sweep's elite.json
 *  `{ kind: 'sweep-elite', elite: [...] }` (already the elite: used whole). Every entry's params are checked against the known
 *  parameter names. Returns the parents and the fraction to select with. */
export function parentsFrom(json: unknown): { parents: Parent[]; frac: number } {
  const list: unknown = Array.isArray(json) ? json : (json as { elite?: unknown } | null)?.elite;
  const frac = Array.isArray(json) ? ELITE_FRACTION : 1;
  if (!Array.isArray(list) || !list.length) throw new Error('the parents file holds no candidates (expected a list, or an elite.json with an "elite" list)');
  const parents = list.map((x: any, i) => {
    if (!x || typeof x.loss !== 'number' || typeof x.params !== 'object' || !x.params) throw new Error(`parents entry ${i} has no params and numeric loss`);
    return { params: resolveDepthSimParams(x.params), loss: x.loss };
  });
  return { parents, frac };
}

/** What to do about a generation that is not whole, in one line (the message's first line is what a commit comment keeps: 400 characters).
 *  RUN is a placeholder: the workflow's collect step prints the same advice with the real run id. */
export const WHOLE_GENERATION_ADVICE = 'a red shard job (crashed, timed out): gh run rerun RUN --failed. A green but incomplete shard (budget stop): a re-run fails the same way; dispatch again with fewer sweep_candidates, or with sweep_partial=true on that dispatch (a finished run cannot be re-collected as partial)';

/** A shard that did not judge its whole slice: `have` of `of` candidates. */
export interface IncompleteShard { shard: number; have: number; of: number }

/** The candidates of a generation merged from its shard files, each exactly once. Missing shards or candidates are named; unless
 *  `partial`, they refuse the merge (a generation judged on some of its candidates is not the generation asked for). The refusal lists
 *  every incomplete shard (a green job that stopped at its budget is incomplete too, not only a failed one) and the shards with no
 *  file, and says how to get a whole generation (WHOLE_GENERATION_ADVICE). `incomplete` and `noFile` are returned for a partial merge. */
export function mergeShards(files: readonly SweepShardFile[], o: { gen: number; shards: number; perShard: number; partial?: boolean }): { results: SweepResult[]; missing: number[]; population: number; incomplete: IncompleteShard[]; noFile: number[] } {
  const population = o.shards * o.perShard, seen = new Map<number, SweepResult>(), incomplete: IncompleteShard[] = [];
  for (const f of files) {
    if (f.kind !== 'sweep-shard' || f.version !== SWEEP_VERSION) throw new Error(`a shard file is not a ${SWEEP_VERSION} shard (kind ${String((f as { kind?: unknown }).kind)}, version ${String((f as { version?: unknown }).version)})`);
    if (f.gen !== o.gen || f.shards !== o.shards || f.perShard !== o.perShard) throw new Error(`shard ${f.shard} of generation ${f.gen} (${f.shards} shards x ${f.perShard}) is not generation ${o.gen} (${o.shards} shards x ${o.perShard})`);
    const [lo, hi] = shardRange(population, o.shards, f.shard);
    for (const r of f.results) {
      if (r.gen !== o.gen || r.index < lo || r.index >= hi) throw new Error(`candidate ${r.index} (generation ${r.gen}) does not belong to shard ${f.shard} of generation ${o.gen}`);
      if (seen.has(r.index)) throw new Error(`candidate ${r.index} appears twice (two shard files cover it)`);
      seen.set(r.index, r);
    }
    if (!f.complete) incomplete.push({ shard: f.shard, have: f.results.length, of: hi - lo });
  }
  const missing = Array.from({ length: population }, (_, i) => i).filter((i) => !seen.has(i));
  const noFile = Array.from({ length: o.shards }, (_, i) => i).filter((i) => !files.some((f) => f.shard === i));
  if ((incomplete.length || missing.length) && !o.partial) {
    const gap = incomplete.length
      ? incomplete.map((x) => `shard ${x.shard} is not complete (${x.have} of ${x.of} candidates)`).join('; ')
      : `${missing.length} of ${population} candidates are missing (${missing.slice(0, 12).join(', ')}${missing.length > 12 ? ', ...' : ''})`;
    throw new Error(`${gap}${noFile.length ? `; no result file for shard ${noFile.join(', ')}` : ''}: ${WHOLE_GENERATION_ADVICE}`);
  }
  if (!seen.size) throw new Error('no candidate was judged: nothing to collect');
  return { results: [...seen.values()].sort((a, b) => a.index - b.index), missing, population, incomplete, noFile };
}

/** Results best first (lowest loss; ties by index). */
export const rankResults = (rs: readonly SweepResult[]): SweepResult[] => [...rs].sort((a, b) => a.loss - b.loss || a.index - b.index);

/** `name value, name value ...` with 4 significant digits (numbers only: for the logs). */
export function describeParams(p: Partial<DepthSimParams>): string {
  return DEPTH_PARAM_NAMES.filter((n) => p[n] !== undefined).map((n) => `${n} ${+(p[n] as number).toPrecision(4)}`).join(', ');
}
