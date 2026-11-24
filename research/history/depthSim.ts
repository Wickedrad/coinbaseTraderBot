// The Kalshi order book's depth, simulated between the history's minute quotes (Steven, Oct 29). Kalshi's history keeps
// one quote a minute per contract; the bot's recordings keep every level and every change. research/depthStudy.ts
// measures on the recordings how the book is shaped and how it moves, against what the history also knows (minutes to
// close and the quote's mid); this plays that back around each quote the history replay gives (the anchors):
//   - at each anchor, the book is re-centred on the anchor's bid and ask: levels still on the right side keep their size
//     (so walls persist), levels the quote moved through go, and empty places near the top are drawn from the measured
//     share of time each level is quoted and its size's median and 90th percentile (log-normal);
//   - until the next anchor, each level's orders arrive and are cancelled at the measured queue-reactive rates
//     (Huang, Lehalle and Rosenbaum 2015: per distance from the best price and queue size), and trades take the best
//     level at the measured rate, size and side;
//   - the trades' rate and side follow where the mid goes by the next quote (the study's flow by move): on the way up,
//     mostly YES takers lift the asks, so a resting order fills just before the price moves against it, as on the
//     real book (adverse selection). Without it, the simulated flow was blind to the next quote, and resting orders
//     filled at no cost: the Oct 27-30 check had depth at +$880 against the real quotes' -$4.51.
// Every draw is seeded by the contract and the anchor's time, so a day plays out the same wherever it is replayed (the
// GitHub runners and the Windows trainer, which bundles this file).
//
// Per asset, and by a causal stress state (Nov 22, round R1; schema 2 of the model file, research/history/depthModelVersion.ts):
// the four assets are not one market (the real days: BTC trades ~3,000 a minute, ETH/SOL/XRP 190-300; BTC's books are ~10x deeper),
// and inside one asset the real books carry one state factor: a contract that is moving NOW has a wide, thin book and small
// trades. So a model file also carries `byAsset`: per asset, the same shape and flow rows, keyed by asset, and by a stress bucket
// of 0 calm, 1 normal, 2 active. The chain of rows a contract's book is drawn from (written down, tested):
//   (asset, stress) row  ->  (asset) row  ->  pooled row (then the pooled table's own nearest cell).
// A row that is missing or thin (shape: under MIN_SHAPE_SAMPLES samples, flow: MIN_FLOW_SECONDS or fewer seconds: the study's own
// filters) is never used: the contract backs off to the next row of the chain. A ticker whose asset the model has no block for
// uses the pooled rows, and a model WITHOUT `byAsset` plays exactly as it always did (bit for bit; the golden hashes hold).
// The stress of a contract at time t is the mean absolute change of its MINUTE mid (the quote at the minute stamps, cents) over
// its last STRESS_MINUTES completed minutes (`minuteStress` below: the one definition the study and the simulator share), bucketed
// with the model's own edges for that asset. It reads only quotes stamped at or before t, so no book at time t sees a later quote.
//
// What `play` actually reads of a model (Nov 22, R1 fix round 1): from the chosen SHAPE row only levelQuoted, levelFilledP50 and P90,
// tradesPerMin.mean, tradeSize p50 and p90, takerYesShare, topChangesPerMin.mean and gapShare (byMove and the model's `informed` block
// only behind USE_NEXT_MOVE, which is off). The FLOW rows (pooled, per asset and per stress: `flow`, `byAsset.*.flow`, `flowRow`), the
// `informed` block, the rows' spread and wall fields and `fit` are written by the study and backed off here, but NOT played: a change that
// is meant to make one asset's twin different has to change the shape-row fields above, or make `play` read `flowRow`.
//
// The empty side (schema 2, `gapShare`) is netted against the twin's own unquoted lead. The requote layer quotes a contract for the first time a
// minute after its open (its first candle ends then), so 5 of the twin's 61 15 s slots are unquoted before any draw is made, which is
// about the mean real unquoted mass already (real quotedShare p10/p50/p90 0.85/0.915/0.966): a draw of the real empty-side share on top of
// it counts that time twice and pushes the twin's quotedShare below the real one. The study therefore also records, per asset and pooled,
// the real mean UNQUOTED share of a whole life (`lives.unquotedShare`: the lead before the first quote plus every empty or crossed
// instant, over all slots), and the simulator draws only what is missing: with L the slots the contract is unquoted before its first
// quote (counted at its first play: the time of that quote from its open, plus the slot taken just before it) and S = 61,
// p = max(0, (unquotedShare * S - L) / (S - L)), spread over the rows by their own gapShares (scale = p / the rows' mean gapShare, at most 1: the
// draw is never above what the study measured), so the twin's expected total unquoted share is the real one, and never more.
//
// Per-asset LEVEL calibration (Nov 22, round R2; schema 3 of the model file). After R1 the asset scales were right but the twin still sat
// below the real days, per asset, in the size of the book (depth10, the best level), the size of a trade, and the rates of quote changes
// and trades. The fix is a first-moment calibration FITTED on the FIT days (research/history/depthCalibrate.ts, run by the workflow after
// the depth fit): a model file may carry `calibration`, per asset five multipliers, all neutral at 1 (CALIBRATION_KNOBS):
//   tradeRateMult  the trade rate;               tradeSizeMult  the trade sizes (median and 90th percentile alike);
//   levelSizeMult  every level's drawn size and the cap (the existing knob);
//   topSizeMult    the best level's size ON TOP of levelSizeMult (level 0 only: its size relative to the others);
//   flickMult      the measured best-price change rate the flicker is made up to (the rate `topChangesPerMin` says, times flickMult,
//                  less what the fill-in makes anyway, flickBasePerSec): a factor on the quote-change rate, not on flickBasePerSec,
//                  because a larger flickBasePerSec would make LESS flicker.
// The parameters a DepthSim plays a ticker with are resolved in this order, each layer over the one before (`DepthSim.paramsFor`, tested):
//   1. the code defaults (DEFAULT_DEPTH_SIM_PARAMS);
//   2. the model's own `params` block;
//   3. the model's `calibration` block for the ticker's ASSET, MULTIPLIED onto the knobs in force after layer 2 (tradeRateMult, tradeSizeMult,
//      levelSizeMult; topSizeMult and flickMult are calibration-only knobs, neutral 1, that no other layer sets);
//   4. the caller's params (a sweep's best.json): a key the caller names REPLACES what layers 1-3 gave that knob, as a caller's params always did.
//      A sweep's best.json names all of them, so it replaces the calibrated level, size and rate knobs for every asset: the fill stage says so
//      (a WARNING) when both are present.
// A model WITHOUT `calibration`, and a ticker whose asset has no block in it, play exactly as before (layers 1, 2 and 4 only; the event
// stream is bit for bit the same, and the golden hashes of tests/depthSimWalk.test.ts hold). The multipliers are per ASSET and CONSTANT
// within a run: no time, day, quote or any later quantity feeds them (they are numbers in the model file, fitted on other days), so
// they add no look-ahead and no clock; the draws stay seeded by the contract and the quote's time.

import fs from 'fs';
import { assetFromSeries } from '../../bot/marketdata/seriesDiscovery';
import { hashStr } from './historyReplay';
import { DEPTH_MODEL_SCHEMA } from './depthModelVersion';

export const DEPTH_LEVELS = 10;
/** Prices in tenths of a cent: Kalshi quotes in tenths below 10 cents and above 90 cents, whole cents between. */
export const PX = 1000;
export const tickAt = (px: number) => (px < 100 || px > 900 ? 1 : 10);
/** Ticks between a price and the best price on its side (both in tenths of a cent). */
export const ticksFrom = (px: number, best: number) => Math.round(Math.abs(px - best) / tickAt(best));
const MIN = 60_000;
/** The time between the replay's quotes (research/history/historyReplay.ts requotes every quarter-minute; research/goLiveTally.ts ANCHOR_MS). */
const ANCHOR_MS = 15_000;
/** The study's buckets (research/depthStudy.ts): minutes to close, mid in cents, queue size in contracts. */
const TAU_EDGES = [1, 3, 6, 10, 15, 60, Infinity];
const MID_EDGES = [10, 25, 40, 60, 75, 90, 101];
const Q_EDGES = [1, 10, 50, 200, 1000, Infinity];
const bucket = (edges: number[], x: number) => { const i = edges.findIndex((e) => x < e); return i < 0 ? edges.length - 1 : i; };

type Quant = { n: number; mean: number; p10: number; p50: number; p90: number };
/** The trade flow over a quarter-minute by where the mid went (research/depthStudy.ts byMove: down, flat, up). */
export interface MoveFlow { segs: number; tradesPerSec: number; takerYesShare: number | null }
export interface ShapeCell { ti: number; mi: number;
  /** The stress bucket of an asset block's row (0 calm, 1 normal, 2 active); absent: the asset's row over every stress (and the pooled rows). */
  si?: number;
  samples: number; levelQuoted: number[]; levelFilledP50: number[]; levelFilledP90: number[]; tradesPerMin: Quant; tradeSize: Quant; takerYesShare: number | null; byMove?: MoveFlow[]; topChangesPerMin?: Quant;
  /** The share of 15 s instants (after the contract was first quoted) at which the book had an empty side or was crossed or locked: the
   *  simulator leaves one side of the book empty at the end of that share of its quarter-minutes. Absent in an older model: never. */
  gapShare?: number }
/** What the study measured of whole contract lives (open to close, in the judge's 15 s slots): the mean share of a life's slots that were
 *  NOT quoted (no book yet, an empty side, a crossed or locked book), and the mean slots before the first quote. The simulator nets
 *  its empty-side draw against it (see the header). Absent in an older model: the rows' own `gapShare` is drawn as measured. */
export interface LifeStats { n: number; unquotedShare: number; leadSlots?: number }
/** The knobs of a calibration block, per asset (see the header: what each scales). All neutral at 1. */
export const CALIBRATION_KNOBS = ['tradeRateMult', 'tradeSizeMult', 'topSizeMult', 'levelSizeMult', 'flickMult'] as const;
export type CalibrationKnob = (typeof CALIBRATION_KNOBS)[number];
/** One asset's multipliers. */
export type AssetCalibration = Record<CalibrationKnob, number>;
/** The format of the `calibration` block (its own `schema`; the model file's schema says the block may be there at all). */
export const CALIBRATION_SCHEMA = 1;
/** The range every multiplier is clipped to: an algorithm setting of the calibration (a fit that wants more than 5x or less than a fifth of
 *  the measured knob has hit something the knob cannot fix), not a tuned number. A file with a multiplier outside it is refused. */
export const CALIBRATION_CLIP: Readonly<{ lo: number; hi: number }> = Object.freeze({ lo: 0.2, hi: 5 });
export const clipMult = (x: number): number => Math.min(CALIBRATION_CLIP.hi, Math.max(CALIBRATION_CLIP.lo, x));
/** The per-asset level calibration (research/history/depthCalibrate.ts): written next to the model's tables by the calibration stage, read here.
 *  `fitDays`: the days it was fitted on (the model's own fit days); `iterations`: the fixed-point iterations it ran; `byAsset`: the multipliers of
 *  each asset it had real and twin lives for. `residual` (optional, informational): per asset the last standardized gaps, twin minus real. */
export interface DepthCalibration { schema: number; fitDays: string[]; iterations: number; byAsset: Record<string, AssetCalibration>; residual?: Record<string, Record<string, number>>;
  /** The code the multipliers were fitted with (written by the calibration stage, checked by a reuse): the multipliers are a fit of THIS simulator, requote layer and
   *  feature code on the FIT days, so a model reused (depth_model_run) under other code would carry numbers fitted to a different twin. */
  code?: CalibrationCode }
/** What a calibration is a fit of: the simulator's source (a hash of depthSim.ts with comments and whitespace out, so any change that can move its stream does), the
 *  requote layer's version (REPLAY_VERSION) and the feature code's version (FEATURE_CODE_VERSION). Plain strings: this file only holds and validates them. */
export interface CalibrationCode { sim: string; replay: string; featureCode: string }
/** Neutral multipliers: a model played with these is the model played without a calibration. */
export const NEUTRAL_CALIBRATION: Readonly<AssetCalibration> = Object.freeze({ tradeRateMult: 1, tradeSizeMult: 1, topSizeMult: 1, levelSizeMult: 1, flickMult: 1 });
/** Fewest samples a shape row of an asset block needs before it feeds a book (the study's own filter: it writes no thinner row). */
export const MIN_SHAPE_SAMPLES = 20;
/** Most seconds a flow row of an asset block may hold and still be refused (the study writes only rows over this). */
export const MIN_FLOW_SECONDS = 60;
/** Fewest quarter-minutes a cell's flow by move needs before it is used (else the cell's flow over all moves). */
export const MOVE_MIN_SEGS = 20;
/** Where the mid goes: 0 down, 1 flat (within half a tick), 2 up. Mids in cents (as research/depthStudy.ts moveOf). */
export const moveOf = (from: number, to: number): 0 | 1 | 2 => { const half = from < 10 || from > 90 ? 0.05 : 0.5, d = to - from; return d < -half ? 0 : d > half ? 2 : 1; };

// ---------------------------------------------------------------------------------------------------------------
// The causal stress state: how much a contract is moving right now, from what its history already shows.

/** The assets a ticker is read as when the model names none of its own (the four 15-minute series the twin replays). */
export const DEPTH_ASSETS = ['BTC', 'ETH', 'SOL', 'XRP'] as const;
/** A contract's asset from its ticker (KXBTC15M-26NOV11..., KXETHD-...): the bot's own series helper (bot/marketdata/seriesDiscovery.ts
 *  assetFromSeries) on the ticker's series, over `assets`; undefined for an asset not among them (its books use the pooled rows). */
export const assetOfTicker = (ticker: string, assets: Iterable<string> = DEPTH_ASSETS): string | undefined => assetFromSeries(ticker.split('-')[0], assets);

/** Completed minutes the stress averages over. The definition (no quantity from minute m or later reaches a book before minute m ends):
 *  a contract's MINUTE mid M[k] is the mid of its quote stamped at minute k (cents; the requote layer reproduces the real one to
 *  0.03-0.05c); at a time t in minute m the minutes completed are m-1, m-2 and m-3, and the stress is the mean of |M[k] - M[k-1]|
 *  for k = m, m-1, m-2 whose two mids exist: the quote stamped m*MIN is at or before t, so it is history. With no such pair (a
 *  contract in its first minute, or with gaps) there is no stress and the asset's own row is used. One number, because the real
 *  within-asset factor is "moving now" (spread, quote changes, mid moves, trades up; sizes down) and the minute mid is what the
 *  requote day and the recording both carry the same way. */
export const STRESS_MINUTES = 3;
/** The minute mid in cents from a quote's bid and ask in tenths of a cent (integers: the study and the simulator get bit-identical mids). */
export const minuteMidCents = (bidTenths: number, askTenths: number): number => (bidTenths + askTenths) / 20;
/** The stress at minute `minute` (see STRESS_MINUTES); `midAt(k)` is the minute mid at stamp k, undefined when there is none. Rounded to
 *  1e-6 so a stress that sits on an edge is on it for the study and for the simulator alike. */
export function minuteStress(midAt: (minute: number) => number | undefined, minute: number): number | undefined {
  let sum = 0, n = 0;
  for (let k = minute; k > minute - STRESS_MINUTES; k--) {
    const a = midAt(k), b = midAt(k - 1);
    if (a !== undefined && b !== undefined) { sum += Math.abs(a - b); n++; }
  }
  return n ? Math.round((sum / n) * 1e6) / 1e6 : undefined;
}
/** The grid the study accumulates stress on and cuts its terciles at (cents): bin f holds a stress up to STRESS_GRID[f] (above the last
 *  value, bin STRESS_GRID.length). The stored edges are values of this grid, so the study's buckets and the simulator's are the same. */
export const STRESS_GRID = [0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10, 15, 25] as const;
export function stressBin(v: number): number { for (let f = 0; f < STRESS_GRID.length; f++) if (v <= STRESS_GRID[f]) return f; return STRESS_GRID.length; }
/** The bucket of a stress for an asset's edges: calm (0) up to the first edge, normal (1) up to the second, active (2) above. */
export const stressBucket = (edges: readonly [number, number], v: number): 0 | 1 | 2 => (v <= edges[0] ? 0 : v <= edges[1] ? 1 : 2);

/** The life of a contract the judge's quotedShare counts over: a 15-minute contract, one slot every ANCHOR_MS from its open to its close,
 *  both ends in (61 slots). The twin replays 15-minute contracts only. */
export const LIFE_MS = 15 * MIN;
export const LIFE_SLOTS = LIFE_MS / ANCHOR_MS + 1;
/** The share of the rows' `gapShare` the simulator draws for a contract (0 to 1), so that its expected unquoted slots are the real ones and
 *  no more: `unquotedShare` is the real mean unquoted share of a life, `meanGap` the rows' mean empty-side share (after the first quote),
 *  `leadSlots` the slots the contract is unquoted before its first quote. The draw p = max(0, (unquotedShare * S - L) / (S - L)) is the
 *  per-slot share that, over the S - L slots after the first quote, makes up what the real unquoted mass has beyond the lead the twin
 *  already has; it is carried by the rows as a scale of their own shares, never above 1 (a real lead longer than the twin's is not made up
 *  with more empty sides than the study measured). No `unquotedShare`, or rows with no share: 1, the rows as measured. */
export function gapScale(unquotedShare: number | undefined, meanGap: number, leadSlots: number): number {
  if (unquotedShare === undefined || !(meanGap > 0)) return 1;
  const L = Math.min(LIFE_SLOTS - 1, Math.max(1, leadSlots));
  const p = Math.max(0, (unquotedShare * LIFE_SLOTS - L) / (LIFE_SLOTS - L));
  return Math.min(1, p / meanGap);
}
/** The mean empty-side share of rows, weighted by the instants each stands for (its samples over one minus its share: the study's share is
 *  of the instants after the first quote, and its samples are those left after the empty ones). */
export function meanGapShare(rows: Iterable<{ samples: number; gapShare?: number }>): number {
  let w = 0, g = 0;
  for (const r of rows) { const x = r.gapShare ?? 0, n = r.samples / Math.max(1e-6, 1 - Math.min(x, 0.999)); w += n; g += n * x; }
  return w > 0 ? g / w : 0;
}
export interface FlowCell { offset: number; qi: number; si?: number; seconds: number; addPerSec: number; cancelPerSec: number; addSize: Quant; cancelSize: Quant }
/** One asset's rows of the model: the shape and flow rows of research/depthStudy.ts, each keyed by (the study's cell) and a stress bucket
 *  `si` (rows without `si` are the asset's own over all stress), and the stress edges the study cut the asset's buckets at. */
export interface AssetBlock { shape: ShapeCell[]; flow: FlowCell[];
  /** The asset's stress terciles over the FIT samples: a stress up to edges[0] (cents) is bucket 0, up to edges[1] bucket 1, else 2. */
  stress?: { edges: [number, number]; n: number };
  /** The asset's real unquoted share of a life (see LifeStats). */
  lives?: LifeStats }
/** research/depthStudy.ts's --out: the depth model. */
export interface DepthModel { days: string[]; shape: ShapeCell[]; flow: FlowCell[];
  /** The schema of the file (research/history/depthModelVersion.ts); absent: 0, the pooled tables only. */
  schema?: number;
  /** Per asset (BTC, ETH, SOL, XRP): the shape and flow rows by asset and stress, written next to the pooled `shape` and `flow` above. */
  byAsset?: Record<string, AssetBlock>;
  /** The real unquoted share of a life over every asset (see LifeStats): what the pooled rows' empty-side draw is netted against. */
  lives?: LifeStats;
  /** research/depthStudy.ts informed flow: the share of trades that took the side the mid went over the next minute. */
  informed?: { n: number; agree: number };
  /** The per-asset level calibration of the fit days (schema 3; see the header and DepthCalibration). Absent: the model plays as measured. */
  calibration?: DepthCalibration;
  /** Optional: depth simulator parameters this model should be played with (override the defaults; the caller's own win over
   *  these). Absent in every model research/depthStudy.ts writes; a sweep's best candidate can be put here. */
  params?: Partial<DepthSimParams> }

export function readDepthModel(file: string): DepthModel | undefined {
  try {
    const m = JSON.parse(fs.readFileSync(file, 'utf8')) as DepthModel;
    if (!(Array.isArray(m.shape) && m.shape.length && Array.isArray(m.flow) && m.shape.every((c) => Number.isInteger(c.ti) && Array.isArray(c.levelQuoted)))) return undefined;
    validateDepthModel(m);
    return m;
  } catch { return undefined; }
}

/** The model file's schema (0 when the file names none: the pooled tables of before schema 2). */
export const modelSchema = (m: { schema?: number }): number => m.schema ?? 0;

/** Throws on a calibration block the simulator cannot read as it was meant: not this block format, no fit days, no iterations count, a
 *  multiplier missing, not a number or outside the clip range. (Which days it was fitted on is checked against the split by historyTwin.ts.) */
export function validateCalibration(c: DepthCalibration): void {
  if (typeof c !== 'object' || c === null || Array.isArray(c)) throw new Error('the depth model\'s calibration must be an object');
  if (c.schema !== CALIBRATION_SCHEMA) throw new Error(`the depth model's calibration is block format ${String(c.schema)} and this code reads format ${CALIBRATION_SCHEMA}: fit it again with this code`);
  if (!Array.isArray(c.fitDays) || !c.fitDays.length || !c.fitDays.every((d) => typeof d === 'string')) throw new Error('the depth model\'s calibration does not record the days it was fitted on');
  if (!Number.isInteger(c.iterations) || c.iterations < 0) throw new Error(`the depth model's calibration must record a whole number of iterations from 0, got ${String(c.iterations)}`);
  if (c.code !== undefined) for (const k of ['sim', 'replay', 'featureCode'] as const) if (typeof c.code?.[k] !== 'string' || !c.code[k]) throw new Error(`the depth model's calibration code stamp must name the ${k} (a non-empty string)`);
  if (typeof c.byAsset !== 'object' || c.byAsset === null || Array.isArray(c.byAsset)) throw new Error('the depth model\'s calibration needs byAsset: an object of asset blocks');
  for (const [a, b] of Object.entries(c.byAsset)) for (const k of CALIBRATION_KNOBS) {
    const v = (b as Partial<AssetCalibration> | undefined)?.[k];
    if (typeof v !== 'number' || !Number.isFinite(v) || v < CALIBRATION_CLIP.lo || v > CALIBRATION_CLIP.hi) throw new Error(`calibration.byAsset.${a}.${k} must be a number from ${CALIBRATION_CLIP.lo} to ${CALIBRATION_CLIP.hi}, got ${String(v)}`);
  }
}

/** Throws on a model file the simulator cannot read as it was meant: a schema newer than this code knows, `byAsset` without schema 2, a
 *  `calibration` without schema 3 or with a bad multiplier, rows without the keys they are looked up by, or stress rows without the asset's
 *  stress edges. A pooled-only model passes as it is. */
export function validateDepthModel(m: Pick<DepthModel, 'schema' | 'byAsset' | 'lives' | 'calibration'>): void {
  const sch = m.schema;
  const lives = (l: LifeStats | undefined, where: string) => { if (l !== undefined && !(Number.isFinite(l.unquotedShare) && l.unquotedShare >= 0 && l.unquotedShare <= 1 && Number.isFinite(l.n) && l.n >= 0)) throw new Error(`${where}: the unquoted share of a life must be a number from 0 to 1 over n lives`); };
  lives(m.lives, 'the depth model\'s lives');
  if (sch !== undefined && (!Number.isInteger(sch) || sch < 0)) throw new Error(`the depth model's schema must be a whole number from 0, got ${String(sch)}`);
  if (modelSchema(m) > DEPTH_MODEL_SCHEMA) throw new Error(`the depth model is schema ${sch} and this code reads up to schema ${DEPTH_MODEL_SCHEMA}: refit it with this code`);
  if (m.calibration !== undefined) {
    if (modelSchema(m) < 3) throw new Error(`the depth model has a calibration block but schema ${modelSchema(m)} (it needs schema 3 or more)`);
    validateCalibration(m.calibration);
  }
  if (m.byAsset === undefined) return;
  if (modelSchema(m) < 2) throw new Error(`the depth model has byAsset blocks but schema ${modelSchema(m)} (they need schema 2 or more)`);
  if (typeof m.byAsset !== 'object' || m.byAsset === null || Array.isArray(m.byAsset)) throw new Error('the depth model\'s byAsset must be an object of asset blocks');
  for (const [a, b] of Object.entries(m.byAsset)) {
    if (!Array.isArray(b?.shape) || !Array.isArray(b?.flow)) throw new Error(`byAsset.${a} needs shape and flow lists`);
    lives(b.lives, `byAsset.${a}.lives`);
    let stressed = false;
    for (const c of b.shape) {
      if (!Number.isInteger(c.ti) || !Number.isInteger(c.mi) || !Array.isArray(c.levelQuoted)) throw new Error(`byAsset.${a}: a shape row without its ti, mi and levels`);
      if (c.si !== undefined) { if (![0, 1, 2].includes(c.si)) throw new Error(`byAsset.${a}: a shape row's stress bucket must be 0, 1 or 2, got ${String(c.si)}`); stressed = true; }
    }
    for (const f of b.flow) {
      if (!Number.isInteger(f.offset) || !Number.isInteger(f.qi)) throw new Error(`byAsset.${a}: a flow row without its offset and queue bucket`);
      if (f.si !== undefined) { if (![0, 1, 2].includes(f.si)) throw new Error(`byAsset.${a}: a flow row's stress bucket must be 0, 1 or 2, got ${String(f.si)}`); stressed = true; }
    }
    const e = b.stress?.edges;
    if (stressed && !(Array.isArray(e) && e.length === 2 && e.every(Number.isFinite) && e[0] <= e[1])) throw new Error(`byAsset.${a} has stress rows but no ascending stress edges`);
  }
}

/** A seeded uniform draw (the same generator as historyReplay's normals). */
function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const normal = (u: () => number) => Math.sqrt(-2 * Math.log(Math.max(u(), 1e-12))) * Math.cos(2 * Math.PI * u());
/** A log-normal draw with this median and 90th percentile, at least 1 contract; `mult` scales it (1: as measured). */
function lognormal(u: () => number, p50: number, p90: number, mult = 1): number {
  if (!(p50 > 0)) return 1;
  const s = p90 > p50 ? Math.log(p90 / p50) / 1.2816 : 0;
  return Math.max(1, Math.round(p50 * mult * Math.exp(s * normal(u))));
}
/** A seeded Poisson count: by multiplying uniforms when small, else its normal approximation. */
function poisson(u: () => number, lambda: number): number {
  if (!(lambda > 0)) return 0;
  if (lambda > 30) return Math.max(0, Math.round(lambda + Math.sqrt(lambda) * normal(u)));
  const L = Math.exp(-lambda);
  let k = 0, p = u();
  while (p > L) { k++; p *= u(); }
  return k;
}
/** The total of n log-normal sizes (median p50, 90th percentile p90): drawn one by one up to 30, else from the mean and
 *  spread of the sum. */
function sumOf(u: () => number, n: number, p50: number, p90: number): number {
  if (n <= 0) return 0;
  if (n <= 30) { let s = 0; for (let i = 0; i < n; i++) s += lognormal(u, p50, p90); return s; }
  const sg = p90 > p50 && p50 > 0 ? Math.log(p90 / p50) / 1.2816 : 0, m = Math.max(1, p50) * Math.exp((sg * sg) / 2);
  const sd = m * Math.sqrt(Math.max(0, Math.exp(sg * sg) - 1));
  return Math.max(n, Math.round(n * m + Math.sqrt(n) * sd * normal(u)));
}

type Level = { price: number; size: number };
type Side = 'bid' | 'ask';
interface SimBook { bid: Map<number, number>; ask: Map<number, number> } // price in tenths of a cent -> size

export type DepthEv = { t: number; k: string; ticker: string; [key: string]: unknown };

/** Whether the trade flow may depend on the next quote (off: that is the future). Never a tuning parameter: it stays out of
 *  DepthSimParams and out of DEPTH_PARAM_SPACE, so no optimizer can switch the look-ahead on. */
const USE_NEXT_MOVE = false;

// ---------------------------------------------------------------------------------------------------------------
// The tuning constants (Nov 22: they were hand constants, tuned by hand per verdict, one 4-hour run at a time). They are one
// object now, so a machine optimizer can set them (research/historyTwin.ts --stage sweep). DEFAULT_DEPTH_SIM_PARAMS holds
// TODAY'S values, and the fill-in with them is bit-identical to the version before the object existed (tests/depthSimWalk.test.ts
// holds the golden hash of a fixed synthetic day, computed from the commit before). No parameter can introduce look-ahead or
// a clock: every draw stays seeded by the contract and the quote's time.

/** The depth fill-in's dynamic constants. Seconds, milliseconds and rates as named; `*Sd` are standard deviations. */
export interface DepthSimParams {
  /** How fast a level's size goes back to its drawn size (seconds; was REVERT_S). */
  revertS: number;
  /** The best level's, faster: its makers put back what trades take (Nov 4 twin: refilled at the others' pace, trades kept
   *  the best level thin or empty, and the mid stopped following the index, 0.19 against 0.77 real; was REVERT_TOP_S). */
  revertTopS: number;
  /** A level's own second-to-second wander (sd as a share of its size; was STEP_SD). */
  stepSd: number;
  /** The fill-in's own best-price changes a second before flicker (Nov 4 twin: ~120 a minute once trades and sizes were
   *  right; with 0.9 the best price changed ~455 times a minute against the real ~350; was FLICK_BASE_PER_SEC). */
  flickBasePerSec: number;
  /** Most trade-sized prints a sweep of one level makes before the rest of it is cancelled (an integer; was SWEEP_PRINTS). */
  sweepPrints: number;
  /** How far a level's size moves within one contract (log sd), the rest of the measured spread being between contracts
   *  (was WITHIN_SD). */
  withinSd: number;
  /** How much one contract's trade rate differs from another's (log sd; its mean stays the measured rate; was ACTIVITY_SD). */
  activitySd: number;
  /** A level's size never goes above this many times its measured 90th percentile (was the literal 4 in the net change). */
  capMult: number;
  /** A flickered best level comes back after at least this many ms (was the literal 20) and ... */
  flickBackMinMs: number;
  /** ... within this many more ms, uniformly (was the literal 180). */
  flickBackSpanMs: number;
  /** NEW knob, neutral at 1: a factor on the measured trade rate (every contract, every cell). */
  tradeRateMult: number;
  /** NEW knob, neutral at 1: a factor on the measured trade sizes (median and 90th percentile alike). */
  tradeSizeMult: number;
  /** NEW knob, neutral at 1: a factor on every drawn level size (and on the cap above, so the shape scales as a whole). */
  levelSizeMult: number;
}

/** TODAY'S values (the constants the fill-in has been run with since the Nov 4 twin). */
export const DEFAULT_DEPTH_SIM_PARAMS: Readonly<DepthSimParams> = Object.freeze({
  revertS: 10, revertTopS: 1, stepSd: 0.1, flickBasePerSec: 2.6, sweepPrints: 3, withinSd: 0.7, activitySd: 0.6,
  capMult: 4, flickBackMinMs: 20, flickBackSpanMs: 180, tradeRateMult: 1, tradeSizeMult: 1, levelSizeMult: 1,
});
export const DEPTH_PARAM_NAMES = Object.keys(DEFAULT_DEPTH_SIM_PARAMS) as Array<keyof DepthSimParams>;

/** What an optimizer may search: bounds, the scale to search them on, and why those bounds. `int`: rounded after sampling. The
 *  defaults sit inside every range (a test holds it). Left OUT of the space on purpose, and why: USE_NEXT_MOVE and
 *  MOVE_MIN_SEGS (look-ahead: never tunable), DEPTH_LEVELS, the TAU/MID/Q bucket edges and ANCHOR_MS / LOOKAHEAD_MS (structure
 *  shared with research/depthStudy.ts and the replay), the 1.2816 normal quantile, the Poisson switch at 30, the flicker guards
 *  (room > 40, room - 30), the /2 (a flicker is two best-price changes) and the seed salts. */
export interface ParamBound { lo: number; hi: number; scale: 'log' | 'linear'; note: string; int?: boolean }
export const DEPTH_PARAM_SPACE: Readonly<Record<keyof DepthSimParams, ParamBound>> = Object.freeze({
  revertS: { lo: 2, hi: 60, scale: 'log', note: 'seconds for a level to go back to its drawn size; default 10' },
  revertTopS: { lo: 0.25, hi: 10, scale: 'log', note: 'seconds for the best level to be put back by its makers; default 1' },
  stepSd: { lo: 0.02, hi: 0.4, scale: 'log', note: 'a level wanders by this share of its size a second; default 0.1' },
  flickBasePerSec: { lo: 0.5, hi: 6, scale: 'linear', note: 'best-price changes a second the fill-in makes before flicker; the real books change ~5 a second; default 2.6' },
  sweepPrints: { lo: 1, hi: 6, scale: 'linear', int: true, note: 'trade-sized prints a sweep of one level makes; default 3' },
  withinSd: { lo: 0.2, hi: 1.5, scale: 'linear', note: 'log sd of a level size within one contract; default 0.7' },
  activitySd: { lo: 0.1, hi: 1.4, scale: 'linear', note: 'log sd of a contract trade rate around the measured one; default 0.6' },
  capMult: { lo: 1.5, hi: 10, scale: 'log', note: 'a level never exceeds this many times its measured 90th percentile; default 4' },
  flickBackMinMs: { lo: 5, hi: 100, scale: 'log', note: 'ms before a flickered best level is back; default 20' },
  flickBackSpanMs: { lo: 40, hi: 600, scale: 'log', note: 'ms more, uniformly, before it is back; default 180' },
  tradeRateMult: { lo: 0.4, hi: 2.5, scale: 'log', note: 'factor on the measured trade rate (new knob, 1 = measured); default 1' },
  tradeSizeMult: { lo: 0.4, hi: 2.5, scale: 'log', note: 'factor on the measured trade sizes (new knob); default 1' },
  levelSizeMult: { lo: 0.3, hi: 3, scale: 'log', note: 'factor on every drawn level size and the cap (new knob); default 1' },
});

/** The parameters in force: the defaults, then each layer in order (a model's own `params` block, then the caller's), each key
 *  checked. Throws on an unknown name, a non-finite or negative number, or a zero where a time or a factor divides. */
export function resolveDepthSimParams(...layers: Array<Partial<DepthSimParams> | undefined>): DepthSimParams {
  const out: DepthSimParams = { ...DEFAULT_DEPTH_SIM_PARAMS };
  for (const layer of layers) {
    if (!layer) continue;
    for (const [k, v] of Object.entries(layer)) {
      if (!(k in DEFAULT_DEPTH_SIM_PARAMS)) throw new Error(`unknown depth simulator parameter "${k}" (known: ${DEPTH_PARAM_NAMES.join(', ')})`);
      if (v === undefined) continue;
      if (typeof v !== 'number' || !Number.isFinite(v) || v < 0) throw new Error(`depth simulator parameter ${k} must be a finite number of at least 0, got ${String(v)}`);
      out[k as keyof DepthSimParams] = v;
    }
  }
  out.sweepPrints = Math.round(out.sweepPrints);
  for (const k of ['revertS', 'revertTopS', 'capMult', 'tradeRateMult', 'tradeSizeMult', 'levelSizeMult'] as const) if (!(out[k] > 0)) throw new Error(`depth simulator parameter ${k} must be above 0, got ${out[k]}`);
  return out;
}

/** What `DepthSim.paramsFor` returns for a ticker. */
export interface TickerPlay { params: DepthSimParams; topSizeMult: number; flickMult: number; asset?: string }
/** One asset's rows, looked up by the cell keys (a thin row is never loaded: it backs off to the next row of the chain). */
interface AssetRows { shape: Map<number, ShapeCell>; flow: Map<number, FlowCell>; edges?: readonly [number, number];
  /** The block's real unquoted share of a life and the mean empty-side share of its rows (see gapScale); absent: the rows as measured. */
  gap?: { unquoted: number; mean: number } }
/** Cell keys of an asset block: tau bucket, mid bucket and stress bucket (-1: the asset's row over all stress); offset, queue bucket and stress. */
const shapeKey = (ti: number, mi: number, si: number) => (ti * 8 + mi) * 4 + (si + 1);
const flowKey = (off: number, qi: number, si: number) => (off * 8 + qi) * 4 + (si + 1);

export class DepthSim {
  /** What the fill-in emitted (a run's diagnostics): seconds simulated, trades (sweep prints among them), flickers. */
  readonly stats = { seconds: 0, trades: 0, sweepPrints: 0, flickers: 0 };
  /** Which row of the chain fed each quarter-minute's book (a diagnostic: the asset and stress rows, then the pooled ones; `stress[i]`:
   *  anchors drawn from the stress-i row, `asset`: from the asset's row over all stress, `pooled`: from the pooled rows). Kept out of
   *  `stats`, which the golden tests hold exactly. */
  readonly picks = { stress: [0, 0, 0], asset: 0, pooled: 0 };
  /** Anchors of tickers whose asset the model has no block for (their books came from the pooled rows, which `picks` does not count). */
  readonly unblocked = { anchors: 0 };
  private readonly shape = new Map<string, ShapeCell>();
  private readonly flow = new Map<string, FlowCell>();
  private readonly books = new Map<string, SimBook>();
  /** The model's asset blocks, by asset; a ticker's block by ticker (null: the model has none for its asset). */
  private readonly assets = new Map<string, AssetRows>();
  private readonly blockOf = new Map<string, AssetRows | null>();
  /** Per contract: the minute mids (cents, by minute) the stress reads, kept for the last few minutes only. */
  private readonly minuteMids = new Map<string, Map<number, number>>();
  /** Per contract: the share of the rows' empty-side draw it plays (gapScale), set at its first quote from the slots it was unquoted before it. */
  private readonly gapScales = new Map<string, number>();
  /** The pooled rows' real unquoted share of a life and mean empty-side share (see gapScale). */
  private readonly pooledGap?: { unquoted: number; mean: number };
  /** The parameters in force with NO calibration: the defaults, the model's own `params` block, then `params` (each over the one before).
   *  A ticker whose asset the model's calibration names is played with `paramsFor(ticker)` instead (see the header's resolution order). */
  readonly params: DepthSimParams;
  /** The model's calibration, by asset (empty: none), and what each ticker is played with (resolved once per ticker). */
  private readonly cal = new Map<string, AssetCalibration>();
  private readonly tickerPlay = new Map<string, TickerPlay>();
  private readonly callerParams?: Partial<DepthSimParams>;
  /** Anchors played with a calibrated asset's multipliers (a diagnostic, kept out of `stats`, which the golden tests hold exactly). */
  readonly calibrated = { anchors: 0 };

  constructor(private readonly model: DepthModel, params?: Partial<DepthSimParams>) {
    validateDepthModel(model);
    this.callerParams = params;
    for (const [a, c] of Object.entries(model.calibration?.byAsset ?? {})) this.cal.set(a, c);
    for (const c of model.shape) this.shape.set(`${c.ti}|${c.mi}`, c);
    for (const f of model.flow) this.flow.set(`${f.offset}|${f.qi}`, f);
    for (const [a, b] of Object.entries(model.byAsset ?? {})) {
      const rows: AssetRows = { shape: new Map(), flow: new Map(), ...(b.stress ? { edges: b.stress.edges } : {}) };
      for (const c of b.shape) if (c.samples >= MIN_SHAPE_SAMPLES) rows.shape.set(shapeKey(c.ti, c.mi, c.si ?? -1), c);
      if (b.lives) rows.gap = { unquoted: b.lives.unquotedShare, mean: meanGapShare([...rows.shape.values()].filter((c) => c.si === undefined)) };
      for (const f of b.flow) if (f.seconds > MIN_FLOW_SECONDS) rows.flow.set(flowKey(f.offset, f.qi, f.si ?? -1), f);
      this.assets.set(a, rows);
    }
    if (model.lives) this.pooledGap = { unquoted: model.lives.unquotedShare, mean: meanGapShare(model.shape.filter((c) => c.samples >= MIN_SHAPE_SAMPLES)) };
    this.params = resolveDepthSimParams(model.params, params);
  }

  /** What a ticker is played with: the parameters in force (the header's resolution order: defaults, the model's params, the model's
   *  calibration for the ticker's asset multiplied on, the caller's params), the best level's extra multiplier and the quote-change
   *  rate's. `asset`: the calibration block it took (undefined: none, and then these are exactly `this.params`, 1 and 1). Constant for a
   *  ticker, whatever the time or the quote: it is read from the model file once. */
  paramsFor(ticker: string): TickerPlay {
    let p = this.tickerPlay.get(ticker);
    if (p) return p;
    const asset = this.cal.size ? assetOfTicker(ticker, this.cal.keys()) : undefined, c = asset !== undefined ? this.cal.get(asset) : undefined;
    if (!c) p = { params: this.params, topSizeMult: 1, flickMult: 1 };
    else {
      const base = resolveDepthSimParams(this.model.params);                                  // layers 1 and 2
      const layer3: Partial<DepthSimParams> = { tradeRateMult: base.tradeRateMult * c.tradeRateMult, tradeSizeMult: base.tradeSizeMult * c.tradeSizeMult, levelSizeMult: base.levelSizeMult * c.levelSizeMult };
      p = { params: resolveDepthSimParams(this.model.params, layer3, this.callerParams), topSizeMult: c.topSizeMult, flickMult: c.flickMult, asset };  // layers 3 and 4
    }
    this.tickerPlay.set(ticker, p);
    return p;
  }

  /** The asset block of a ticker's asset, undefined when the model has none (the pooled rows then feed its books). */
  private assetRows(ticker: string): AssetRows | undefined {
    let b = this.blockOf.get(ticker);
    if (b === undefined) { const a = this.assets.size ? assetOfTicker(ticker, this.assets.keys()) : undefined; b = a !== undefined ? this.assets.get(a) ?? null : null; this.blockOf.set(ticker, b); }
    return b ?? undefined;
  }

  /** The shape row for a contract's state, by the chain (asset, stress) -> (asset) -> pooled: its own bucket when measured, else the
   *  nearest mid at the same minutes to close, else the nearest minutes to close (the pooled rows' own fallback). `si`: the contract's
   *  stress bucket (undefined: none yet, the asset's row is used). `from` says which row of the chain answered. */
  private pick(tau: number, mid: number, ab?: AssetRows, si?: number): { cell: ShapeCell; from: 'stress' | 'asset' | 'pooled' } {
    const ti = bucket(TAU_EDGES, Math.max(0, tau)), mi = bucket(MID_EDGES, mid);
    if (ab) {
      const s = si !== undefined ? ab.shape.get(shapeKey(ti, mi, si)) : undefined;
      if (s) return { cell: s, from: 'stress' };
      const a = ab.shape.get(shapeKey(ti, mi, -1));
      if (a) return { cell: a, from: 'asset' };
    }
    const own = this.shape.get(`${ti}|${mi}`);
    if (own) return { cell: own, from: 'pooled' };
    let best: ShapeCell | undefined, bd = Infinity;
    for (const c of this.model.shape) { const d = 3 * Math.abs(c.ti - ti) + Math.abs(c.mi - mi); if (d < bd || (d === bd && best && c.samples > best.samples)) { bd = d; best = c; } }
    return { cell: best!, from: 'pooled' };
  }
  /** The row a quarter-minute's book is drawn from, counted in `picks` when the ticker has an asset block (the diagnostic of which rows fed the day). */
  private cell(tau: number, mid: number, ab?: AssetRows, si?: number): ShapeCell {
    const { cell, from } = this.pick(tau, mid, ab, si);
    if (ab) { if (from === 'stress') this.picks.stress[si!]++; else this.picks[from]++; } else this.unblocked.anchors++;
    return cell;
  }

  /** The flow row at a distance from the best price and a queue size, by the chain (asset, stress) -> (asset) -> pooled, an exact queue
   *  bucket first; the pooled table then takes the nearest queue bucket as it always did. (The fill-in plays the shape rows' own flow
   *  today; the flow rows are what a queue-reactive play would read, and what the study measures per asset and stress.) */
  flowRow(ticker: string, off: number, q: number, si?: number): FlowCell | undefined {
    const qi = bucket(Q_EDGES, q), ab = this.assetRows(ticker);
    if (ab) {
      const s = si !== undefined ? ab.flow.get(flowKey(off, qi, si)) : undefined;
      if (s) return s;
      const a = ab.flow.get(flowKey(off, qi, -1));
      if (a) return a;
    }
    for (let k = 0; k < Q_EDGES.length; k++) { const f = this.flow.get(`${off}|${qi + k}`) ?? this.flow.get(`${off}|${qi - k}`); if (f) return f; }
    return undefined;
  }

  /** The shape row (and which of the chain answered) a contract's quote of this mid, minutes to close and stress bucket would be drawn from, as
   *  `play` draws it (for tests and diagnostics; it counts nothing). */
  shapeRow(ticker: string, tau: number, mid: number, si?: number): ShapeCell & { from: 'stress' | 'asset' | 'pooled' } {
    const { cell, from } = this.pick(tau, mid, this.assetRows(ticker), si);
    return { ...cell, from };
  }

  /** The contract's stress bucket at `t` for an asset's edges: its minute mids up to the quote stamped at or before `t` (that of minute
   *  m = t's own minute is recorded when it is played, at the stamp). Undefined: no stress yet (the asset's row). Also records the quote
   *  when it is a minute stamp. */
  private stressNow(ticker: string, t: number, bB: number, bA: number, edges: readonly [number, number]): 0 | 1 | 2 | undefined {
    const m = Math.floor(t / MIN);
    let mm = this.minuteMids.get(ticker);
    if (!mm) this.minuteMids.set(ticker, (mm = new Map()));
    if (t % MIN === 0) { mm.set(m, minuteMidCents(bB, bA)); mm.delete(m - STRESS_MINUTES - 2); }
    const v = minuteStress((k) => mm!.get(k), m);
    return v === undefined ? undefined : stressBucket(edges, v);
  }

  /** Drop a contract's book (settled). */
  forget(ticker: string): void { this.books.delete(ticker); this.minuteMids.delete(ticker); this.gapScales.delete(ticker); for (const k of [...this.scale.keys()]) if (k.startsWith(`${ticker}|`)) this.scale.delete(k); }

  /** Each contract's own depth (Nov 4 twin): the measured sizes' spread (90th percentile ~20x the median) is mostly
   *  between contracts and hours, not second to second. Drawn iid each time, every contract's mean size came out ~15x the
   *  median and its top ~40x the real one; so a contract keeps one draw of that spread, and moves within withinSd. */
  private readonly scale = new Map<string, number>();
  /** A contract's own standard normal draw for one purpose (seeded by its ticker, the same wherever it is replayed). */
  private contractZ(ticker: string, salt: number): number {
    const k = `${ticker}|${salt}`;
    let z = this.scale.get(k);
    if (z === undefined) { z = normal(rng(hashStr(ticker) ^ salt)); this.scale.set(k, z); }
    return z;
  }
  /** A level's size: its measured median and 90th percentile, `P.levelSizeMult` on every level and `top` (the calibration's topSizeMult, 1
   *  for every level but the best one, and for every uncalibrated ticker: x * 1 is x) on the best level only. */
  private size(u: () => number, ticker: string, p50: number | null | undefined, p90: number | null | undefined, P: DepthSimParams, top = 1): number {
    if (!(p50 && p50 > 0)) return 1;
    const sg = p90 && p90 > p50 ? Math.log(p90 / p50) / 1.2816 : 0, sw = Math.min(sg, P.withinSd), sc = Math.sqrt(Math.max(0, sg * sg - sw * sw));
    const z = this.contractZ(ticker, 0x5bd1e995);
    return Math.max(1, Math.round(p50 * P.levelSizeMult * top * Math.exp(sc * z + sw * normal(u))));
  }

  /** The book at an anchor quote (bid and ask in dollars) and its life until `until`: a full snapshot at `t`, then
   *  the changes and trades in between, in time order. `close` is the contract's close time; `nextMid` (dollars), the
   *  next quote's mid, sets the trade flow by where the price is going (unknown: the flow over all moves). */
  play(ticker: string, t: number, bid: number, ask: number, until: number, close: number, nextMid?: number): DepthEv[] {
    const bB = Math.round(bid * PX), bA = Math.round(ask * PX);
    if (!(bB >= 1 && bA <= PX - 1 && bA > bB)) return [];
    const { params: P, topSizeMult: topM, flickMult: flickM } = this.paramsFor(ticker);
    if (P !== this.params) this.calibrated.anchors++;
    const u = rng(hashStr(ticker) ^ Math.floor(t / 1000));
    const ab = this.assetRows(ticker);
    const si = ab?.edges ? this.stressNow(ticker, t, bB, bA, ab.edges) : undefined;
    const cell = this.cell((close - t) / MIN, (bB + bA) / 20, ab, si);
    // The share of the empty-side draw this contract plays: set once, at its first quote (see gapScale).
    let gs = this.gapScales.get(ticker);
    if (gs === undefined) {
      const g = ab?.gap ?? this.pooledGap;
      gs = g ? gapScale(g.unquoted, g.mean, Math.round((t - (close - LIFE_MS)) / ANCHOR_MS) + 1) : 1;
      this.gapScales.set(ticker, gs);
    }
    let b = this.books.get(ticker);
    if (!b) this.books.set(ticker, (b = { bid: new Map(), ask: new Map() }));
    // The move to this quote (Nov 4): the levels it moved through are taken at the quote's own time, a few trade-sized
    // prints each (NO takers on the way down, YES on the way up) and the rest pulled, so an order resting there is picked
    // off as the index moves, not before. The walk toward the NEXT quote this replaces moved the book a quarter-minute
    // ahead of the index (the twin's mid followed the index at 0.19 against 0.77 real) and showed the bot the future.
    const pre: DepthEv[] = [];
    let prePrints = 0;
    for (const side of ['bid', 'ask'] as Side[]) {
      const m = b[side], yes = side === 'ask';
      const gone = [...m.keys()].filter((p) => (side === 'bid' ? p > bB : p < bA)).sort((x, y) => (side === 'bid' ? y - x : x - y));
      for (const p of gone) {
        let q = m.get(p)!, k = 0;
        while (q > 0 && k < P.sweepPrints) {
          const n = Math.min(q, lognormal(u, cell.tradeSize.p50, cell.tradeSize.p90, P.tradeSizeMult));
          pre.push({ t, k: 'trade', ticker, price: p / PX, count: n, takerSide: yes ? 'yes' : 'no', ts: t, sim: 1 });
          pre.push({ t, k: 'delta', ticker, side, price: p / PX, delta: -n, ts: t, sim: 1 });
          q -= n; k++;
        }
        if (q > 0) pre.push({ t, k: 'delta', ticker, side, price: p / PX, delta: -q, ts: t, sim: 1 });
        m.delete(p);
        prePrints += k;
      }
    }
    this.stats.sweepPrints += prePrints; this.stats.trades += prePrints;
    // Re-centre: the quote's levels are the best ones; empty places near the top are drawn.
    for (const [p] of b.bid) if (p > bB || ticksFrom(p, bB) >= DEPTH_LEVELS) b.bid.delete(p);
    for (const [p] of b.ask) if (p < bA || ticksFrom(p, bA) >= DEPTH_LEVELS) b.ask.delete(p);
    for (const side of ['bid', 'ask'] as Side[]) {
      const m = b[side], best = side === 'bid' ? bB : bA, tick = tickAt(best);
      for (let off = 0; off < DEPTH_LEVELS; off++) {
        const p = side === 'bid' ? best - off * tick : best + off * tick;
        if (p < 1 || p > PX - 1 || m.has(p)) continue;
        if (off === 0 || u() < (cell.levelQuoted[off] ?? 0)) m.set(p, this.size(u, ticker, cell.levelFilledP50[off], cell.levelFilledP90[off], P, off === 0 ? topM : 1));
      }
    }
    const levels = (side: Side): Level[] => [...b![side].entries()].sort((x, y) => (side === 'bid' ? y[0] - x[0] : x[0] - y[0])).map(([p, s]) => ({ price: p / PX, size: s }));
    const out: DepthEv[] = [...pre, { t, k: 'book', ticker, bids: levels('bid'), asks: levels('ask'), ts: t, sim: 1 }];
    // Until the next anchor, second by second: each level's adds and cancels arrive at the measured queue-reactive rates
    // (Poisson counts per second, netted into one change per level), and the trades take the best level at the measured
    // rate, size and side. Counting per second, not event by event, keeps a busy book (hundreds of changes a second) cheap.
    // The flow over all moves (Nov 4): the flow by where the price goes next told the book the next quote ahead of time.
    const mv = USE_NEXT_MOVE && nextMid !== undefined && Number.isFinite(nextMid) ? cell.byMove?.[moveOf((bB + bA) / 20, nextMid * 100)] : undefined;
    const byMove = mv && mv.segs >= MOVE_MIN_SEGS ? mv : undefined;
    // Each contract its own activity (Nov 4 twin: the same mean trade rate as the real books, ~650 a minute, but the real
    // contracts spread far wider, AUC 0.78 on trades a minute alone).
    const actScale = Math.exp(P.activitySd * this.contractZ(ticker, 0x2545f491) - P.activitySd * P.activitySd / 2);
    const tradeRate = actScale * (byMove ? Math.max(0, byMove.tradesPerSec) : Math.max(0, cell.tradesPerMin?.mean ?? 0) / 60) * P.tradeRateMult;
    const yesShare = (byMove ? byMove.takerYesShare : undefined) ?? cell.takerYesShare ?? 0.5;
    const best = (side: Side) => { const m = b![side]; let top = side === 'bid' ? -Infinity : Infinity; for (const p of m.keys()) if (side === 'bid' ? p > top : p < top) top = p; return top; };
    // No walk toward the next quote any more (see the move to this quote, above).
    const sweeps: Array<{ at: number; side: Side }> = [];
    let sw = 0;
    // Where the quote stands (tenths of a cent): the anchor's bid and ask, moved only by the walk. The book's levels are
    // placed and refilled around it, not around whatever best a cancel left (Nov 2 twin: drifting off the quote, the
    // fill-in's mid stopped following the index, 0.05 against 0.77 real and 0.66 for the quotes it was built on).
    let refB = bB, refA = bA;
    const inf = this.model.informed, informedP = USE_NEXT_MOVE && inf && inf.n >= 1000 ? Math.min(1, Math.max(0, 2 * (inf.agree - 0.5))) : 0;
    const dir = nextMid !== undefined && Number.isFinite(nextMid) ? Math.sign(Math.round(nextMid * PX) - (bB + bA) / 2) : 0;
    // Each level's size for this quarter-minute, drawn from the measured shape (quoted or not, its size): the adds and
    // cancels pull a queue around it, and it pulls back (revertS). Without the pull the netted flow drifted up to the
    // cap (Nov 2 twin, run 41496163760: the top ~25x the real one's, so a sweep traded thousands at once).
    const target: Record<Side, number[]> = { bid: [], ask: [] };
    for (const side of ['bid', 'ask'] as Side[]) for (let off = 0; off < DEPTH_LEVELS; off++) {
      const p50 = cell.levelFilledP50[off], p90 = cell.levelFilledP90[off];
      target[side][off] = p50 && (off === 0 || u() < (cell.levelQuoted[off] ?? 0)) ? this.size(u, ticker, p50, p90, P, off === 0 ? topM : 1) : 0;
    }
    const pull = 1 - Math.exp(-1 / P.revertS), pullTop = 1 - Math.exp(-1 / P.revertTopS);
    // Flicker (Nov 2 twin: the real best price changes ~324 times a minute, the fill-in's 55): a best level pulled and put
    // back within the second, as the real books' makers do; a trade in that moment takes the next level.
    const realTops = cell.topChangesPerMin?.mean;
    const flickPerSec = realTops !== undefined && Number.isFinite(realTops) ? Math.max(0, (realTops * flickM) / 60 - P.flickBasePerSec) / 2 : 0;
    // Trades a sweep printed come out of the interval's measured count (the real count includes them).
    let owe = prePrints;
    const tradeSz = () => lognormal(u, cell.tradeSize.p50, cell.tradeSize.p90, P.tradeSizeMult);
    for (let sec = t; sec < until; sec += 1000) {
      const end = Math.min(sec + 1000, until);
      this.stats.seconds += (end - sec) / 1000;
      // The walk's sweeps due in this second: the best level traded away in trade-sized prints, the other side follows.
      for (; sw < sweeps.length && sweeps[sw].at < end; sw++) {
        const { at, side } = sweeps[sw], m = b[side], top = best(side);
        if (!Number.isFinite(top)) continue;
        let q = m.get(top)!, k = 0;
        const yes = side === 'ask';
        while (q > 0 && k < P.sweepPrints) {
          const n = Math.min(q, tradeSz());
          out.push({ t: at, k: 'trade', ticker, price: top / PX, count: n, takerSide: yes ? 'yes' : 'no', ts: at, sim: 1 });
          out.push({ t: at, k: 'delta', ticker, side, price: top / PX, delta: -n, ts: at, sim: 1 });
          q -= n; k++;
        }
        // The rest is pulled by its makers (Nov 4 twin: traded in full, sweeps alone printed ~485 trades a minute against
        // the real books' ~250 all told); the far side then quotes at this price, so an order resting here is crossed.
        if (q > 0) out.push({ t: at, k: 'delta', ticker, side, price: top / PX, delta: -q, ts: at, sim: 1 });
        m.delete(top);
        owe += k; this.stats.sweepPrints += k; this.stats.trades += k;
        // The far side moves up behind the price (a down move: a new ask at the level just taken).
        const other: Side = side === 'bid' ? 'ask' : 'bid', om = b[other];
        if (side === 'bid') { refA = top; refB = top - tickAt(top); } else { refB = top; refA = top + tickAt(top); }
        if (!om.has(top)) { const sz = this.size(u, ticker, cell.levelFilledP50[0], cell.levelFilledP90[0], P, topM); om.set(top, sz); out.push({ t: at, k: 'delta', ticker, side: other, price: top / PX, delta: sz, ts: at, sim: 1 }); }
        for (const p of [...om.keys()]) if (ticksFrom(p, top) >= DEPTH_LEVELS) { const d = om.get(p)!; om.delete(p); out.push({ t: at, k: 'delta', ticker, side: other, price: p / PX, delta: -d, ts: at, sim: 1 }); }
      }
      // The second's trades and flickers in time order, each on the book as it stands then.
      let nTr = poisson(u, tradeRate * ((end - sec) / 1000));
      const paid = Math.min(nTr, owe); nTr -= paid; owe -= paid;
      const room = end - 1 - sec;
      type Step = { at: number; kind: 'trade' } | { at: number; kind: 'pull'; side: Side; back: number } | { at: number; kind: 'back'; side: Side; price: number; size: number };
      const steps: Step[] = [];
      for (let i = 0; i < nTr; i++) steps.push({ at: sec + Math.floor(((i + 1) * room) / (nTr + 1)), kind: 'trade' });
      if (room > 40) { const nF = poisson(u, flickPerSec * ((end - sec) / 1000)); for (let i = 0; i < nF; i++) { const at = sec + Math.floor(u() * (room - 30)); steps.push({ at, kind: 'pull', side: u() < 0.5 ? 'bid' : 'ask', back: Math.min(end - 2, at + P.flickBackMinMs + Math.floor(u() * P.flickBackSpanMs)) }); } }
      steps.sort((x, y) => x.at - y.at);
      for (let i = 0; i < steps.length; i++) {
        const st = steps[i], at = st.at;
        if (st.kind === 'trade') {
          // A YES taker buys at the best ask; a NO taker sells YES at the best bid.
          // Informed flow (Nov 2): a measured share of the trades takes the side the price is going (the next quote),
          // the rest are blind; the real books' share is what picks resting orders off before a move.
          const yes = informedP > 0 && dir !== 0 && u() < informedP ? dir > 0 : u() < yesShare, side: Side = yes ? 'ask' : 'bid', m = b[side], top = best(side);
          if (!Number.isFinite(top)) continue;
          const q = m.get(top)!, n = Math.min(q, tradeSz());
          out.push({ t: at, k: 'trade', ticker, price: top / PX, count: n, takerSide: yes ? 'yes' : 'no', ts: at, sim: 1 });
          if (q - n > 0) m.set(top, q - n); else m.delete(top);
          out.push({ t: at, k: 'delta', ticker, side, price: top / PX, delta: -n, ts: at, sim: 1 });
          this.stats.trades++;
        } else if (st.kind === 'pull') {
          const m = b[st.side], top = best(st.side);
          if (!Number.isFinite(top) || m.size < 2) continue;
          const q = m.get(top)!;
          m.delete(top);
          out.push({ t: at, k: 'delta', ticker, side: st.side, price: top / PX, delta: -q, ts: at, sim: 1 });
          const back: Step = { at: st.back, kind: 'back', side: st.side, price: top, size: q };
          let j = i + 1; while (j < steps.length && steps[j].at <= back.at) j++;
          steps.splice(j, 0, back);
          this.stats.flickers++;
        } else {
          const m = b[st.side];
          m.set(st.price, (m.get(st.price) ?? 0) + st.size);
          out.push({ t: at, k: 'delta', ticker, side: st.side, price: st.price / PX, delta: st.size, ts: at, sim: 1 });
        }
      }
      // Then each level's net change over the second.
      const at = end - 1, frac = (end - sec) / 1000;
      for (const side of ['bid', 'ask'] as Side[]) {
        const m = b[side], top = side === 'bid' ? refB : refA;
        const tick = tickAt(top);
        for (let off = 0; off < DEPTH_LEVELS; off++) {
          const p = side === 'bid' ? top - off * tick : top + off * tick;
          if (p < 1 || p > PX - 1) continue;
          const q = m.get(p) ?? 0;
          // Each level wanders about this quarter-minute's drawn size and goes back to it (revertS): the measured
          // per-second adds and cancels, netted, made a random walk of thousands a second that sat at the cap (Nov 4 twin).
          let next = q + (off === 0 ? pullTop : pull) * frac * (target[side][off] - q) + q * P.stepSd * Math.sqrt(frac) * normal(u);
          // The quote's own level, emptied by trades or cancels, is quoted again as often as the real books quote it.
          if (off === 0 && q === 0 && u() < (cell.levelQuoted[0] ?? 1)) next = this.size(u, ticker, cell.levelFilledP50[0], cell.levelFilledP90[0], P, topM);
          const cap = P.capMult * P.levelSizeMult * (off === 0 ? topM : 1) * Math.max(1, cell.levelFilledP90[off] ?? cell.levelFilledP90[cell.levelFilledP90.length - 1] ?? 1);
          next = Math.max(0, Math.min(cap, Math.round(next)));
          const d = next - q;
          if (d === 0) continue;
          if (next > 0) m.set(p, next); else m.delete(p);
          out.push({ t: at, k: 'delta', ticker, side, price: p / PX, delta: d, ts: at, sim: 1 });
        }
      }
    }
    // An instant with an empty side (schema 2, `gapShare`: the real books have one at that share of their 15 s instants, mostly at
    // the price's extremes, where the side with no one behind it empties): the side the price is running out of is left empty in
    // the last millisecond of the quarter-minute, so the instant that follows sees a one-sided book; the next quote draws it again.
    // Drawn last, from the anchor's own seed, and only where the row has a share: a model without one is untouched. The row's share is scaled
    // by the contract's `gapScale` (netted against the unquoted lead the twin already has: see the header), so a share that does not make up a
    // shortfall draws nothing.
    const gap = cell.gapShare ? cell.gapShare * gs : 0;
    if (gap > 0 && until > t && until % ANCHOR_MS === 0 && u() < gap) {
      const side: Side = (bB + bA) / 20 >= 50 ? 'ask' : 'bid', m = b[side], at = until - 1;
      for (const [p, size] of [...m.entries()].sort((x, y) => (side === 'bid' ? y[0] - x[0] : x[0] - y[0]))) out.push({ t: at, k: 'delta', ticker, side, price: p / PX, delta: -size, ts: at, sim: 1 });
      m.clear();
    }
    return out;
  }
}
