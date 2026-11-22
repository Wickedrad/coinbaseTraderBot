// Round R2 (Nov 22): the per-asset level calibration of the depth fill-in. Synthetic days only (tests/twinSweepSynth.ts): nothing here needs a recording.
//   - the model file's `calibration` block: schema 3, validated, refused when it cannot be read as it was meant;
//   - the resolution order of what a ticker is played with, and bit-identity without a calibration;
//   - the fixed point: one damped step, the clip, the recovery of known per-asset level offsets, determinism, the held-in check's budget.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CALIBRATION_CLIP, CALIBRATION_SCHEMA, DEFAULT_DEPTH_SIM_PARAMS, DepthSim, NEUTRAL_CALIBRATION, readDepthModel, resolveDepthSimParams, validateDepthModel, type AssetCalibration, type DepthModel } from '../research/history/depthSim';
import { DEPTH_MODEL_SCHEMA } from '../research/history/depthModelVersion';
import {
  calibrateDepthModel, CAL_DAMPING, CAL_MAX_ITER, CAL_MIN_LIVES, CAL_TOL_SD, gapsByAsset, gapsOfAsset, heldInCheck, heldInPasses, stepMults, withCalibration, type CalCols, type CalRow,
} from '../research/history/depthCalibrate';
import { FEATURES, filledDayRows } from '../research/historyTwin';
import { eventsHash, pinned, playAnchors, synthModel, synthRequoteDay } from './twinSweepSynth';
import { tmpDir } from './helpers';
import fs from 'fs';
import path from 'path';

const fi = (k: (typeof FEATURES)[number]) => FEATURES.indexOf(k);
const COLS: CalCols = { top: fi('topSize'), depth10: fi('depth10'), tradeSize: fi('tradeSize'), qchg: fi('quoteChangesPerMin'), trades: fi('tradesPerMin'), quotedShare: fi('quotedShare') };
const DAYS = ['2026-11-11', '2026-11-12'];
/** The synthetic model with the simulator's constants pinned in its own `params` block (tests/twinSweepSynth.ts `pinned`; layer 2 of the resolution order, and the
 *  calibration multiplies on top of it). WHY: the tests of the calibration's algorithm (the recovery of known offsets, the held-in check ...) play a synthetic day
 *  through the simulator, and how fast the quote-change rate answers to flickMult (and how the five knobs interact) depends on the shipped constants, so a promotion of a
 *  sweep's winners (RUNBOOK 9.5) would break them for a reason that is no bug. The one test that reads a shipped default on purpose (the resolution order) says so. */
const model3 = (days = DAYS): DepthModel => pinned({ ...synthModel({ days }), schema: DEPTH_MODEL_SCHEMA });
const requote = (days: string[], windows = 12) => new Map(days.map((d, i) => [d, synthRequoteDay({ day: d, assets: ['BTC', 'ETH'], windows, seed: 5 + i })]));
/** The twin's rows on the given FIT days, built in-stream as the stage builds them; `passes` counts the days played. */
function twinOf(req: Map<string, ReturnType<typeof synthRequoteDay>>) {
  const state = { days: 0, clock: 0, perDay: 0 };
  const rows = async (m: DepthModel, ds: readonly string[]): Promise<CalRow[]> => {
    const out: CalRow[] = [];
    for (const d of ds) { out.push(...(await filledDayRows(req.get(d)!, d, 'depth', new Map(), m, undefined, { diag: false })).rows); state.days++; state.clock += state.perDay; }
    return out;
  };
  return { rows, state };
}
const TRUTH: Record<string, AssetCalibration> = {
  BTC: { tradeRateMult: 1.5, tradeSizeMult: 1.6, topSizeMult: 1.3, levelSizeMult: 2.2, flickMult: 0.8 },
  ETH: { tradeRateMult: 0.7, tradeSizeMult: 0.6, topSizeMult: 0.8, levelSizeMult: 0.5, flickMult: 1.3 },
};
const KNOBS = Object.keys(NEUTRAL_CALIBRATION) as Array<keyof AssetCalibration>;

test('the model file: a calibration needs schema 3, its own block format, fit days, and every multiplier inside the clip range; an older reader refuses a newer file', () => {
  const base = model3(), cal = withCalibration(base, DAYS, 2, { BTC: { ...TRUTH.BTC } });
  assert.equal(DEPTH_MODEL_SCHEMA, 3);
  assert.doesNotThrow(() => validateDepthModel(cal));
  assert.equal(cal.schema, DEPTH_MODEL_SCHEMA);
  assert.deepEqual(cal.calibration!.byAsset.BTC, TRUTH.BTC);
  const c = cal.calibration!;
  assert.throws(() => validateDepthModel({ ...base, schema: 2, calibration: c }), /calibration block but schema 2 \(it needs schema 3/);
  assert.throws(() => validateDepthModel({ ...base, calibration: { ...c, schema: CALIBRATION_SCHEMA + 1 } }), /block format \d+ and this code reads format 1/);
  assert.throws(() => validateDepthModel({ ...base, calibration: { ...c, fitDays: [] } }), /does not record the days/);
  assert.throws(() => validateDepthModel({ ...base, calibration: { ...c, iterations: 1.5 } }), /whole number of iterations/);
  assert.throws(() => validateDepthModel({ ...base, calibration: { ...c, byAsset: { BTC: { ...TRUTH.BTC, flickMult: CALIBRATION_CLIP.hi + 0.01 } } } }), /calibration\.byAsset\.BTC\.flickMult must be a number from 0\.2 to 5/);
  assert.throws(() => validateDepthModel({ ...base, calibration: { ...c, byAsset: { BTC: { ...TRUTH.BTC, levelSizeMult: 0.19 } } } }), /levelSizeMult must be a number from 0\.2 to 5/);
  assert.throws(() => validateDepthModel({ ...base, calibration: { ...c, byAsset: { BTC: { ...TRUTH.BTC, topSizeMult: undefined as never } } } }), /topSizeMult must be a number/);
  assert.throws(() => validateDepthModel({ ...base, calibration: null as never }), /must be an object/);
  assert.throws(() => new DepthSim({ ...base, calibration: { ...c, byAsset: { BTC: { ...TRUTH.BTC, tradeRateMult: NaN } } } }), /tradeRateMult must be a number/);
  // an older reader (schema 2 code) refuses this file for its schema; this code refuses a schema newer than its own
  assert.throws(() => validateDepthModel({ ...base, schema: DEPTH_MODEL_SCHEMA + 1 }), /schema \d+ and this code reads up to schema 3/);
  // the file as written reads back, calibration and all
  const f = path.join(tmpDir(), 'm.json'); fs.writeFileSync(f, JSON.stringify(cal));
  assert.deepEqual(readDepthModel(f)!.calibration, cal.calibration);
  fs.writeFileSync(f, JSON.stringify({ ...cal, calibration: { ...c, byAsset: { BTC: { ...TRUTH.BTC, flickMult: 9 } } } }));
  assert.equal(readDepthModel(f), undefined, 'a file with a multiplier outside the clip does not read');
});

test('the block may carry the code it was fitted by (simulator hash, requote layer, feature code): a part left empty is refused, and the stamp moves no event', () => {
  const base = model3(), code = { sim: '0123456789abcdef', replay: '9', featureCode: 'f1' };
  const cal = withCalibration(base, DAYS, 2, { BTC: { ...TRUTH.BTC } }, undefined, code), bare = withCalibration(base, DAYS, 2, { BTC: { ...TRUTH.BTC } });
  assert.deepEqual(cal.calibration!.code, code); assert.equal(bare.calibration!.code, undefined, 'a block without a stamp is still a block the simulator reads');
  assert.doesNotThrow(() => validateDepthModel(cal)); assert.doesNotThrow(() => validateDepthModel(bare));
  for (const k of ['sim', 'replay', 'featureCode'] as const) assert.throws(() => validateDepthModel({ ...cal, calibration: { ...cal.calibration!, code: { ...code, [k]: '' } } }), new RegExp(`calibration code stamp must name the ${k}`));
  assert.throws(() => validateDepthModel({ ...cal, calibration: { ...cal.calibration!, code: null as never } }), /code stamp must name the sim/);
  const events = synthRequoteDay({ day: DAYS[0], assets: ['BTC', 'ETH'], windows: 3, seed: 7 });
  assert.equal(eventsHash(playAnchors(DepthSim as never, events, cal).out), eventsHash(playAnchors(DepthSim as never, events, bare).out), 'the stamp is a label: the stream is the same');
  // the stage's calibration writes the stamp it is given
  const f = path.join(tmpDir(), 'm.json'); fs.writeFileSync(f, JSON.stringify(cal)); assert.deepEqual(readDepthModel(f)!.calibration!.code, code);
});

test('what a ticker is played with: the defaults, then the model\'s params, then the calibration of ITS asset multiplied on, then the caller\'s params; no asset block, no change', () => {
  const base = model3();
  const model: DepthModel = withCalibration({ ...base, params: { levelSizeMult: 2, tradeRateMult: 1.5, capMult: 6 } }, DAYS, 3, { BTC: { tradeRateMult: 3, tradeSizeMult: 2, topSizeMult: 1.7, levelSizeMult: 0.5, flickMult: 0.4 } });
  const btc = 'KXBTC15M-26NOV11-00', eth = 'KXETH15M-26NOV11-00', sol = 'KXSOL15M-26NOV11-00';
  // no caller: layers 1 to 3
  const a = new DepthSim(model), pb = a.paramsFor(btc);
  // tradeSizeMult is not in the params block, so it is layer 1 (whatever the shipped default is: a promotion changes it) times the calibration's 2
  assert.deepEqual([pb.params.levelSizeMult, pb.params.tradeRateMult, pb.params.tradeSizeMult, pb.params.capMult, pb.topSizeMult, pb.flickMult, pb.asset], [1, 4.5, DEFAULT_DEPTH_SIM_PARAMS.tradeSizeMult * 2, 6, 1.7, 0.4, 'BTC'], 'defaults < params block (x2, x1.5, cap 6) < calibration multiplied on (x0.5, x3, x2)');
  // an asset the calibration has no block for, or no asset at all: layers 1 and 2 only, exactly `params`
  for (const t of [eth, sol, 'KXDOGE15M-26NOV11-00', 'WEIRD']) { const p = a.paramsFor(t); assert.equal(p.params, a.params, t); assert.deepEqual([p.topSizeMult, p.flickMult, p.asset], [1, 1, undefined]); }
  assert.equal(a.params.levelSizeMult, 2); assert.equal(a.params.tradeRateMult, 1.5);
  // the caller's params are the last layer: a key it names REPLACES what the layers before gave that knob (for the calibrated asset only where it was calibrated), the rest keeps its calibration
  const b = new DepthSim(model, { tradeSizeMult: 3, levelSizeMult: 0.9 }), pc = b.paramsFor(btc), pe = b.paramsFor(eth);
  assert.deepEqual([pc.params.tradeSizeMult, pc.params.levelSizeMult, pc.params.tradeRateMult, pc.topSizeMult, pc.flickMult], [3, 0.9, 4.5, 1.7, 0.4]);
  assert.deepEqual([pe.params.tradeSizeMult, pe.params.levelSizeMult, pe.params.tradeRateMult], [3, 0.9, 1.5], 'an uncalibrated ticker: defaults < params block < caller');
  assert.deepEqual(b.params, resolveDepthSimParams(model.params, { tradeSizeMult: 3, levelSizeMult: 0.9 }), 'the sim-wide params are the old resolution (no calibration)');
  // the resolution is constant per ticker (no time or quote in it) and stable across calls
  assert.equal(b.paramsFor(btc), pc);
  // a caller's unknown knob is still refused, and the calibrated product must stay above 0
  assert.throws(() => new DepthSim(model, { topSizeMult: 2 } as never), /unknown depth simulator parameter "topSizeMult"/);
});

test('a model WITHOUT a calibration, a neutral one, and one for an asset the day does not have play the same event stream bit for bit; a calibration for one asset changes that asset only', () => {
  const days = ['2026-11-11'], model = model3(days);
  const events = synthRequoteDay({ day: days[0], assets: ['BTC', 'ETH'], windows: 3, seed: 7 });
  const hash = (m: DepthModel, asset?: string) => eventsHash(playAnchors(DepthSim as never, events, m).out.filter((e) => !asset || String(e.ticker).startsWith(`KX${asset}`)));
  const base = hash(model);
  assert.equal(hash(withCalibration(model, days, 0, { BTC: { ...NEUTRAL_CALIBRATION }, ETH: { ...NEUTRAL_CALIBRATION } })), base, 'neutral multipliers');
  assert.equal(hash(withCalibration(model, days, 1, { SOL: { ...TRUTH.BTC } })), base, 'a calibration of an asset that has no contract on the day');
  assert.equal(hash({ ...model, schema: 2 }), base, 'the same model written as schema 2');
  const btcOnly = withCalibration(model, days, 1, { BTC: { ...TRUTH.BTC } });
  assert.notEqual(hash(btcOnly, 'BTC'), hash(model, 'BTC'), 'BTC is played with its multipliers');
  assert.equal(hash(btcOnly, 'ETH'), hash(model, 'ETH'), 'ETH, with no block, is played exactly as before');
  // each knob moves the stream (none is dead code) and a calibrated stream replays the same
  for (const k of KNOBS) assert.notEqual(hash(withCalibration(model, days, 1, { BTC: { ...NEUTRAL_CALIBRATION, [k]: 1.8 } }), 'BTC'), hash(model, 'BTC'), `${k} acts`);
  assert.equal(hash(btcOnly), hash(btcOnly), 'deterministic');
});

test('one damped step: log mult += damping x the log gap, the best level takes what the level step left, and every multiplier is clipped to [0.2, 5]', () => {
  const n = { ...NEUTRAL_CALIBRATION }, L = Math.log;
  const s = stepMults(n, { top: L(2), depth10: L(2), tradeSize: L(1.5), qchg: L(0.5), trades: L(3) });
  const r4 = (x: number) => +x.toFixed(4);
  assert.equal(CAL_DAMPING, 0.8);
  assert.equal(s.levelSizeMult, r4(2 ** 0.8)); assert.equal(s.tradeSizeMult, r4(1.5 ** 0.8)); assert.equal(s.flickMult, r4(0.5 ** 0.8)); assert.equal(s.tradeRateMult, r4(3 ** 0.8));
  assert.equal(s.topSizeMult, 1, 'the best level\'s gap is the level\'s: nothing left for its own multiplier');
  const t = stepMults(n, { top: L(4), depth10: L(2), tradeSize: 0, qchg: 0, trades: 0 });
  assert.equal(t.topSizeMult, r4(Math.exp(0.8 * L(4) - 0.8 * L(2))), 'only the part of the best level\'s gap the level step did not cover');
  // the clip: a gap of 100x goes to the top of the range, 1/100x to the bottom; and a multiplier already at the end stays there
  const hi = stepMults(n, { top: L(100), depth10: L(100), tradeSize: L(100), qchg: L(100), trades: L(100) }), lo = stepMults(n, { top: L(0.01), depth10: L(0.01), tradeSize: L(0.01), qchg: L(0.01), trades: L(0.01) });
  for (const k of ['levelSizeMult', 'tradeSizeMult', 'flickMult', 'tradeRateMult'] as const) { assert.equal(hi[k], CALIBRATION_CLIP.hi, `${k} up`); assert.equal(lo[k], CALIBRATION_CLIP.lo, `${k} down`); }
  assert.ok(hi.topSizeMult >= CALIBRATION_CLIP.lo && hi.topSizeMult <= CALIBRATION_CLIP.hi && lo.topSizeMult >= CALIBRATION_CLIP.lo && lo.topSizeMult <= CALIBRATION_CLIP.hi);
  assert.deepEqual(stepMults(hi, { top: L(100), depth10: L(100), tradeSize: L(100), qchg: L(100), trades: L(100) }).levelSizeMult, CALIBRATION_CLIP.hi);
  assert.deepEqual([CALIBRATION_CLIP.lo, CALIBRATION_CLIP.hi, CAL_MAX_ITER, CAL_TOL_SD, CAL_MIN_LIVES], [0.2, 5, 5, 0.1, 20], 'the algorithm settings, written down');
});

test('the gaps: twin mean minus real mean in the real within-asset sd, per asset, from the rows\' own columns', () => {
  const row = (ticker: string, v: number[]): CalRow => ({ ticker, f: v });
  const real = [row('KXBTC15M-A', [1, 10]), row('KXBTC15M-B', [3, 10]), row('KXETH15M-A', [5, 0]), row('KXETH15M-B', [7, 4]), row('KXDOGE15M-A', [99, 99])];
  const twin = [row('KXBTC15M-A', [2, 10]), row('KXBTC15M-B', [4, 10]), row('KXETH15M-A', [7, 0]), row('KXETH15M-B', [9, 4]), row('KXDOGE15M-A', [0, 0])];
  const g = gapsByAsset(real, twin, { a: 0, b: 1 });
  assert.deepEqual(Object.keys(g), ['BTC', 'ETH'], 'only the four assets; DOGE is not one');
  assert.deepEqual([g.BTC.gaps.a, g.ETH.gaps.a], [1, 2], 'BTC: twin 1 above real, real sd 1: 1 sd; ETH: twin 2 above, real sd 1: 2 sd');
  assert.deepEqual([g.BTC.gaps.b, g.ETH.gaps.b], [0, 0], 'no gap');
  assert.equal(gapsOfAsset([row('KXBTC15M-A', [0, 10]), row('KXBTC15M-B', [0, 10])], [row('KXBTC15M-A', [0, 12]), row('KXBTC15M-B', [0, 12])], { b: 1 }).gaps.b, 2, 'a feature with no spread in the real rows is read in units of 1');
  assert.ok(Number.isNaN(gapsOfAsset(real, [], { a: 0 }).gaps.a), 'no twin rows: no gap, never a 0');
});

test('two assets with known level offsets are recovered from neutral, within 10 percent, and the residual gaps are small; the same input gives the same answer', async () => {
  const model = model3(), req = requote(DAYS), tw = twinOf(req);
  const real = await tw.rows(withCalibration(model, DAYS, 0, TRUTH), DAYS);
  assert.ok(real.length >= 48);
  const run = async () => { const lines: string[] = []; const r = await calibrateDepthModel({ model, fitDays: DAYS, realRows: real, twinRows: tw.rows, cols: COLS, log: (l) => lines.push(l) }); return { r, lines }; };
  const { r, lines } = await run();
  for (const a of ['BTC', 'ETH']) for (const k of KNOBS) {
    const got = r.calibration.byAsset[a][k], want = TRUTH[a][k];
    assert.ok(Math.abs(got / want - 1) <= 0.1, `${a} ${k}: ${got} against ${want}`);
  }
  // the residual: every calibrated feature within 0.3 sd (the loop stops at 0.1 or K), and it is what the final line says
  for (const a of ['BTC', 'ETH']) for (const f of ['top', 'depth10', 'tradeSize', 'qchg', 'trades']) assert.ok(Math.abs(r.residual[a][f]) < 0.3, `${a} ${f} residual ${r.residual[a][f]}`);
  assert.equal(r.calibration.schema, CALIBRATION_SCHEMA); assert.deepEqual(r.calibration.fitDays, DAYS); assert.ok(r.calibration.iterations >= 2 && r.calibration.iterations <= CAL_MAX_ITER);
  assert.deepEqual(r.model.calibration, r.calibration); assert.equal(r.model.schema, DEPTH_MODEL_SCHEMA); assert.doesNotThrow(() => validateDepthModel(r.model));
  // the first iteration is the uncalibrated twin, far from the real days; the last is close
  const first = r.trace.find((t) => t.asset === 'BTC' && t.iter === 1)!, last = r.trace.filter((t) => t.asset === 'BTC').pop()!;
  assert.deepEqual(first.mults, NEUTRAL_CALIBRATION);
  assert.ok(Math.abs(first.gaps.depth10) > 0.4 && Math.abs(last.gaps.depth10) < 0.1, `${first.gaps.depth10} -> ${last.gaps.depth10}`);
  // the lines: one per iteration and asset in the shape the brief gives, a final line per asset and a summary; numbers only
  const it = lines.filter((l) => /^\[twin\] calibration: asset \w+ iter \d+:/.test(l));
  assert.ok(it.length >= 4);
  for (const l of it) assert.match(l, /^\[twin\] calibration: asset (BTC|ETH) iter \d: gaps \(sd\) top -?[\d.]+ depth10 -?[\d.]+ tradeSize -?[\d.]+ qchg -?[\d.]+ trades -?[\d.]+; mults top [\d.]+ level [\d.]+ size [\d.]+ trades [\d.]+ flick [\d.]+$/);
  assert.equal(lines.filter((l) => /^\[twin\] calibration: asset \w+ final /.test(l)).length, 2);
  assert.match(lines.find((l) => /final/.test(l))!, /residual gaps \(sd\) top .* trades -?[\d.]+; quotedShare -?[\d.]+ \(not calibrated\); mults top .*; lives real \d+ twin \d+$/);
  assert.match(lines[lines.length - 1], /^\[twin\] calibration: fitted on the FIT days 2026-11-11 2026-11-12: 2 asset\(s\), \d iteration\(s\) of at most 5 \(damping 0.8, clip 0.2..5, stop under 0.1 sd: algorithm settings\); largest residual gap [\d.]+ sd \(\w+\); (converged|not converged)$/);
  assert.ok(lines.every((l) => /^\[twin\] calibration: /.test(l)) && lines.every((l) => !/KX|2026-11-1\d-/.test(l.replace(/FIT days [\d -]+/, ''))), 'no ticker or recording line');
  // determinism: the same rows in, the same block and the same lines out
  const again = await run();
  assert.deepEqual(again.r.calibration, r.calibration); assert.deepEqual(again.lines, lines);
});

test('the code stamp given to the calibration is the one in the block it returns (and none given, none stamped)', async () => {
  const model = model3(), req = requote(DAYS, 4), tw = twinOf(req), code = { sim: 'abcdef0123456789', replay: '9', featureCode: 'f1' };
  const real = await tw.rows(model, DAYS);
  const stamped = await calibrateDepthModel({ model, fitDays: DAYS, realRows: real, twinRows: tw.rows, cols: COLS, minLives: 8, code }), plain = await calibrateDepthModel({ model, fitDays: DAYS, realRows: real, twinRows: tw.rows, cols: COLS, minLives: 8 });
  assert.deepEqual(stamped.calibration.code, code); assert.deepEqual(stamped.model.calibration!.code, code); assert.equal(plain.calibration.code, undefined);
  assert.deepEqual({ ...stamped.calibration, code: undefined }, { ...plain.calibration, code: undefined }, 'the stamp changes nothing else');
});

test('a neutral twin is left alone: when the twin already meets the real days the loop stops at once and the block is all 1', async () => {
  const model = model3(), req = requote(DAYS), tw = twinOf(req);
  const real = await tw.rows(model, DAYS);
  const r = await calibrateDepthModel({ model, fitDays: DAYS, realRows: real, twinRows: tw.rows, cols: COLS });
  assert.equal(r.iterations, 1); assert.ok(r.converged);
  for (const a of ['BTC', 'ETH']) assert.deepEqual(r.calibration.byAsset[a], NEUTRAL_CALIBRATION);
});

test('an asset with too few lives is not calibrated and plays as measured; with none to calibrate, and with days that are not the model\'s, the calibration refuses', async () => {
  const model = model3(), req = requote(DAYS, 4), tw = twinOf(req);
  const real = await tw.rows(withCalibration(model, DAYS, 0, TRUTH), DAYS);
  assert.ok(real.length < 40);
  await assert.rejects(calibrateDepthModel({ model, fitDays: DAYS, realRows: real, twinRows: tw.rows, cols: COLS }), /no asset has the lives to calibrate \(BTC: 8 real lives \(at least 20 needed\); ETH: 8 real lives/);
  const lines: string[] = [], r = await calibrateDepthModel({ model, fitDays: DAYS, realRows: real, twinRows: tw.rows, cols: COLS, minLives: 8, log: (l) => lines.push(l) });
  assert.deepEqual(Object.keys(r.calibration.byAsset).sort(), ['BTC', 'ETH']);
  const twinBtcOnly = async (m: DepthModel, ds: readonly string[]) => (await tw.rows(m, ds)).filter((x) => x.ticker.startsWith('KXBTC'));
  const one = await calibrateDepthModel({ model, fitDays: DAYS, realRows: real, twinRows: twinBtcOnly, cols: COLS, minLives: 8, log: (l) => lines.push(l) });
  assert.deepEqual(Object.keys(one.calibration.byAsset), ['BTC']); assert.deepEqual(Object.keys(one.skipped), ['ETH']);
  assert.ok(lines.some((l) => /asset ETH not calibrated \(0 twin lives \(at least 8 needed\)\); it plays as measured$/.test(l)));
  // days the model was not fitted on, and real rows of another day: refused before anything is played
  await assert.rejects(calibrateDepthModel({ model, fitDays: [...DAYS, '2026-11-13'], realRows: real, twinRows: tw.rows, cols: COLS }), /reads only the days the depth model was fitted on \(2026-11-11, 2026-11-12\): 2026-11-13 is not among them/);
  await assert.rejects(calibrateDepthModel({ model, fitDays: DAYS, realRows: [...real, { ticker: 'KXBTC15M-X', day: '2026-11-13', f: [] }], twinRows: tw.rows, cols: COLS }), /real rows hold day\(s\) that are not fit days: 2026-11-13/);
  await assert.rejects(calibrateDepthModel({ model, fitDays: [], realRows: real, twinRows: tw.rows, cols: COLS }), /no fit days/);
});

test('the held-in check leaves each FIT day out in turn, prices itself before it runs, and is skipped when it would cost more than its budget', async () => {
  const days = ['2026-11-11', '2026-11-12', '2026-11-15'], model = model3(days), req = requote(days), tw = twinOf(req);
  const real = await tw.rows(withCalibration(model, days, 0, TRUTH), days);
  tw.state.days = 0;
  const lines: string[] = [];
  const input = (budget: number) => ({ model, fitDays: days, realRows: real, twinRows: tw.rows, cols: COLS, log: (l: string) => lines.push(l), now: () => tw.state.clock, heldInBudgetS: budget });
  tw.state.perDay = 10; // a day's pass takes 10 s of the fake clock
  const fit = await calibrateDepthModel(input(180));
  assert.equal(fit.secPerDayPass, 10);
  assert.equal(heldInPasses(3, 1), 3); assert.equal(heldInPasses(3, 2), 9); assert.equal(heldInPasses(7, 1), 7); assert.equal(heldInPasses(7, 2), 49);
  // a budget of 100 s buys the 2-iteration version (9 passes = 90 s), 50 s only the 1-iteration one (3 passes), 20 s none
  for (const [budget, k] of [[100, 2], [50, 1]] as const) {
    lines.length = 0; tw.state.days = 0;
    const h = await heldInCheck(input(budget), fit);
    assert.ok(h.ran); assert.equal(h.iterations, k); assert.equal(h.passes, heldInPasses(3, k)); assert.equal(tw.state.days, heldInPasses(3, k), 'it plays exactly the passes it priced (the neutral rows of the main fit are not played again)');
    assert.deepEqual(h.folds.map((f) => f.day), days);
    assert.equal(lines.filter((l) => /^\[twin\] calibration: held-in 2026-11-\d\d asset (BTC|ETH) /.test(l)).length, 6, '3 days, 2 assets');
    assert.match(lines[lines.length - 1], new RegExp(`^\\[twin\\] calibration: held-in check \\(3 folds, ${k} iteration\\(s\\) each, ${heldInPasses(3, k)} day passes\\): mean \\|gap\\| over assets, days and the 6 features, uncalibrated [\\d.]+ sd, calibrated on the other days [\\d.]+ sd \\(report only\\)$`));
    assert.ok(h.meanAfter < h.meanBefore, `the calibration carries to the day left out: ${h.meanBefore} -> ${h.meanAfter}`);
  }
  lines.length = 0; tw.state.days = 0;
  const skipped = await heldInCheck(input(20), fit);
  assert.equal(skipped.ran, false); assert.equal(tw.state.days, 0, 'a skipped check plays nothing'); assert.match(lines[0], /^\[twin\] calibration: held-in check skipped: about 30 s for the cheapest version \(3 day passes at 10 s\) against a budget of 20 s$/);
  assert.equal((await heldInCheck(input(0), fit)).ran, false);
  assert.match((await heldInCheck({ ...input(100), fitDays: [days[0]] }, fit)).note!, /1 fit day\(s\): leaving one out needs at least 2/);
});
