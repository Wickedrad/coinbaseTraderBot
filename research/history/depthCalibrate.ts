// Per-asset LEVEL calibration of the depth fill-in, fitted on the FIT days (Nov 22, round R2; the model file's `calibration` block, schema 3).
//
// Why. The judge's adversary is a linear logistic over 13 per-contract-life features, so it reads per-asset MEAN gaps. After R1 the asset
// scales were right but the twin still sat below the real days, per asset, in the size of the book (depth10, the best level), the size of a
// trade and the rates of quote changes and trades (rounds/R1.md). This closes those first moments, on the days the depth model was fitted
// on and on no other: nothing here sees a judged day, and no number in it is a tuned constant of a judged day.
//
// What it does (a damped fixed point, per asset, in the LOG of the quantity). For each asset, take the mean over its contract lives of five
// features, in the real FIT rows and in the twin's FIT rows (the fill-in played on the FIT days' requote days with the multipliers so far):
//   topSize, depth10, tradeSize   (the rows hold log1p of the size: the quantity is expm1 of the mean, a size in contracts),
//   quoteChangesPerMin, tradesPerMin   (raw rates: the quantity is the mean).
// With g = log(real quantity) - log(twin quantity) (positive: the twin is below the real days), each iteration sets
//   log mult += damping * g          tradesPerMin -> tradeRateMult, tradeSize -> tradeSizeMult, depth10 -> levelSizeMult,
//                                    quoteChangesPerMin -> flickMult, topSize -> topSizeMult
// where topSizeMult is the best level's size RELATIVE to the others: levelSizeMult scales every level (the best one too), so the best
// level's own multiplier takes only what is left of its gap after that step. The knobs act on each other's features (a bigger book is
// traded in bigger prints; more trades move the best price), so all five move together and the last iteration shows the residual.
// Each multiplier is clipped to [CALIBRATION_CLIP.lo, CALIBRATION_CLIP.hi]. An asset stops when its five standardized gaps (twin mean minus
// real mean, in the real within-asset sd of the feature, in the feature's own units) are all under `tolSd`; the loop stops after
// `maxIter` iterations. Assets do not interact in the simulator (a ticker's book depends on its own rows and its own seed), so each asset
// has its own iteration count and keeps the multipliers of its BEST evaluated iteration (the smallest largest-gap), never a worse last one.
//
// The damping (0.8), the iteration count (5), the stop (0.1 sd), the clip (0.2 to 5) and the fewest lives an asset needs (20) are SETTINGS OF
// THE ALGORITHM, written down here and tested, not numbers tuned on any day. quotedShare is reported, not calibrated (the twin never quotes
// before its first candle: structure, round R3).
//
// The real rows it is handed must be the judge's population: the real contracts the twin HAS on the same day (the stage restricts them with historyTwin.ts
// restrictFitRows, as the judged real rows are restricted to the requote day's tickers). Real contracts with no twin counterpart are typically quiet, thin-book ones;
// fitted to as well, they would pull the twin's means toward a population the judge never compares. The stage also stamps the code the multipliers are a fit of
// (`code`: simulator source hash, requote layer, feature code) into the block, so that a reuse under other code is refused.
//
// Pure: the twin's rows come from a function the caller passes (the workflow stage plays the fill-in in-stream), the clock is a function the
// caller passes, and there is no Date.now, no Math.random and no file access here. Same rows in, same multipliers out. Node built-ins are not
// even needed; the file imports only the simulator's own definitions, and it is NOT part of the Windows trainer's bundle (only depthSim.ts is).

import { assetOfTicker, CALIBRATION_CLIP, CALIBRATION_SCHEMA, clipMult, DEPTH_ASSETS, modelSchema, NEUTRAL_CALIBRATION, validateCalibration, type AssetCalibration, type CalibrationCode, type DepthCalibration, type DepthModel } from './depthSim';
import { DEPTH_MODEL_SCHEMA } from './depthModelVersion';

/** The damped step of the fixed point (an algorithm setting, not a tuned number). */
export const CAL_DAMPING = 0.8;
/** Most iterations (each is one pass of the fill-in over the FIT days). */
export const CAL_MAX_ITER = 5;
/** An asset has converged when each of its five gaps is under this many real within-asset sd. */
export const CAL_TOL_SD = 0.1;
/** Fewest real and twin lives an asset needs to be calibrated (the sweep's own MIN_SWEEP_LIVES): fewer, and its means are noise. */
export const CAL_MIN_LIVES = 20;
/** The held-in check's time budget in seconds (RUNBOOK: skipped when it would take longer). */
export const CAL_HELD_IN_BUDGET_S = 180;

/** The calibrated features, the knob each one drives, and whether its row value is log1p of the quantity. */
export const CAL_TARGETS = [
  { name: 'top', feature: 'topSize', knob: 'topSizeMult', log1p: true },
  { name: 'depth10', feature: 'depth10', knob: 'levelSizeMult', log1p: true },
  { name: 'tradeSize', feature: 'tradeSize', knob: 'tradeSizeMult', log1p: true },
  { name: 'qchg', feature: 'quoteChangesPerMin', knob: 'flickMult', log1p: false },
  { name: 'trades', feature: 'tradesPerMin', knob: 'tradeRateMult', log1p: false },
] as const;
type TargetName = (typeof CAL_TARGETS)[number]['name'];

/** A contract life's row as the calibration reads it: its ticker (the asset), its day (for the held-in check), the feature values. */
export interface CalRow { ticker: string; day?: string; f: readonly number[] }
/** Where each feature sits in a row's `f` (the caller's FEATURES order); `quotedShare` is reported only. */
export interface CalCols { top: number; depth10: number; tradeSize: number; qchg: number; trades: number; quotedShare?: number }

const finite = (x: number) => Number.isFinite(x);
const mean = (xs: readonly number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN);
/** The population sd of the finite values (the judge's own fitLogit scale); 0 when there are under two. */
function sdOf(xs: readonly number[]): number { const m = mean(xs); return xs.length > 1 ? Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / xs.length) : 0; }
const col = (rows: readonly CalRow[], j: number) => rows.map((r) => r.f[j]).filter(finite);
const r2 = (x: number) => (Number.isFinite(x) ? String(+x.toFixed(2)) : 'na');
const r4 = (x: number) => +x.toFixed(4);

/** One asset's gaps between a twin and a real set of rows: twin mean minus real mean in the REAL within-asset sd (`sd`: from the real rows
 *  unless given, to hold a scale fixed across calls), per feature in `cols`; NaN where either side has no finite value. A feature with
 *  no spread in the real rows is read in units of 1. */
export interface AssetGaps { real: number; twin: number; gaps: Record<string, number> }
export function gapsOfAsset(real: readonly CalRow[], twin: readonly CalRow[], cols: Readonly<Record<string, number>>, sd?: Readonly<Record<string, number>>): AssetGaps {
  const gaps: Record<string, number> = {};
  for (const [name, j] of Object.entries(cols)) {
    const a = col(real, j), b = col(twin, j);
    const s = sd?.[name] ?? sdOf(a);
    gaps[name] = a.length && b.length ? (mean(b) - mean(a)) / (s > 1e-12 ? s : 1) : NaN;
  }
  return { real: real.length, twin: twin.length, gaps };
}
/** The within-asset sd of each feature over the real rows. */
export const sdsOf = (real: readonly CalRow[], cols: Readonly<Record<string, number>>): Record<string, number> => Object.fromEntries(Object.entries(cols).map(([n, j]) => [n, sdOf(col(real, j))]));
/** The asset of a row's ticker among DEPTH_ASSETS (the four series the twin replays); undefined for any other. */
export const rowAsset = (r: { ticker: string }): string | undefined => assetOfTicker(r.ticker, DEPTH_ASSETS);

/** Per asset (DEPTH_ASSETS order), the gaps of the twin rows against the real rows (REPORT-ONLY helper the verdict uses on the judged days). */
export function gapsByAsset(real: readonly CalRow[], twin: readonly CalRow[], cols: Readonly<Record<string, number>>): Record<string, AssetGaps> {
  const out: Record<string, AssetGaps> = {};
  for (const a of DEPTH_ASSETS) {
    const rr = real.filter((r) => rowAsset(r) === a), tt = twin.filter((r) => rowAsset(r) === a);
    if (rr.length || tt.length) out[a] = gapsOfAsset(rr, tt, cols);
  }
  return out;
}

const colsOf = (c: CalCols): Record<string, number> => ({ top: c.top, depth10: c.depth10, tradeSize: c.tradeSize, qchg: c.qchg, trades: c.trades, ...(c.quotedShare !== undefined ? { quotedShare: c.quotedShare } : {}) });
/** The quantity of a target in a set of rows, in its own units (a size in contracts for the log1p features, a rate for the others). */
function quantity(rows: readonly CalRow[], j: number, log1p: boolean): number { const m = mean(col(rows, j)); return log1p ? Math.expm1(m) : m; }
/** log(real / twin) of a quantity, 0 when the real one says nothing, and the largest move the clip allows when the twin has none. */
function logGap(real: number, twin: number): number {
  if (!(real > 0) || !finite(real)) return 0;
  if (!(twin > 0) || !finite(twin)) return Math.log(CALIBRATION_CLIP.hi);
  return Math.log(real / twin);
}

const multText = (m: AssetCalibration) => `top ${r2(m.topSizeMult)} level ${r2(m.levelSizeMult)} size ${r2(m.tradeSizeMult)} trades ${r2(m.tradeRateMult)} flick ${r2(m.flickMult)}`;
const gapText = (g: Record<string, number>) => `top ${r2(g.top)} depth10 ${r2(g.depth10)} tradeSize ${r2(g.tradeSize)} qchg ${r2(g.qchg)} trades ${r2(g.trades)}`;
const worst = (g: Record<string, number>) => Math.max(0, ...CAL_TARGETS.map((t) => Math.abs(g[t.name])).filter(finite));
/** NaN gaps are as bad as they come (the asset could not be measured): they never read as converged. */
const maxGap = (g: Record<string, number>) => (CAL_TARGETS.some((t) => !finite(g[t.name])) ? Infinity : worst(g));

/** One damped step: the multipliers after one iteration given the log gaps measured at `m` (see the header). Pure; exported for tests. */
export function stepMults(m: AssetCalibration, logGaps: Record<TargetName, number>, damping = CAL_DAMPING): AssetCalibration {
  const mv = (x: number, d: number) => r4(clipMult(x * Math.exp(d)));
  const level = mv(m.levelSizeMult, damping * logGaps.depth10), applied = Math.log(level / m.levelSizeMult);
  return {
    levelSizeMult: level,
    // the best level's own multiplier takes what the level step left of its gap
    topSizeMult: mv(m.topSizeMult, damping * logGaps.top - applied),
    tradeSizeMult: mv(m.tradeSizeMult, damping * logGaps.tradeSize),
    tradeRateMult: mv(m.tradeRateMult, damping * logGaps.trades),
    flickMult: mv(m.flickMult, damping * logGaps.qchg),
  };
}

/** What a twin pass is asked: the model to play (with the multipliers of this iteration in its `calibration`) and the FIT days to play it on. */
export type TwinRows = (model: DepthModel, days: readonly string[]) => Promise<CalRow[]> | CalRow[];

export interface CalibrateInput {
  /** The fitted model (its own calibration, if any, is replaced). */
  model: DepthModel;
  /** The days the model was fitted on, and the real rows of those days. */
  fitDays: readonly string[];
  realRows: readonly CalRow[];
  twinRows: TwinRows;
  cols: CalCols;
  maxIter?: number; damping?: number; tolSd?: number; minLives?: number;
  /** The code the multipliers are a fit of (the stage passes the simulator's hash, REPLAY_VERSION and FEATURE_CODE_VERSION): stamped into the block, checked by a reuse. */
  code?: CalibrationCode;
  /** One printed line at a time. */
  log?: (line: string) => void;
  /** Seconds, monotonic (the stage passes process.hrtime; tests pass a fake). Only used to price the held-in check. */
  now?: () => number;
  /** The held-in check's budget in seconds; 0 skips it. */
  heldInBudgetS?: number;
}

export interface AssetTrace { iter: number; asset: string; gaps: Record<string, number>; mults: AssetCalibration; lives: { real: number; twin: number } }
export interface CalibrateResult {
  /** The model with its calibration block (schema DEPTH_MODEL_SCHEMA). */
  model: DepthModel;
  calibration: DepthCalibration;
  trace: AssetTrace[];
  /** Assets left out and why (fewer lives than the minimum on either side). */
  skipped: Record<string, string>;
  converged: boolean;
  iterations: number;
  /** The residual gaps per asset at the multipliers kept (the five calibrated features and quotedShare when the columns name it). */
  residual: Record<string, Record<string, number>>;
  /** The twin rows of the first, neutral iteration (what the held-in check starts from) and the seconds a day's pass took. */
  neutralTwin: CalRow[];
  secPerDayPass: number;
}

/** The model as an iteration plays it: the calibration block of these multipliers over the model's own tables. */
export function withCalibration(model: DepthModel, fitDays: readonly string[], iterations: number, byAsset: Record<string, AssetCalibration>, residual?: Record<string, Record<string, number>>, code?: CalibrationCode): DepthModel {
  const calibration: DepthCalibration = { schema: CALIBRATION_SCHEMA, fitDays: [...fitDays], iterations, byAsset: Object.fromEntries(Object.entries(byAsset).map(([a, m]) => [a, { ...m }])), ...(residual ? { residual } : {}), ...(code ? { code: { ...code } } : {}) };
  validateCalibration(calibration);
  return { ...model, schema: Math.max(modelSchema(model), DEPTH_MODEL_SCHEMA), calibration };
}

interface LoopOut { kept: Record<string, AssetCalibration>; next: Record<string, AssetCalibration>; trace: AssetTrace[]; skipped: Record<string, string>; iterations: number; converged: boolean; residual: Record<string, Record<string, number>>; first: CalRow[]; passSeconds: number; passes: number }

/** The fixed point over `days`. `updateLast`: also take the step after the last iteration (the held-in check, which then plays the NEXT multipliers
 *  on a day it did not read); the main fit keeps the best evaluated iteration instead. `first`: the neutral twin rows of these days, when known. */
async function runLoop(i: CalibrateInput, days: readonly string[], real: readonly CalRow[], o: { maxIter: number; updateLast: boolean; first?: CalRow[]; label: string; quiet?: boolean }): Promise<LoopOut> {
  const damping = i.damping ?? CAL_DAMPING, tol = i.tolSd ?? CAL_TOL_SD, minLives = i.minLives ?? CAL_MIN_LIVES, now = i.now ?? (() => 0);
  const say = i.log ?? (() => undefined), cols = colsOf(i.cols);
  const realBy: Record<string, CalRow[]> = {}, sd: Record<string, Record<string, number>> = {};
  for (const a of DEPTH_ASSETS) { realBy[a] = real.filter((r) => rowAsset(r) === a); sd[a] = sdsOf(realBy[a], cols); }
  const skipped: Record<string, string> = {}, active: string[] = [];
  for (const a of DEPTH_ASSETS) { if (realBy[a].length >= minLives) active.push(a); else if (realBy[a].length) skipped[a] = `${realBy[a].length} real lives (at least ${minLives} needed)`; }
  const mults: Record<string, AssetCalibration> = Object.fromEntries(active.map((a) => [a, { ...NEUTRAL_CALIBRATION }]));
  const kept: Record<string, AssetCalibration> = {}, keptGap: Record<string, number> = {}, residual: Record<string, Record<string, number>> = {};
  const done = new Set<string>(), trace: AssetTrace[] = [];
  let first: CalRow[] = [], iterations = 0, passSeconds = 0, passes = 0;
  for (let iter = 1; iter <= o.maxIter; iter++) {
    const live = active.filter((a) => !done.has(a) && !skipped[a]);
    if (!live.length) break;
    // every asset still moving is played in one pass (the assets do not interact: each ticker's book is its own)
    const model = withCalibration(i.model, days, iter - 1, Object.fromEntries(active.map((a) => [a, mults[a]])));
    let twin: CalRow[];
    if (iter === 1 && o.first) twin = [...o.first];
    else { const t0 = now(); twin = await i.twinRows(model, days); passSeconds += Math.max(0, now() - t0); passes += days.length; }
    if (iter === 1) first = twin;
    iterations = iter;
    const step: Record<string, AssetCalibration> = {};
    for (const a of live) {
      const tt = twin.filter((r) => rowAsset(r) === a);
      if (iter === 1 && tt.length < minLives) { skipped[a] = `${tt.length} twin lives (at least ${minLives} needed)`; continue; }
      const g = gapsOfAsset(realBy[a], tt, cols, sd[a]);
      const m = mults[a], mg = maxGap(g.gaps);
      trace.push({ iter, asset: a, gaps: g.gaps, mults: { ...m }, lives: { real: g.real, twin: g.twin } });
      if (!o.quiet) say(`[twin] calibration: ${o.label}asset ${a} iter ${iter}: gaps (sd) ${gapText(g.gaps)}; mults ${multText(m)}`);
      if (keptGap[a] === undefined || mg < keptGap[a]) { keptGap[a] = mg; kept[a] = { ...m }; residual[a] = { ...g.gaps }; }
      if (mg < tol) { done.add(a); continue; }
      if (iter < o.maxIter || o.updateLast) {
        const lg = Object.fromEntries(CAL_TARGETS.map((t) => [t.name, logGap(quantity(realBy[a], i.cols[t.name], t.log1p), quantity(tt, i.cols[t.name], t.log1p))])) as Record<TargetName, number>;
        step[a] = stepMults(m, lg, damping);
      }
    }
    for (const a of Object.keys(step)) mults[a] = step[a];
  }
  const next: Record<string, AssetCalibration> = {};
  for (const a of active) if (!skipped[a]) next[a] = { ...mults[a] };
  for (const a of Object.keys(kept)) if (skipped[a]) { delete kept[a]; delete residual[a]; }
  // a quotedShare gap is reported at the kept multipliers (it is not calibrated, so it is a read of the same twin rows: the last pass's)
  return { kept, next, trace, skipped, iterations, converged: active.filter((a) => !skipped[a]).every((a) => done.has(a)) && active.some((a) => !skipped[a]), residual, first, passSeconds, passes };
}

/** The calibration of a fitted model on its FIT days (see the header). Prints one line per iteration and asset, then the residual per asset. */
export async function calibrateDepthModel(i: CalibrateInput): Promise<CalibrateResult> {
  const maxIter = i.maxIter ?? CAL_MAX_ITER, say = i.log ?? (() => undefined);
  if (!(Number.isInteger(maxIter) && maxIter >= 1 && maxIter <= 20)) throw new Error(`calibration: maxIter must be a whole number from 1 to 20, got ${String(maxIter)}`);
  if (!i.fitDays.length) throw new Error('calibration: no fit days');
  // It reads only the days the model was fitted on (the workflow stage holds those against the split, assertCalibrationDays; this holds the rows against the days).
  const modelDays = i.model.days ?? [], notFitted = i.fitDays.filter((d) => !modelDays.includes(d));
  if (notFitted.length) throw new Error(`calibration reads only the days the depth model was fitted on (${modelDays.join(', ') || 'none recorded'}): ${notFitted.join(', ')} ${notFitted.length > 1 ? 'are' : 'is'} not among them`);
  const strayRows = [...new Set(i.realRows.map((r) => r.day ?? '').filter((d) => !i.fitDays.includes(d)))];
  if (strayRows.length) throw new Error(`calibration: the real rows hold day(s) that are not fit days: ${strayRows.map((d) => d || '(no day)').join(', ')}`);
  const out = await runLoop(i, i.fitDays, i.realRows, { maxIter, updateLast: false, label: '' });
  const assets = Object.keys(out.kept);
  if (!assets.length) throw new Error(`calibration: no asset has the lives to calibrate (${Object.entries(out.skipped).map(([a, why]) => `${a}: ${why}`).join('; ') || 'no real rows of BTC, ETH, SOL or XRP'})`);
  const byAsset: Record<string, AssetCalibration> = Object.fromEntries(assets.map((a) => [a, out.kept[a]]));
  const model = withCalibration(i.model, i.fitDays, out.iterations, byAsset, out.residual, i.code);
  for (const a of assets) {
    const at = out.trace.filter((t) => t.asset === a), best = at.find((t) => JSON.stringify(t.mults) === JSON.stringify(out.kept[a])) ?? at[at.length - 1];
    const qs = out.residual[a].quotedShare;
    say(`[twin] calibration: asset ${a} final (best of ${at.length} iteration(s): iteration ${best.iter}): residual gaps (sd) ${gapText(out.residual[a])}${qs !== undefined ? `; quotedShare ${r2(qs)} (not calibrated)` : ''}; mults ${multText(out.kept[a])}; lives real ${best.lives.real} twin ${best.lives.twin}`);
  }
  for (const [a, why] of Object.entries(out.skipped)) say(`[twin] calibration: asset ${a} not calibrated (${why}); it plays as measured`);
  const w = assets.map((a) => ({ a, g: maxGap(out.residual[a]) })).sort((x, y) => y.g - x.g)[0];
  say(`[twin] calibration: fitted on the FIT days ${i.fitDays.join(' ')}: ${assets.length} asset(s), ${out.iterations} iteration(s) of at most ${maxIter} (damping ${i.damping ?? CAL_DAMPING}, clip ${CALIBRATION_CLIP.lo}..${CALIBRATION_CLIP.hi}, stop under ${i.tolSd ?? CAL_TOL_SD} sd: algorithm settings); largest residual gap ${r2(w.g)} sd (${w.a}); ${out.converged ? 'converged' : 'not converged'}`);
  return { model, calibration: model.calibration!, trace: out.trace, skipped: out.skipped, converged: out.converged, iterations: out.iterations, residual: out.residual, neutralTwin: out.first, secPerDayPass: out.passes ? out.passSeconds / out.passes : 0 };
}

export interface HeldInResult { ran: boolean; iterations: number; passes: number; folds: Array<{ day: string; byAsset: Record<string, { before: Record<string, number>; after: Record<string, number> }> }>; meanBefore: number; meanAfter: number; note?: string }
/** Passes of the fill-in over one FIT day the held-in check needs, with `k` iterations per fold over `n` fit days (the first, neutral iteration
 *  is read from the main fit's own pass). */
export const heldInPasses = (n: number, k: number): number => n * ((k - 1) * (n - 1) + 1);

/** The held-in (leave-one-fit-day-out) check: for each FIT day, fit the multipliers on the OTHER fit days (the same loop, `k` iterations and the
 *  step after the last) and print the six gaps on the day left out, next to the uncalibrated ones, in the within-asset sd of ALL the real FIT
 *  rows (one scale for every fold). It shows whether the first-moment shifts carry from days to a day; it reads FIT days only, and its
 *  numbers feed nothing. The largest k in {2, 1} whose passes fit `budgetS` at the measured seconds a pass takes is used; none fits: skipped. */
export async function heldInCheck(i: CalibrateInput, fit: CalibrateResult): Promise<HeldInResult> {
  const say = i.log ?? (() => undefined), budget = i.heldInBudgetS ?? CAL_HELD_IN_BUDGET_S, days = [...i.fitDays];
  const none = (note: string): HeldInResult => { say(`[twin] calibration: held-in check skipped: ${note}`); return { ran: false, iterations: 0, passes: 0, folds: [], meanBefore: NaN, meanAfter: NaN, note }; };
  if (days.length < 2) return none(`${days.length} fit day(s): leaving one out needs at least 2`);
  if (budget <= 0) return none('switched off');
  const sec = fit.secPerDayPass, pick = [2, 1].find((k) => heldInPasses(days.length, k) * sec <= budget);
  if (pick === undefined) return none(`about ${Math.round(heldInPasses(days.length, 1) * sec)} s for the cheapest version (${heldInPasses(days.length, 1)} day passes at ${r2(sec)} s) against a budget of ${budget} s`);
  const cols6 = colsOf(i.cols), fullSd: Record<string, Record<string, number>> = {};
  for (const a of DEPTH_ASSETS) fullSd[a] = sdsOf(i.realRows.filter((r) => rowAsset(r) === a), cols6);
  const dayOf = (r: CalRow) => r.day ?? '';
  const folds: HeldInResult['folds'] = [];
  let passes = 0, sumB = 0, sumA = 0, nGap = 0;
  for (const held of days) {
    const train = days.filter((d) => d !== held), realTrain = i.realRows.filter((r) => train.includes(dayOf(r))), realHeld = i.realRows.filter((r) => dayOf(r) === held);
    const out = await runLoop({ ...i, log: undefined }, train, realTrain, { maxIter: pick, updateLast: true, first: fit.neutralTwin.filter((r) => train.includes(dayOf(r))), label: '', quiet: true });
    passes += out.passes;
    const model = withCalibration(i.model, train, out.iterations, out.next);
    const twinHeld = await i.twinRows(model, [held]);
    passes += 1;
    const neutralHeld = fit.neutralTwin.filter((r) => dayOf(r) === held), byAsset: Record<string, { before: Record<string, number>; after: Record<string, number> }> = {};
    for (const a of Object.keys(out.next)) {
      const rr = realHeld.filter((r) => rowAsset(r) === a);
      if (!rr.length) continue;
      const before = gapsOfAsset(rr, neutralHeld.filter((r) => rowAsset(r) === a), cols6, fullSd[a]).gaps, after = gapsOfAsset(rr, twinHeld.filter((r) => rowAsset(r) === a), cols6, fullSd[a]).gaps;
      byAsset[a] = { before, after };
      const names = Object.keys(cols6);
      say(`[twin] calibration: held-in ${held} asset ${a} (calibrated on the other ${train.length} fit day(s)): gaps (sd) before -> after ${names.map((n) => `${n} ${r2(before[n])} -> ${r2(after[n])}`).join(', ')}`);
      for (const n of names) if (finite(before[n]) && finite(after[n])) { sumB += Math.abs(before[n]); sumA += Math.abs(after[n]); nGap++; }
    }
    folds.push({ day: held, byAsset });
  }
  const res: HeldInResult = { ran: true, iterations: pick, passes, folds, meanBefore: nGap ? sumB / nGap : NaN, meanAfter: nGap ? sumA / nGap : NaN };
  say(`[twin] calibration: held-in check (${days.length} folds, ${pick} iteration(s) each, ${passes} day passes): mean |gap| over assets, days and the ${Object.keys(cols6).length} features, uncalibrated ${r2(res.meanBefore)} sd, calibrated on the other days ${r2(res.meanAfter)} sd (report only)`);
  return res;
}
