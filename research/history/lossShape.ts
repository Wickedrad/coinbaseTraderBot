// Round J1: the amended realism check 3, "does the twin's traded-window P&L have the real days' SHAPE?"
//
// Why it exists (rounds/P2b.md, the written reason BRIEF.md asks for a judge change; Steven's card of 2026-11-23 22:02 UTC / 5:02 PM EST):
// check 3 as pre-registered (per-window rmse <= 1.5x the placebo's) cannot be passed by any statistical simulator, because the real days'
// per-window P&L is dominated by a couple of stop-outs that no twin can place in the same windows. This check compares the DISTRIBUTION of the
// twin's traded-window P&L with the real days' instead, in two parts, each tested against the real days' own sampling noise:
//   1. stop-out frequency: how many traded windows lost more than STOP_LINE dollars, an exact two-sided Fisher test on the 2x2 table;
//   2. body distribution: the P&L of every OTHER traded window, an energy (Cramer) distance with a seeded permutation p-value.
// It is a TRIPWIRE, not a certificate: with a few dozen real windows and two or so stop-outs it sees winners 15 to 25% off, a body spread
// wrong by 2x (weakly) and stop-out counts several times real's; it cannot see a twin with fewer or no stop-outs, the SIZE of a stop-out,
// one huge loss, the total P&L, or WHICH windows traded. A pass is never evidence about the loss tail (RUNBOOK 3.9, 8).
//
// A port of the design panel's reference implementation (frozen 2026-11-23T23:37:58Z before it was run on any real window), plus ONE
// change the director made to its degenerate rules (below, "kR = 0"). Pure: no I/O, no clock, no Math.random, no module state. The
// generator is the judge's own LCG (the one outcome() in historyTwin.ts uses), created fresh in every call, so a call's answer depends on its
// two lists and nothing else.
//
// Inputs: dollars (fees in) of each side's OWN traded windows (contracts > 0 on that side), as `tradedPnl` in historyTwin.ts reads them
// from the windows-*.json maps. NOT the union-padded arrays outcome() builds for check 2.

/** A traded window with P&L strictly below this many dollars is a "stop-out". Equal to POSITION_LOSER_CENTS / 100 in historyTwin.ts (a test holds the two together; restated here so this module imports nothing). */
export const STOP_LINE = -5;
/** Level of the stop-out frequency test (the two levels together: family-wise at most about 0.10). */
export const ALPHA_STOP = 0.05;
/** Level of the body distribution test. */
export const ALPHA_BODY = 0.05;
/** Permutations of the body test. */
export const PERMS = 9999;
/** The LCG's seed (check 2's bootstrap uses 1). */
export const SEED = 3;

/** The check's answer. Every field is deterministic. A number is null when the step that makes it did not run (see the degenerate rules in `lossShapeCheck`). */
export interface LossShape {
  pass: boolean;
  /** False when the inputs do not allow the test (the rules in `lossShapeCheck`); then `pass` is false and `reason` says why. */
  evaluable: boolean;
  reason: string;
  /** Stop-out windows (P&L below STOP_LINE) and traded windows, real then twin. */
  kR: number; nR: number; kT: number; nT: number;
  /** Two-sided exact Fisher p of the stop-out counts; the permutation p of the body distribution. */
  pStop: number | null; pBody: number | null;
  /** The observed energy distance of the two bodies (dollars: the integral of the squared gap between the two CDFs) and the 95th percentile of its permutation draws. */
  energy: number | null; crit95: number | null;
  /** Mean P&L of the non-stop-out windows of each side, and the worst window (the minimum P&L, stop-outs included) of each side. */
  bodyMeanR: number | null; bodyMeanT: number | null; worstR: number | null; worstT: number | null;
  /** Real had no stop-out window (the tests still run: a twin with none gets pStop 1, a twin with several fails). */
  realHadNoStopOut: boolean;
  /** The twin had none (while real may have some: nothing can reject that at this sample size). */
  twinHadNoStopOut: boolean;
}

const EPS = 1e-9;

/** Two-sided exact Fisher p for the 2x2 table [[kR, nR-kR], [kT, nT-kT]], the minimum-likelihood way: the sum of the hypergeometric
 *  probabilities of every table with the same margins that is no more likely than the observed one (a 1e-9 relative slack on ties). */
export function fisherTwoSided(kR: number, nR: number, kT: number, nT: number): number {
  const K = kR + kT, N = nR + nT;
  const lf = new Float64Array(N + 1); for (let i = 1; i <= N; i++) lf[i] = lf[i - 1] + Math.log(i);
  const lc = (n: number, k: number) => lf[n] - lf[k] - lf[n - k];
  const lo = Math.max(0, K - nR), hi = Math.min(K, nT);
  const pm = (a: number) => Math.exp(lc(nT, a) + lc(nR, K - a) - lc(N, K));
  const p0 = pm(kT); let p = 0;
  for (let a = lo; a <= hi; a++) { const q = pm(a); if (q <= p0 * (1 + EPS)) p += q; }
  return Math.min(1, p);
}

/** The energy (Cramer) distance of two samples, the integral over dollars of (F_x - F_y)^2, with a permutation p-value: the labels of the
 *  pooled, sorted values are shuffled `perms` times (Fisher-Yates, ONE generator stream, the judge's LCG) and the p-value counts the draws
 *  at least as large as the observed statistic (ties count against the twin). `crit95` is the 95th percentile of the draws. */
export function energyPerm(x: readonly number[], y: readonly number[], perms = PERMS, seed = SEED): { p: number; energy: number; crit95: number } {
  const n = x.length, m = y.length, N = n + m;
  const pooled = [...x.map((v) => [v, 1] as const), ...y.map((v) => [v, 0] as const)].sort((a, b) => a[0] - b[0]);
  const gap = new Float64Array(N), lab = new Uint8Array(N);
  for (let i = 0; i < N; i++) { lab[i] = pooled[i][1]; if (i < N - 1) gap[i] = pooled[i + 1][0] - pooled[i][0]; }
  const T = (): number => { let c = 0, e = 0; for (let k = 0; k < N - 1; k++) { c += lab[k] ? 1 / n : -1 / m; e += gap[k] * c * c; } return e; };
  const obs = T();                                                   // the observed labels, before any shuffle
  let s = seed >>> 0 || 1; const rnd = () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
  const draws = new Float64Array(perms); let ge = 0;
  for (let b = 0; b < perms; b++) {
    for (let i = N - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)), t = lab[i]; lab[i] = lab[j]; lab[j] = t; }
    draws[b] = T(); if (draws[b] >= obs * (1 - EPS)) ge++;           // ties count against the twin
  }
  const sorted = Array.from(draws).sort((a, b) => a - b);
  return { p: (1 + ge) / (perms + 1), energy: obs, crit95: sorted[Math.min(perms - 1, Math.floor(0.95 * perms))] };
}

/** A copy of a list when it is an array of finite numbers (every index, holes included), else null. Reads each element once, never throws. */
function finiteList(a: unknown): number[] | null {
  try {
    if (!Array.isArray(a)) return null;
    const out: number[] = [];
    for (let i = 0; i < a.length; i++) { const v: unknown = a[i]; if (typeof v !== 'number' || !Number.isFinite(v)) return null; out.push(v); }
    return out;
  } catch { return null; }
}

const meanOf = (a: readonly number[]): number | null => (a.length ? a.reduce((s, v) => s + v, 0) / a.length : null);
const minOf = (a: readonly number[]): number | null => (a.length ? a.reduce((m, v) => Math.min(m, v), Infinity) : null);

/** A result that says nothing could be judged, for a reason (the degenerate rules; also what the verdict builds for a source whose per-window file is missing). Never passes. */
export function notEvaluable(reason: string, extra: Partial<LossShape> = {}): LossShape {
  return {
    pass: false, evaluable: false, reason, kR: 0, nR: 0, kT: 0, nT: 0, pStop: null, pBody: null, energy: null, crit95: null,
    bodyMeanR: null, bodyMeanT: null, worstR: null, worstT: null, realHadNoStopOut: false, twinHadNoStopOut: false, ...extra,
  };
}

/** The amended check 3. `realPnl` and `twinPnl` are the P&L in dollars (fees in) of each side's own traded windows.
 *
 *  Split: a stop-out is a window with P&L < STOP_LINE (strict); the body is every other window (zeros and small losses included).
 *  Test 1 (stop-out frequency): Fisher, exact two-sided; fails when p <= ALPHA_STOP.
 *  Test 2 (body distribution): energy distance, PERMS permutations; fails when p <= ALPHA_BODY.
 *  pass = evaluable and neither fails.
 *
 *  Degenerate inputs, in this order, never throw and never pass (evaluable false, a reason):
 *   1. an input that is not an array, or a value that is not a finite number        -> 'a window P&L is not a finite number'
 *   2. the twin traded 0 windows                                                    -> 'twin traded 0 windows'
 *   3. real traded 0 windows                                                        -> 'real traded 0 windows'
 *   4. either body has fewer than 2 windows                                         -> 'not evaluable: fewer than 2 non-stop-out windows'
 *  NOT a degenerate case (the director's addition to the design panel's rule, which returned "not evaluable" when real has no stop-out):
 *  real with NO stop-out runs both tests and sets `realHadNoStopOut`. The exact test is valid with a zero cell: a twin with none gets
 *  pStop 1, a twin with several fails. Without this, about 12% of fresh 37-window real samples would make the one blind CONFIRM look
 *  un-passable by chance. It touches an input class the DEV days do not contain. A twin with NO stop-out while real has some PASSES the
 *  stop-out test: at this sample size nothing can reject it (the verdict's caveat line says so). */
export function lossShapeCheck(realPnl: readonly number[], twinPnl: readonly number[]): LossShape {
  const real = finiteList(realPnl), twin = finiteList(twinPnl);
  const lenOf = (a: unknown): number => { try { return Array.isArray(a) ? a.length : 0; } catch { return 0; } };
  if (!real || !twin) return notEvaluable('a window P&L is not a finite number', { nR: lenOf(realPnl), nT: lenOf(twinPnl) });
  const rStop = real.filter((v) => v < STOP_LINE), tStop = twin.filter((v) => v < STOP_LINE);
  const rBody = real.filter((v) => v >= STOP_LINE), tBody = twin.filter((v) => v >= STOP_LINE);
  const info: Partial<LossShape> = {
    nR: real.length, nT: twin.length, kR: rStop.length, kT: tStop.length,
    worstR: minOf(real), worstT: minOf(twin), bodyMeanR: meanOf(rBody), bodyMeanT: meanOf(tBody),
  };
  if (twin.length === 0) return notEvaluable('twin traded 0 windows', info);
  if (real.length === 0) return notEvaluable('real traded 0 windows', info);
  const noStop = { realHadNoStopOut: rStop.length === 0, twinHadNoStopOut: tStop.length === 0 };
  if (rBody.length < 2 || tBody.length < 2) return notEvaluable('not evaluable: fewer than 2 non-stop-out windows', { ...info, ...noStop });
  const pStop = fisherTwoSided(rStop.length, real.length, tStop.length, twin.length);
  const e = energyPerm(rBody, tBody);
  const failed = [pStop <= ALPHA_STOP ? 'stop-out frequency' : '', e.p <= ALPHA_BODY ? 'body distribution' : ''].filter(Boolean);
  return {
    ...notEvaluable('', info), ...noStop, evaluable: true, pass: failed.length === 0,
    reason: failed.length ? failed.map((f) => `differs from real: ${f}`).join('; ') : 'ok',
    pStop, pBody: e.p, energy: e.energy, crit95: e.crit95,
  };
}
