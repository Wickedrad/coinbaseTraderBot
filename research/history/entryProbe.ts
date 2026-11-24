// The entry-state probe's pure part (round R3b, REPORT ONLY): the aggregates one (source, day) pass keeps, how they merge, and the
// lines they print. No file, clock or random number is read here (research/historyTwin.ts --stage probe does the reading and the
// writing; --stage probe-report prints from the written files alone with the same functions below).
//
// Why: R3a found that the decision model enters ETH, SOL and XRP on the twin's days and almost never on the real days (real: BTC 35,
// ETH 1, SOL 0, XRP 3 positions over the 4 DEV days; the depth twin: BTC 34, ETH 15, SOL 14, XRP 19), although the judge's own
// per-asset contract-life gaps are small. The cause has to be in the state the policy reads at entry time: the quote against the fair
// value, the spread, the volatility, the decision model's inputs, or the model's price. This keeps, per source (real, requote,
// depth), per day and per asset, a small struct of counts, sums and fixed-bin histograms of exactly those quantities (nothing per
// row is kept), policy-free: no fill, no position, no outcome label.
//
// Units: prices are dollars in the rows and cents in every struct and line. Histograms have fixed bins (the width of a bin is the
// resolution of every quantile read from it: mid 1c, spread 0.5c, the two gaps 0.25c; a quantile is the lower edge of the bin that holds
// it), so two aggregates add and a pooled aggregate is the sum of its days'. Means and standard deviations of the model's input
// features are Welford (count, mean, sum of squared deviations) and merge the way Chan's parallel formula says.
//
// A line carries counts, cents, shares and z-scores only: no timestamp, no ticker, no per-row figure (the repository is public). Days
// are named day 1..N in date order.

/** The version of what a probe file holds: a file of another version is refused by the reader. */
export const PROBE_VERSION = 1;
export const PROBE_SOURCES = ['real', 'requote', 'depth'] as const;
export type ProbeSource = (typeof PROBE_SOURCES)[number];
/** The four assets the twin trades; every row also goes into `all` (rows of another asset only there). */
export const PROBE_ASSETS = ['BTC', 'ETH', 'SOL', 'XRP'] as const;
export const PROBE_ALL = 'all';
export const PROBE_KEYS: readonly string[] = [...PROBE_ASSETS, PROBE_ALL];
/** The sampling step of the dataset builder, seconds (the spec's 15 s: the twin's own print grid). */
export const PROBE_STEP_SEC = 15;
/** The take-edge thresholds, cents (shares of rows with a taker edge at least this big). */
export const EDGE_STEPS = [0, 2, 4, 6, 10] as const;
/** Per-day lines are printed for at most this many days (more days: the pooled lines only), so the report stays inside a commit comment. */
export const MAX_DAY_LINES = 8;
/** The features with the largest |z| each twin source prints per asset, and how many of them one line carries (the comment cuts a line at 300 characters). */
export const TOP_FEATURES = 8, FEATURES_PER_LINE = 3;
/** A feature's z-score needs this many finite values on each side. */
export const MIN_Z_N = 10;

// ---- the histograms ----------------------------------------------------------------------------------------------
const W = { mid: 1, spread: 0.5, gap: 0.25 } as const;
const BINS = { mid: 100, spread: 101, gap: 201 } as const;
type HistKey = keyof typeof W;
const zeros = (n: number): number[] => new Array<number>(n).fill(0);
const r6 = (x: number): number => Math.round(x * 1e6) / 1e6; // the dollar prices are floats: 0.53 - 0.51 must land in the 2c bin
const bin = (k: HistKey, cents: number): number => Math.max(0, Math.min(BINS[k] - 1, Math.floor(r6(cents) / W[k])));

/** The lower edge of the bin that holds the p-quantile (p in [0, 1]) of a histogram; NaN when it is empty. */
export function histQuantile(h: readonly number[], width: number, p: number): number {
  let total = 0;
  for (const c of h) total += c;
  if (!(total > 0)) return NaN;
  const target = p * total;
  let cum = 0;
  for (let i = 0; i < h.length; i++) { cum += h[i]; if (h[i] > 0 && cum >= target) return i * width; }
  return (h.length - 1) * width;
}

// ---- the aggregate -----------------------------------------------------------------------------------------------
export interface FeatStat { n: number; mean: number; m2: number }
export interface ProbeAgg {
  /** Rows counted. */
  n: number;
  /** Rows left out because a number the line needs was not finite (kept so a probe that drops rows says so). */
  bad: number;
  mid: number[];
  spread: { sum: number; h: number[] };
  fvGap: { sum: number; ge3: number; ge5: number; ge10: number; h: number[] };
  pGap: { sum: number; signed: number; h: number[] };
  edge: { ge0: number; ge2: number; ge4: number; ge6: number; ge10: number };
  sigma: number; sigmaPricing: number; tau: number;
  fx: Record<string, FeatStat>;
}

export const newAgg = (): ProbeAgg => ({
  n: 0, bad: 0, mid: zeros(BINS.mid), spread: { sum: 0, h: zeros(BINS.spread) }, fvGap: { sum: 0, ge3: 0, ge5: 0, ge10: 0, h: zeros(BINS.gap) }, pGap: { sum: 0, signed: 0, h: zeros(BINS.gap) },
  edge: { ge0: 0, ge2: 0, ge4: 0, ge6: 0, ge10: 0 }, sigma: 0, sigmaPricing: 0, tau: 0, fx: {},
});

/** What one dataset row gives the probe: the quote and fair value in dollars, the model's price, the policy's sigma and the pricing sigma, seconds to close, and the model's input features. */
export interface ProbeRow { bid: number; ask: number; fv: number; mid: number; pModel: number; sigma: number; sigmaPricing: number; tauSec: number; fx: Record<string, number> }

/** Adds one row. `features`: the names of the decision model's inputs (each is a Welford stat of its finite values); a row with a number the
 *  struct needs not finite is counted in `bad` and nothing else. */
export function addRow(a: ProbeAgg, r: ProbeRow, features: readonly string[]): void {
  const need = [r.bid, r.ask, r.fv, r.mid, r.pModel, r.sigma, r.sigmaPricing, r.tauSec];
  if (!need.every(Number.isFinite)) { a.bad++; return; }
  a.n++;
  a.mid[bin('mid', r.mid * 100)]++;
  const spread = r6((r.ask - r.bid) * 100), fvGap = r6(Math.abs(r.fv - r.mid) * 100), pGap = r6(Math.abs(r.pModel - r.mid) * 100), edge = r6(Math.max(r.pModel - r.ask, r.bid - r.pModel) * 100);
  a.spread.sum += spread; a.spread.h[bin('spread', spread)]++;
  a.fvGap.sum += fvGap; a.fvGap.h[bin('gap', fvGap)]++;
  if (fvGap >= 3) a.fvGap.ge3++; if (fvGap >= 5) a.fvGap.ge5++; if (fvGap >= 10) a.fvGap.ge10++;
  a.pGap.sum += pGap; a.pGap.signed += r6((r.pModel - r.mid) * 100); a.pGap.h[bin('gap', pGap)]++;
  if (edge >= 0) a.edge.ge0++; if (edge >= 2) a.edge.ge2++; if (edge >= 4) a.edge.ge4++; if (edge >= 6) a.edge.ge6++; if (edge >= 10) a.edge.ge10++;
  a.sigma += r.sigma; a.sigmaPricing += r.sigmaPricing; a.tau += r.tauSec;
  for (const k of features) {
    const x = r.fx[k];
    if (typeof x !== 'number' || !Number.isFinite(x)) continue;
    const s = (a.fx[k] ??= { n: 0, mean: 0, m2: 0 });
    s.n++; const d = x - s.mean; s.mean += d / s.n; s.m2 += d * (x - s.mean);
  }
}

const addArr = (x: readonly number[], y: readonly number[]): number[] => x.map((v, i) => v + (y[i] ?? 0));
/** The sum of two aggregates (a new one; the days of a pooled aggregate are added in date order, so the result is the same every time). */
export function mergeAgg(a: ProbeAgg, b: ProbeAgg): ProbeAgg {
  const fx: Record<string, FeatStat> = {};
  for (const k of [...Object.keys(a.fx), ...Object.keys(b.fx).filter((x) => !(x in a.fx))]) {
    const x = a.fx[k], y = b.fx[k];
    if (!x || !y) { fx[k] = { ...(x ?? y) }; continue; }
    const n = x.n + y.n, d = y.mean - x.mean;
    fx[k] = { n, mean: x.mean + d * y.n / n, m2: x.m2 + y.m2 + d * d * x.n * y.n / n };
  }
  return {
    n: a.n + b.n, bad: a.bad + b.bad, mid: addArr(a.mid, b.mid),
    spread: { sum: a.spread.sum + b.spread.sum, h: addArr(a.spread.h, b.spread.h) },
    fvGap: { sum: a.fvGap.sum + b.fvGap.sum, ge3: a.fvGap.ge3 + b.fvGap.ge3, ge5: a.fvGap.ge5 + b.fvGap.ge5, ge10: a.fvGap.ge10 + b.fvGap.ge10, h: addArr(a.fvGap.h, b.fvGap.h) },
    pGap: { sum: a.pGap.sum + b.pGap.sum, signed: a.pGap.signed + b.pGap.signed, h: addArr(a.pGap.h, b.pGap.h) },
    edge: { ge0: a.edge.ge0 + b.edge.ge0, ge2: a.edge.ge2 + b.edge.ge2, ge4: a.edge.ge4 + b.edge.ge4, ge6: a.edge.ge6 + b.edge.ge6, ge10: a.edge.ge10 + b.edge.ge10 },
    sigma: a.sigma + b.sigma, sigmaPricing: a.sigmaPricing + b.sigmaPricing, tau: a.tau + b.tau, fx,
  };
}

/** The figures a line prints, read off an aggregate (undefined when it holds no row). Cents, shares in [0, 1]. */
export interface ProbeSummary {
  n: number;
  spread: { mean: number; p50: number; p90: number };
  fvGap: { mean: number; p50: number; p90: number; ge3: number; ge5: number; ge10: number };
  pGap: { mean: number; p50: number; p90: number; signed: number };
  edge: Record<`ge${(typeof EDGE_STEPS)[number]}`, number>;
  sigma: number; sigmaPricing: number; sigmaRatio: number; tau: number;
  mid: { p10: number; p50: number; p90: number };
}
export function summarize(a: ProbeAgg | undefined): ProbeSummary | undefined {
  if (!a || !(a.n > 0)) return undefined;
  const n = a.n, q = (h: readonly number[], w: number, p: number) => histQuantile(h, w, p);
  return {
    n,
    spread: { mean: a.spread.sum / n, p50: q(a.spread.h, W.spread, 0.5), p90: q(a.spread.h, W.spread, 0.9) },
    fvGap: { mean: a.fvGap.sum / n, p50: q(a.fvGap.h, W.gap, 0.5), p90: q(a.fvGap.h, W.gap, 0.9), ge3: a.fvGap.ge3 / n, ge5: a.fvGap.ge5 / n, ge10: a.fvGap.ge10 / n },
    pGap: { mean: a.pGap.sum / n, p50: q(a.pGap.h, W.gap, 0.5), p90: q(a.pGap.h, W.gap, 0.9), signed: a.pGap.signed / n },
    edge: { ge0: a.edge.ge0 / n, ge2: a.edge.ge2 / n, ge4: a.edge.ge4 / n, ge6: a.edge.ge6 / n, ge10: a.edge.ge10 / n },
    sigma: a.sigma / n, sigmaPricing: a.sigmaPricing / n, sigmaRatio: a.sigma > 0 ? a.sigmaPricing / a.sigma : NaN, tau: a.tau / n,
    mid: { p10: q(a.mid, W.mid, 0.1), p50: q(a.mid, W.mid, 0.5), p90: q(a.mid, W.mid, 0.9) },
  };
}

/** The sample standard deviation of a feature stat (NaN under two values). */
export const statSd = (s: FeatStat | undefined): number => (s && s.n > 1 ? Math.sqrt(Math.max(0, s.m2) / (s.n - 1)) : NaN);

// ---- the file one (source, day) pass writes -----------------------------------------------------------------------
export interface ProbeFile {
  v: number;
  src: ProbeSource;
  day: string;
  /** The sampling step (s) and the entry window (seconds before close, earliest then latest) the rows came from. */
  step: number;
  window: [number, number];
  /** The decision model's input features, in the model's order. */
  features: string[];
  /** Was the day before read (warm-up)? Without it the first rows of the day start cold. */
  warm: boolean;
  /** Real only: the real contracts the twin's contract list kept, and those it did not (dropped). */
  contracts?: { kept: number; dropped: number };
  /** The volatility model the dataset builder applied: validated (its multiplier is on), unvalidated (loaded, multiplier 1) or none. */
  volModel: 'validated' | 'unvalidated' | 'none';
  assets: Record<string, ProbeAgg>;
}

const DAY_RE = /^\d{4}-\d{2}-\d{2}$/;
/** A parsed probe file, or a reason it is not one (the reader refuses it with the file's name, never a guess). */
export function checkProbeFile(x: unknown): string | undefined {
  const f = x as Partial<ProbeFile> | null;
  if (!f || typeof f !== 'object') return 'not an object';
  if (f.v !== PROBE_VERSION) return `version ${String(f.v)}, this code reads version ${PROBE_VERSION}`;
  if (!PROBE_SOURCES.includes(f.src as ProbeSource)) return `unknown source ${String(f.src).slice(0, 20)}`;
  if (typeof f.day !== 'string' || !DAY_RE.test(f.day)) return 'no day';
  if (!f.assets || typeof f.assets !== 'object' || !PROBE_KEYS.every((k) => f.assets![k] && Array.isArray(f.assets![k].mid) && f.assets![k].mid.length === BINS.mid)) return 'no per-asset aggregates of this shape';
  if (!Array.isArray(f.features)) return 'no feature list';
  return undefined;
}

/** The file `probe-days.json` the workflow step writes beside the probe files: the days the dispatch asked for, in date order. It lets a re-read keep the
 *  numbering of the request (day k = the k-th requested day) when a day has no file at all (its process died, or the limit cut it), instead of renumbering
 *  the days that have files. Dates live in this file only (kept on Drive with the others, like the file names); no printed line carries one. */
export interface ProbeDaysFile { v: number; days: string[] }
export const PROBE_DAYS_FILE = 'probe-days.json';
/** Why a parsed `probe-days.json` is not one (undefined when it is): a version this code does not read, days that are not YYYY-MM-DD, out of order or twice. */
export function checkProbeDays(x: unknown): string | undefined {
  const f = x as Partial<ProbeDaysFile> | null;
  if (!f || typeof f !== 'object') return 'not an object';
  if (f.v !== PROBE_VERSION) return `version ${String(f.v)}, this code reads version ${PROBE_VERSION}`;
  if (!Array.isArray(f.days) || !f.days.length) return 'no days';
  if (!f.days.every((d) => typeof d === 'string' && DAY_RE.test(d))) return 'a day is not YYYY-MM-DD';
  if (f.days.some((d, i) => i > 0 && !(f.days![i - 1] < d))) return 'the days are not in date order, once each';
  return undefined;
}

// ---- the lines -----------------------------------------------------------------------------------------------------
const fx1 = (x: number): string => (Number.isFinite(x) ? x.toFixed(1) : 'n/a');
const fx2 = (x: number): string => (Number.isFinite(x) ? x.toFixed(2) : 'n/a');
const c1 = (x: number): string => `${fx1(x)}c`;
const sg1 = (x: number): string => (Number.isFinite(x) ? `${x >= 0 ? '+' : ''}${x.toFixed(1)}` : 'n/a');
const pct = (x: number): string => (Number.isFinite(x) ? `${(x * 100).toFixed(1)}%` : 'n/a');
const sci = (x: number): string => (Number.isFinite(x) ? x.toExponential(2) : 'n/a');
const num3 = (x: number): string => (Number.isFinite(x) ? (Math.abs(x) < 1e-9 ? '0' : String(Number(x.toPrecision(3)))) : 'n/a'); // floating-point noise around zero is a 0
const ratio = (a: number, b: number): string => (b > 0 && Number.isFinite(a) ? fx2(a / b) : 'n/a');
const zfmt = (z: number): string => `${z >= 0 ? '+' : ''}${z.toFixed(2)}`;

/** The two lines of one source's one asset (the second starts with the same words: a line is cut at 300 characters in a commit comment). */
export function sourceLines(src: string, asset: string, s: ProbeSummary | undefined, dayTag = ''): string[] {
  const head = `[twin] probe ${src}${dayTag} ${asset}:`;
  if (!s) return [`${head} rows 0`];
  return [
    `${head} rows ${s.n}, spread ${c1(s.spread.mean)} (p50 ${fx1(s.spread.p50)} p90 ${fx1(s.spread.p90)}), |fv-mid| ${c1(s.fvGap.mean)} (p50 ${fx1(s.fvGap.p50)} p90 ${fx1(s.fvGap.p90)}; >=3c ${pct(s.fvGap.ge3)} >=5c ${pct(s.fvGap.ge5)} >=10c ${pct(s.fvGap.ge10)}), |pModel-mid| ${c1(s.pGap.mean)} (p50 ${fx1(s.pGap.p50)} p90 ${fx1(s.pGap.p90)}), pModel-mid ${sg1(s.pGap.signed)}c`,
    `${head} take edge >=0c ${pct(s.edge.ge0)} >=2c ${pct(s.edge.ge2)} >=4c ${pct(s.edge.ge4)} >=6c ${pct(s.edge.ge6)} >=10c ${pct(s.edge.ge10)}, sigma ${sci(s.sigma)}, sigmaPricing/sigma ${s.sigmaRatio.toFixed(3)}, tau ${s.tau.toFixed(0)} s, mid p10/p50/p90 ${s.mid.p10.toFixed(0)}/${s.mid.p50.toFixed(0)}/${s.mid.p90.toFixed(0)}c`,
  ];
}

/** The line of a twin source against real, one asset (a day or pooled): ratios of counts and means, and the shares side by side (twin vs real). */
export function versusLine(twin: string, asset: string, t: ProbeSummary | undefined, r: ProbeSummary | undefined, dayTag = ''): string {
  const head = `[twin] probe ${twin} vs real${dayTag} ${asset}:`;
  if (!t || !r) return `${head} rows ${t?.n ?? 0} vs ${r?.n ?? 0}, nothing to compare`;
  const sh = (a: number, b: number) => `${pct(a)} vs ${pct(b)}`;
  return `${head} rows ratio ${ratio(t.n, r.n)}, spread ratio ${ratio(t.spread.mean, r.spread.mean)}, |fv-mid| ratio ${ratio(t.fvGap.mean, r.fvGap.mean)}, |pModel-mid| ratio ${ratio(t.pGap.mean, r.pGap.mean)}, take edge >=2c ${sh(t.edge.ge2, r.edge.ge2)}, >=4c ${sh(t.edge.ge4, r.edge.ge4)}, >=6c ${sh(t.edge.ge6, r.edge.ge6)}, |fv-mid| >=5c ${sh(t.fvGap.ge5, r.fvGap.ge5)}, sigma ratio ${ratio(t.sigma, r.sigma)}, mid p50 ${t.mid.p50.toFixed(0)}c vs ${r.mid.p50.toFixed(0)}c`;
}

export interface FeatureGap { name: string; z: number; real: number; twin: number }
/** The features with the largest |z| = (twin mean - real mean) / real within-asset sd (at most `top`; a feature needs MIN_Z_N finite values on each side and a real sd above zero). Ties by name. */
export function featureGaps(real: ProbeAgg | undefined, twin: ProbeAgg | undefined, top = TOP_FEATURES): FeatureGap[] {
  if (!real || !twin) return [];
  const out: FeatureGap[] = [];
  for (const name of Object.keys(real.fx)) {
    const r = real.fx[name], t = twin.fx[name], sd = statSd(r);
    if (!t || r.n < MIN_Z_N || t.n < MIN_Z_N || !(sd > 1e-12)) continue;
    out.push({ name, z: (t.mean - r.mean) / sd, real: r.mean, twin: t.mean });
  }
  return out.sort((a, b) => Math.abs(b.z) - Math.abs(a.z) || (a.name < b.name ? -1 : 1)).slice(0, top);
}
/** The feature lines of one twin source and asset: `feature NAME z=+1.23 (real m, twin m)`, FEATURES_PER_LINE to a line. */
export function featureLines(twin: string, asset: string, gaps: readonly FeatureGap[]): string[] {
  if (!gaps.length) return [`[twin] probe ${twin} vs real ${asset} features: none with enough values on both sides`];
  const out: string[] = [], per = FEATURES_PER_LINE, parts = Math.ceil(gaps.length / per);
  for (let i = 0; i < gaps.length; i += per) out.push(`[twin] probe ${twin} vs real ${asset} features ${i / per + 1}/${parts}: ${gaps.slice(i, i + per).map((g) => `feature ${g.name} z=${zfmt(g.z)} (real ${num3(g.real)}, twin ${num3(g.twin)})`).join('; ')}`);
  return out;
}

/** Sum of the aggregates of one source and asset over `days` (date order). */
function pooled(files: readonly ProbeFile[], src: string, key: string, days: readonly string[]): ProbeAgg | undefined {
  let acc: ProbeAgg | undefined;
  for (const d of days) { const f = files.find((x) => x.src === src && x.day === d); if (f) acc = acc ? mergeAgg(acc, f.assets[key]) : mergeAgg(newAgg(), f.assets[key]); }
  return acc;
}

/** Every line of the report, from the files alone (a live run and a later `--stage probe-report` print the same lines). Pooled over the days every present
 *  source has; per day (at most MAX_DAY_LINES days) the twin-against-real lines; the closing line says which asset has the largest take-edge share gap.
 *  `requested`: the days the dispatch asked for (probe-days.json), in date order. Day k is the k-th requested day; a requested day with no file in any source is
 *  said (`no probe file in any source`) and keeps its number. Without it, day k is the k-th day that has a file (an older folder, or a stage run by hand). */
export function probeReportLines(files: readonly ProbeFile[], requested?: readonly string[]): string[] {
  const out: string[] = [];
  const srcs = PROBE_SOURCES.filter((s) => files.some((f) => f.src === s));
  // the days are the requested ones when the request is known (probe-days.json: a day with no file at all keeps its number), else the days that have a file
  const days = [...new Set([...(requested ?? []), ...files.map((f) => f.day)])].sort();
  if (!files.length) return ['[twin] probe report: no probe files (a run made before round R3b has none)'];
  const have = (s: string, d: string) => files.find((f) => f.src === s && f.day === d);
  const common = days.filter((d) => srcs.every((s) => have(s, d)));
  const f0 = files[0], vol = [...new Set(files.map((f) => f.volModel))].sort().join('/');
  out.push(`[twin] probe: ${days.length} day(s) (day 1 to ${days.length} in date order), sources ${srcs.join(' ')}, ${f0.step} s step, entry window ${f0.window[0]} to ${f0.window[1]} s before close, ${f0.features.length} model input feature(s); the report pools the ${common.length} day(s) every source has`);
  out.push(`[twin] probe pricing: the dataset builder's own fair value (the backtest's flat vol fallback multiplier and Student-t nu are not applied, so sigmaPricing/sigma is 1 unless a validated vol model is on), vol model ${vol}; pModel is the decision model's price without the TA tilt or rule shifts`);
  out.push('[twin] probe reading: take edge = max(pModel - ask, bid - pModel); quantiles are the lower edge of a bin (mid 1c, spread 0.5c, gaps 0.25c); feature z = (twin mean - real mean) / real within-asset sd; rows are the 15 s samples of 15-minute Up/Down contracts inside the entry window');
  for (const d of days) {
    const cold = srcs.filter((s) => have(s, d) && !have(s, d)!.warm);
    if (cold.length) out.push(`[twin] probe day ${days.indexOf(d) + 1}: no warm-up day read for ${cold.join(' ')} (the first rows of the day start cold)`);
    const miss = srcs.filter((s) => !have(s, d));
    if (miss.length === srcs.length) out.push(`[twin] probe day ${days.indexOf(d) + 1}: no probe file in any source (its passes did not finish, or its requote day is missing); the day is left out of every line below and the day numbers stay the requested ones`);
    else if (miss.length) out.push(`[twin] probe day ${days.indexOf(d) + 1}: no file for ${miss.join(' ')} (the day is left out of the pooled lines)`);
  }
  const realFiles = days.map((d) => ({ d, f: have('real', d) })).filter((x) => x.f?.contracts);
  for (const { d, f } of realFiles) out.push(`[twin] probe real day ${days.indexOf(d) + 1}: contracts kept ${f!.contracts!.kept}, dropped ${f!.contracts!.dropped} (a real contract the requote day's contract list does not hold is left out, so real and twin cover the same contracts)`);
  if (!common.length) { out.push(`[twin] probe: no day is present in every source (${srcs.map((s) => `${s} ${days.filter((d) => have(s, d)).length}`).join(', ')}): nothing to pool`); return out; }
  // pooled, per source
  const pool = (s: string, k: string, ds: readonly string[] = common) => pooled(files, s, k, ds);
  for (const s of srcs) for (const k of PROBE_KEYS) out.push(...sourceLines(s, k, summarize(pool(s, k))));
  // pooled, a twin source against real
  const twins = srcs.filter((s) => s !== 'real');
  if (srcs.includes('real')) {
    for (const t of twins) for (const k of PROBE_KEYS) out.push(versusLine(t, k, summarize(pool(t, k)), summarize(pool('real', k))));
    for (const t of twins) for (const a of PROBE_ASSETS) out.push(...featureLines(t, a, featureGaps(pool('real', a), pool(t, a))));
    if (common.length <= MAX_DAY_LINES) {
      for (const d of common) for (const t of twins) for (const k of PROBE_KEYS) out.push(versusLine(t, k, summarize(pool(t, k, [d])), summarize(pool('real', k, [d])), ` day ${days.indexOf(d) + 1}`));
    } else out.push(`[twin] probe: ${common.length} days, so the per-day lines are left out (the pooled lines above hold them)`);
    // the closing line: the asset with the largest take-edge (>=4c) share gap, per twin source
    const gaps: string[] = [];
    for (const t of twins) {
      let best: { a: string; gap: number; tw: number; re: number } | undefined;
      for (const a of PROBE_ASSETS) {
        const ts = summarize(pool(t, a)), rs = summarize(pool('real', a));
        if (!ts || !rs) continue;
        const gap = ts.edge.ge4 - rs.edge.ge4;
        if (!best || Math.abs(gap) > Math.abs(best.gap)) best = { a, gap, tw: ts.edge.ge4, re: rs.edge.ge4 };
      }
      if (best) gaps.push(`${t} ${best.a} ${sg1(best.gap * 100)} points (twin ${pct(best.tw)} vs real ${pct(best.re)})`);
    }
    out.push(gaps.length ? `[twin] probe summary: the largest take-edge (>=4c) share gap against real is ${gaps.join('; ')}` : '[twin] probe summary: no asset has rows in both a twin source and real, so there is no gap to name');
  } else out.push('[twin] probe summary: no real source among the files, so no gap against real');
  return out;
}
