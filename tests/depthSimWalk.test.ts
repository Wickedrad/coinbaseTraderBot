import assert from 'node:assert/strict';
import fs from 'fs';
import path from 'path';
import { spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { test } from 'node:test';
import {
  DEFAULT_DEPTH_SIM_PARAMS, DEPTH_PARAM_NAMES, DEPTH_PARAM_SPACE, DepthSim, readDepthModel, resolveDepthSimParams, type DepthModel, type DepthSimParams,
} from '../research/history/depthSim';
import { fillQuotes, depthSims } from '../research/goLiveTally';
import { eventsHash, playAnchors, synthModel, synthRequoteDay } from './twinSweepSynth';
import { tmpDir } from './helpers';

const MIN = 60_000;
const q = { n: 1, mean: 0, p10: 1, p50: 1, p90: 2 };
// A book with ten quoted levels of 100 a side, no other flow: only the walk to the next quote trades.
const model: DepthModel = {
  days: ['x'],
  shape: [{ ti: 0, mi: 0, samples: 1, levelQuoted: Array(10).fill(1), levelFilledP50: Array(10).fill(100), levelFilledP90: Array(10).fill(100), tradesPerMin: q, tradeSize: q, takerYesShare: 0.5 }],
  flow: [],
};

test('a quote that moves down takes the bids it moved through at its own time, with NO takers, and nothing before it', () => {
  const sim = new DepthSim(model);
  const t = 1_000_000 * MIN;
  const first = sim.play('T', t, 0.5, 0.52, t + 15_000, t + 30 * MIN, 0.47);
  // No trades ahead of the move: the next quote is not known to the book before its time.
  assert.equal(first.filter((e) => e.k === 'trade').length, 0);
  const ev = sim.play('T', t + 15_000, 0.47, 0.49, t + 30_000, t + 30 * MIN);
  const trades = ev.filter((e) => e.k === 'trade');
  // From bid 50c to 47c: the bids at 50, 49 and 48c go, each with a few trade-sized prints (at most sweepPrints, 3 in the base
  // commit; read from the defaults so a promotion of a sweep's winners does not break the mechanism), the rest pulled,
  // all at the new quote's time and before its book.
  const prices = trades.map((e) => Math.round((e.price as number) * 100));
  assert.deepEqual([...new Set(prices)], [50, 49, 48]);
  assert.ok(trades.length >= 3 && trades.length <= 3 * DEFAULT_DEPTH_SIM_PARAMS.sweepPrints);
  assert.ok(trades.every((e) => e.takerSide === 'no' && e.t === t + 15_000));
  assert.ok(ev.findIndex((e) => e.k === 'book') > ev.findIndex((e) => e.k === 'trade'));
  // A flat quote takes nothing.
  const flat = new DepthSim(model);
  flat.play('U', t, 0.5, 0.52, t + 15_000, t + 30 * MIN);
  assert.equal(flat.play('U', t + 15_000, 0.5, 0.52, t + 30_000, t + 30 * MIN).filter((e) => e.k === 'trade').length, 0);
});

test('the trades before a quote do not know where the next quote goes', () => {
  const busy: DepthModel = { ...model, shape: [{ ...model.shape[0], tradesPerMin: { n: 1, mean: 60, p10: 60, p50: 60, p90: 60 } }], informed: { n: 5000, agree: 1 } };
  const t = 1_000_000 * MIN;
  const down = new DepthSim(busy).play('V', t, 0.5, 0.52, t + MIN, t + 30 * MIN, 0.3);
  const up = new DepthSim(busy).play('V', t, 0.5, 0.52, t + MIN, t + 30 * MIN, 0.7);
  assert.deepEqual(down, up);
  assert.ok(down.filter((e) => e.k === 'trade').length > 20);
});

test('sizes go back to the measured shape and the best price flickers at the measured rate', () => {
  const t = 1_000_000 * MIN;
  // Adds far outpacing cancels at the top used to drift the queue up to the cap; the pull keeps it near its draw.
  const flow = [0, 1, 2, 3, 4, 5].map((qi) => ({ offset: 0, qi, seconds: 1000, addPerSec: 2, cancelPerSec: 0.1, addSize: { n: 1, mean: 50, p10: 50, p50: 50, p90: 50 }, cancelSize: q }));
  const busy: DepthModel = { ...model, shape: [{ ...model.shape[0], topChangesPerMin: { n: 1, mean: 300, p10: 300, p50: 300, p90: 300 } }], flow };
  const sim = new DepthSim(busy);
  const ev = sim.play('W', t, 0.5, 0.52, t + 15_000, t + 30 * MIN, 0.51);
  const top = new Map<number, number>();
  for (const e of ev) if (e.k === 'book') for (const l of e.bids as Array<{ price: number; size: number }>) top.set(Math.round(l.price * 1000), l.size);
  else if (e.k === 'delta' && e.side === 'bid') { const p = Math.round((e.price as number) * 1000); top.set(p, (top.get(p) ?? 0) + (e.delta as number)); }
  assert.ok((top.get(500) ?? 0) < 400, `top bid ${top.get(500)}`);
  // ~(300/60 - 0.9)/2 = 2 flickers a second over 15 s.
  assert.ok(sim.stats.flickers >= 15 && sim.stats.flickers <= 50, `flickers ${sim.stats.flickers}`);
});

// ---------------------------------------------------------------------------------------------------------------
// The tuning constants as one object (Nov 22): defaults = the hand constants, merge, bounds, and the golden parity with the
// commit before the object existed.

const ROOT = process.cwd();
/** The commit the parameter object was made on top of: its research/history/depthSim.ts is the reference for bit-identity. */
const BASE_COMMIT = 'dfaa030';

/** The hand constants of the BASE commit (dfaa030), spelled out. FIXED FOREVER: it is what the base commit's file ran with, whatever
 *  DEFAULT_DEPTH_SIM_PARAMS becomes. The parity tests below pass it to the parameterised code explicitly, so they keep proving "the
 *  parameterised code is the base code" after a sweep's winners are promoted to the defaults. Do NOT edit it when promoting (RUNBOOK 9.5). */
const BASE_PARAMS = Object.freeze({
  revertS: 10, revertTopS: 1, stepSd: 0.1, flickBasePerSec: 2.6, sweepPrints: 3, withinSd: 0.7, activitySd: 0.6, capMult: 4, flickBackMinMs: 20, flickBackSpanMs: 180,
  tradeRateMult: 1, tradeSizeMult: 1, levelSizeMult: 1,
}) as DepthSimParams;

/** The defaults the code ships TODAY, spelled out (a pin, not a derivation). A promotion of a sweep's winners edits this literal and
 *  GOLDEN_CURRENT below, and nothing else in the tests (RUNBOOK 9.5). Today they are the base commit's constants. */
const CURRENT_DEFAULTS: DepthSimParams = {
  revertS: 10, revertTopS: 1, stepSd: 0.1, flickBasePerSec: 2.6, sweepPrints: 3, withinSd: 0.7, activitySd: 0.6, capMult: 4, flickBackMinMs: 20, flickBackSpanMs: 180,
  tradeRateMult: 1, tradeSizeMult: 1, levelSizeMult: 1,
};

test('the base constants are the hand constants the fill-in ran with, and the parameter space holds every one of them and every default', () => {
  // adding a parameter means adding its neutral value to BASE_PARAMS, on purpose: the parity tests run the base file's behaviour through it
  assert.deepEqual(Object.keys(BASE_PARAMS).sort(), [...DEPTH_PARAM_NAMES].sort(), 'BASE_PARAMS names every parameter');
  assert.deepEqual(Object.keys(DEPTH_PARAM_SPACE).sort(), [...DEPTH_PARAM_NAMES].sort(), 'a bound for every parameter, and no other');
  for (const n of DEPTH_PARAM_NAMES) {
    const b = DEPTH_PARAM_SPACE[n], d = DEFAULT_DEPTH_SIM_PARAMS[n];
    assert.ok(b.lo < b.hi, `${n}: lo below hi`);
    assert.ok(d >= b.lo && d <= b.hi, `${n}: the default ${d} is inside [${b.lo}, ${b.hi}]`);
    assert.ok(BASE_PARAMS[n] >= b.lo && BASE_PARAMS[n] <= b.hi, `${n}: the base constant ${BASE_PARAMS[n]} is inside [${b.lo}, ${b.hi}]`);
    assert.ok(b.scale === 'linear' || b.lo > 0, `${n}: a log scale needs a positive lower bound`);
    assert.ok(b.note.length > 10, `${n}: says what it is`);
  }
  assert.deepEqual(DEPTH_PARAM_NAMES.filter((n) => DEPTH_PARAM_SPACE[n].int), ['sweepPrints']);
  // the defaults object cannot be edited in place by a sweep (promoting winners is a reviewed code change)
  assert.throws(() => { (DEFAULT_DEPTH_SIM_PARAMS as DepthSimParams).revertS = 99; }, TypeError);
  assert.throws(() => { (BASE_PARAMS as DepthSimParams).revertS = 99; }, TypeError);
  // the look-ahead switch is not a parameter, and no parameter name can switch it on
  assert.ok(!DEPTH_PARAM_NAMES.some((n) => /next|ahead|informed/i.test(n)));
});

test('the shipped defaults, exact: this literal is one of the two things a promotion edits (with GOLDEN_CURRENT)', () => {
  assert.deepEqual({ ...DEFAULT_DEPTH_SIM_PARAMS }, CURRENT_DEFAULTS);
});

test('params merge over the defaults, the model\'s own block under the caller\'s, and bad ones are refused', () => {
  assert.deepEqual(resolveDepthSimParams(), { ...DEFAULT_DEPTH_SIM_PARAMS });
  assert.deepEqual(resolveDepthSimParams({ revertS: 20 }), { ...DEFAULT_DEPTH_SIM_PARAMS, revertS: 20 });
  assert.equal(resolveDepthSimParams({ revertS: 20, stepSd: 0.2 }, { revertS: 30 }).revertS, 30, 'the later layer wins');
  assert.equal(resolveDepthSimParams({ revertS: 20, stepSd: 0.2 }, { revertS: 30 }).stepSd, 0.2, 'what it does not name stays');
  assert.equal(resolveDepthSimParams({ revertS: undefined }).revertS, DEFAULT_DEPTH_SIM_PARAMS.revertS, 'an undefined is not a value');
  assert.equal(resolveDepthSimParams({ sweepPrints: 2.6 }).sweepPrints, 3, 'the integer parameter is rounded');
  assert.equal(resolveDepthSimParams({ sweepPrints: 4.4 }).sweepPrints, 4, 'to the nearest whole number, whatever the default is');
  assert.throws(() => resolveDepthSimParams({ reverts: 3 } as never), /unknown depth simulator parameter "reverts"/);
  assert.throws(() => resolveDepthSimParams({ revertS: Number.NaN }), /revertS must be a finite number/);
  assert.throws(() => resolveDepthSimParams({ stepSd: -0.1 }), /stepSd must be a finite number of at least 0/);
  assert.throws(() => resolveDepthSimParams({ revertS: '10' as never }), /revertS/);
  assert.throws(() => resolveDepthSimParams({ revertS: 0 }), /revertS must be above 0/);
  assert.throws(() => resolveDepthSimParams({ tradeRateMult: 0 }), /tradeRateMult must be above 0/);
  // DepthSim: defaults < model.params < constructor params
  const m = synthModel();
  assert.deepEqual(new DepthSim(m).params, { ...DEFAULT_DEPTH_SIM_PARAMS });
  const withBlock: DepthModel = { ...m, params: { revertS: 25, stepSd: 0.3 } };
  assert.equal(new DepthSim(withBlock).params.revertS, 25);
  assert.equal(new DepthSim(withBlock, { revertS: 5 }).params.revertS, 5);
  assert.equal(new DepthSim(withBlock, { revertS: 5 }).params.stepSd, 0.3);
  assert.throws(() => new DepthSim({ ...m, params: { nope: 1 } as never }), /unknown depth simulator parameter/);
});

test('readDepthModel keeps working on old model files and carries a params block when there is one', () => {
  const old = readDepthModel(path.join(ROOT, 'tests/fixtures/depth_model.json'));
  assert.ok(old && old.params === undefined && old.shape.length > 0, 'the checked-in model has no params block and still reads');
  assert.deepEqual(new DepthSim(old!).params, { ...DEFAULT_DEPTH_SIM_PARAMS });
  const f = path.join(tmpDir(), 'depth_model.json');
  fs.writeFileSync(f, JSON.stringify({ ...synthModel(), params: { revertS: 17, tradeRateMult: 1.2 } }));
  const m = readDepthModel(f);
  assert.deepEqual(m?.params, { revertS: 17, tradeRateMult: 1.2 });
  assert.equal(new DepthSim(m!).params.revertS, 17);
  assert.equal(new DepthSim(m!).params.stepSd, DEFAULT_DEPTH_SIM_PARAMS.stepSd);
});

// The golden hashes were computed from the BASE commit's depthSim.ts and goLiveTally.ts (a checkout of dfaa030, the same
// synthetic day, `eventsHash`), before the parameter object existed. A: the whole fill-in (fillQuotes, depth) of the day; B:
// DepthSim.play called quote by quote. Both are 8 contracts of 15 minutes with sweeps, flickers, trades and the tails.
// FIXED FOREVER: they are the base commit's output, and the tests that hold them pass BASE_PARAMS explicitly, so they do not move
// when the defaults are promoted.
const GOLDEN_BASE = {
  A: { hash: '648afeb0204f2a090499f23d4525d5a94aa9feec1c7c4edf6a6d146021a2bb36', events: 160007, stats: { seconds: 7208, trades: 14947, sweepPrints: 6793, flickers: 8614 } },
  B: { hash: 'c2faebc4a52aa14fac8f05e0a170bf1705ca1c9368d5ebac9c4dbc5f8f2c91ae', events: 161789, stats: { seconds: 7320, trades: 15130, sweepPrints: 6793, flickers: 8729 } },
};
/** The same day through the fill-in with the defaults the code ships TODAY (no params passed). Today it is GOLDEN_BASE.A; after a
 *  promotion of a sweep's winners it is the only hash that changes (RUNBOOK 9.5: recompute it, say so in the commit message). */
const GOLDEN_CURRENT = { hash: '648afeb0204f2a090499f23d4525d5a94aa9feec1c7c4edf6a6d146021a2bb36', events: 160007, stats: { seconds: 7208, trades: 14947, sweepPrints: 6793, flickers: 8614 } };
const goldenDay = () => synthRequoteDay({ day: '2026-11-11' });
const goldenModel = () => synthModel({ trades: 90, topChanges: 300 });
/** DepthSim with the base commit's constants given explicitly. */
class BaseConstantsSim extends DepthSim { constructor(m: DepthModel) { super(m, BASE_PARAMS); } }

test('run with the base commit\'s constants the parameterised fill-in is bit-identical to the base commit: the golden hash of a fixed synthetic requote day', () => {
  const events = goldenDay(), model = goldenModel();
  const before = depthSims.length;
  const a = fillQuotes(events, { how: 'depth' }, model, BASE_PARAMS);
  const sim = depthSims[before];
  assert.equal(a.length, GOLDEN_BASE.A.events);
  assert.deepEqual(sim.stats, GOLDEN_BASE.A.stats, 'the same activity, to the print');
  assert.equal(eventsHash(a), GOLDEN_BASE.A.hash, 'every record of the whole fill-in, number by number');
  // every path of the simulator is on it: sweeps, flickers, trades, the tails (below 10 and above 90 cents), the cap
  assert.ok(sim.stats.sweepPrints > 1000 && sim.stats.flickers > 1000 && sim.stats.trades > 1000);
  assert.ok(a.some((e) => e.k === 'book' && (e.bids as Array<{ price: number }>).some((l) => l.price < 0.1)) && a.some((e) => e.k === 'book' && (e.asks as Array<{ price: number }>).some((l) => l.price > 0.9)), 'quotes in both tails');
  const b = playAnchors(BaseConstantsSim as never, events, model);
  assert.equal(b.out.length, GOLDEN_BASE.B.events);
  assert.deepEqual(b.stats, GOLDEN_BASE.B.stats);
  assert.equal(eventsHash(b.out), GOLDEN_BASE.B.hash);
  // the base constants win over a model's own params block and over nothing at all: they are a full set
  assert.equal(eventsHash(fillQuotes(events, { how: 'depth' }, { ...model, params: { revertS: 40, tradeRateMult: 2 } }, BASE_PARAMS)), GOLDEN_BASE.A.hash);
});

test('the fill-in with the shipped defaults: its golden hash and activity (one of the two things a promotion edits, with CURRENT_DEFAULTS)', () => {
  const events = goldenDay(), model = goldenModel();
  const before = depthSims.length;
  const a = fillQuotes(events, { how: 'depth' }, model);
  const sim = depthSims[before];
  assert.equal(a.length, GOLDEN_CURRENT.events);
  assert.deepEqual(sim.stats, GOLDEN_CURRENT.stats);
  assert.equal(eventsHash(a), GOLDEN_CURRENT.hash);
  // explicit defaults, and the defaults as a model's own block, are the defaults
  assert.equal(eventsHash(fillQuotes(events, { how: 'depth' }, model, { ...DEFAULT_DEPTH_SIM_PARAMS })), GOLDEN_CURRENT.hash);
  assert.equal(eventsHash(fillQuotes(events, { how: 'depth' }, { ...model, params: { ...DEFAULT_DEPTH_SIM_PARAMS } })), GOLDEN_CURRENT.hash);
  assert.equal(eventsHash(playAnchors(DepthSim as never, events, model).out), eventsHash(playAnchors(class extends DepthSim { constructor(m: DepthModel) { super(m, { ...DEFAULT_DEPTH_SIM_PARAMS }); } } as never, events, model).out));
});

test('the same stream as the base commit\'s own file, run side by side with the base constants (when the base commit is in this checkout)', async (t) => {
  const r = spawnSync('git', ['show', `${BASE_COMMIT}:research/history/depthSim.ts`], { cwd: ROOT, encoding: 'utf8', maxBuffer: 16 << 20 });
  if (r.status !== 0 || !r.stdout.includes('REVERT_S')) { t.skip(`commit ${BASE_COMMIT} is not in this checkout (a shallow clone): the committed golden hashes above stand in for it`); return; }
  const file = path.join(tmpDir(), 'depthSimBase.ts');
  fs.writeFileSync(file, r.stdout.replace("from './historyReplay'", `from '${path.join(ROOT, 'research/history/historyReplay').split(path.sep).join('/')}'`));
  const base = await import(pathToFileURL(file).href) as { DepthSim: typeof DepthSim };
  const events = goldenDay(), model = goldenModel();
  // the base file knows no parameters: its constants against the new code given the same constants explicitly (BASE_PARAMS, never the
  // shipped defaults: those may be a promoted sweep's winners by now, and the parity is about the code, not about the numbers)
  const was = playAnchors(base.DepthSim as never, events, model), now = playAnchors(BaseConstantsSim as never, events, model);
  assert.equal(now.out.length, was.out.length);
  assert.equal(eventsHash(now.out), eventsHash(was.out));
  assert.deepEqual(now.stats, was.stats);
  assert.equal(eventsHash(was.out), GOLDEN_BASE.B.hash, 'and the golden hash is what the base commit makes');
});

test('every parameter moves the stream (the parity above is not vacuous), and a changed stream is still seeded and in time order', () => {
  const events = synthRequoteDay({ day: '2026-11-11', assets: ['BTC'], windows: 2 }), model = goldenModel();
  const hashOf = (p: Partial<DepthSimParams>, m: DepthModel = model) => eventsHash(playAnchors(class extends DepthSim { constructor(mm: DepthModel) { super(mm, p); } } as never, events, m).out);
  const same = hashOf({});
  assert.equal(same, eventsHash(playAnchors(DepthSim as never, events, model).out));
  // the cap only binds where a level's size can wander past 1.5 times its 90th percentile: a model with a tight spread and a wandering book
  const tight: DepthModel = { ...model, shape: model.shape.map((c) => ({ ...c, levelFilledP90: c.levelFilledP50.map((x) => Math.round(x * 1.05)) })) };
  for (const n of DEPTH_PARAM_NAMES) {
    const b = DEPTH_PARAM_SPACE[n], [m, base]: [DepthModel, Partial<DepthSimParams>] = n === 'capMult' ? [tight, { stepSd: 0.4 }] : [model, {}];
    const ref = hashOf(base, m), moved = [b.lo, b.hi].map((v) => hashOf({ ...base, [n]: v }, m));
    assert.ok(moved.some((h) => h !== ref), `${n} changes nothing at either end of its range`);
  }
  // seeded: the same params, the same stream
  const p = { revertS: 20, tradeRateMult: 1.5, levelSizeMult: 0.7 };
  assert.equal(hashOf(p), hashOf(p));
  assert.notEqual(hashOf(p), same);
  const out = fillQuotes(events, { how: 'depth' }, model, p);
  assert.ok(out.every((e, i) => i === 0 || e.t >= out[i - 1].t), 'time order');
});

test('no parameter can see the future: the book and the trades before a quote do not move when the next quote does', () => {
  const t = 1_000_000 * MIN;
  const busy: DepthModel = { ...goldenModel(), informed: { n: 9000, agree: 1 } };
  const wild: Partial<DepthSimParams> = { revertS: 3, revertTopS: 0.3, stepSd: 0.3, flickBasePerSec: 0.6, sweepPrints: 6, withinSd: 1.2, activitySd: 1.2, capMult: 2, flickBackMinMs: 8, flickBackSpanMs: 500, tradeRateMult: 2, tradeSizeMult: 2, levelSizeMult: 2 };
  for (const p of [undefined, wild]) {
    const play = (nextMid?: number) => new DepthSim(busy, p).play('K', t, 0.5, 0.52, t + 15_000, t + 30 * MIN, nextMid);
    assert.deepEqual(play(0.3), play(0.7));
    assert.deepEqual(play(0.3), play());
  }
  // and the source holds no clock or global random draw, and the look-ahead switch stays off
  const src = fs.readFileSync(path.join(ROOT, 'research/history/depthSim.ts'), 'utf8');
  assert.ok(!/Date\.now|new Date\(|Math\.random|performance\.now|hrtime/.test(src), 'no clock, no unseeded draw in the simulator');
  assert.match(src, /const USE_NEXT_MOVE = false;/);
});

// ---------------------------------------------------------------------------------------------------------------
// Round R1 (Nov 22): a depth model per asset and per causal stress bucket (schema 2 of the model file).
import { assetOfTicker, DEPTH_ASSETS, MIN_FLOW_SECONDS, MIN_SHAPE_SAMPLES, minuteStress, modelSchema, stressBucket, validateDepthModel, type FlowCell, type ShapeCell } from '../research/history/depthSim';
import { DEPTH_MODEL_SCHEMA } from '../research/history/depthModelVersion';
import { depthStudy } from '../research/depthStudy';
import { rowBuilder } from '../research/historyTwin';
import { synthRecording, writeRecording } from './depthStudySynth';

const quant = (p50: number, p90 = p50) => ({ n: 100, mean: p50, p10: p50, p50, p90 });
/** A shape row of one flat level size (p50 = p90: the size drawn is exactly `p50`), a trade rate and, if asked, an empty-side share. */
const row = (o: { ti: number; mi: number; si?: number; samples?: number; p50?: number; trades?: number; gap?: number; size?: number }): ShapeCell => ({
  ti: o.ti, mi: o.mi, ...(o.si !== undefined ? { si: o.si } : {}), samples: o.samples ?? 400, levelQuoted: Array(10).fill(1),
  levelFilledP50: Array(10).fill(o.p50 ?? 100), levelFilledP90: Array(10).fill(o.p50 ?? 100), tradesPerMin: quant(o.trades ?? 0), tradeSize: quant(o.size ?? 1, o.size ?? 1), takerYesShare: 0.5,
  ...(o.gap !== undefined ? { gapShare: o.gap } : {}),
});
const frow = (o: { offset: number; qi: number; si?: number; seconds?: number; add: number }): FlowCell => ({ offset: o.offset, qi: o.qi, ...(o.si !== undefined ? { si: o.si } : {}), seconds: o.seconds ?? 3600, addPerSec: o.add, cancelPerSec: 0, addSize: quant(5), cancelSize: quant(5) });
const modelOf = (parts: Partial<DepthModel>): DepthModel => ({ days: ['2026-11-11'], schema: 2, shape: [row({ ti: 0, mi: 0 })], flow: [], ...parts });
const top = (ev: ReadonlyArray<Record<string, any>>) => (ev.find((e) => e.k === 'book')!.bids as Array<{ price: number; size: number }>)[0].size;

test('the chain of rows: (asset, stress) -> (asset) -> pooled; a thin row is never used; an unknown asset and a model without blocks use the pooled rows', () => {
  const pooled = [row({ ti: 3, mi: 3, p50: 10 }), row({ ti: 3, mi: 4, p50: 20 })];
  const btc: ShapeCell[] = [
    row({ ti: 3, mi: 3, p50: 1000 }), row({ ti: 3, mi: 3, si: 0, p50: 500 }), row({ ti: 3, mi: 3, si: 1, p50: 1500 }),
    row({ ti: 3, mi: 3, si: 2, p50: 2500, samples: MIN_SHAPE_SAMPLES - 1 }),   // thin: refused
    row({ ti: 3, mi: 4, p50: 3000, samples: MIN_SHAPE_SAMPLES - 1 }),           // a thin asset row: back off to the pooled row
  ];
  const eth: ShapeCell[] = [row({ ti: 3, mi: 3, p50: 2000 })];
  const m = modelOf({ shape: pooled, byAsset: { BTC: { shape: btc, flow: [], stress: { edges: [0.2, 1], n: 900 } }, ETH: { shape: eth, flow: [] } } });
  const sim = new DepthSim(m);
  const p50 = (ticker: string, mid: number, si?: number, tau = 8) => sim.shapeRow(ticker, tau, mid, si).levelFilledP50[0];
  const B = 'KXBTC15M-26NOV11-B', E = 'KXETH15M-26NOV11-E';
  assert.equal(p50(B, 50, 0), 500, 'the (asset, stress) row');
  assert.equal(p50(B, 50, 1), 1500);
  assert.equal(p50(B, 50, 2), 1000, 'a stress row under the sample floor is refused: the asset row');
  const from = (t: string, mid: number, si?: number) => sim.shapeRow(t, 8, mid, si).from;
  assert.deepEqual([from(B, 50, 0), from(B, 50, 2), from(B, 50), from(B, 70, 1), from(E, 50, 2), from('KXDOGE15M-26NOV11-D', 50, 1)], ['stress', 'asset', 'asset', 'pooled', 'asset', 'pooled'], 'which row of the chain answered');
  assert.equal(p50(B, 50), 1000, 'no stress yet (a contract in its first minute): the asset row');
  assert.equal(p50(B, 70, 1), 20, 'no row of the asset at this mid (its own row is thin): the pooled row');
  assert.equal(p50(B, 80, 0), 20, 'no pooled row either: the pooled rows\' own nearest cell');
  assert.equal(p50(E, 50, 2), 2000, 'an asset with no stress rows: its row');
  assert.equal(p50(E, 70), 20, 'ETH has no row at this mid: pooled');
  for (const t of ['KXDOGE15M-26NOV11-D', 'KXSOL15M-26NOV11-S', 'SYN-1', 'KXBTCMAXY-26-X']) assert.equal(p50(t, 50, 1), 10, `${t}: no block for its asset, the pooled row`);
  assert.equal(p50(B, 50, 0, 20), 10, 'a bucket of minutes to close the asset has no row for: the pooled row at it');
  // the floor is the study's own (it writes no thinner row), and the picks count which row fed each draw
  assert.equal(MIN_SHAPE_SAMPLES, 20);
  // a model WITHOUT blocks reads every ticker from the pooled rows, as before
  const plain = new DepthSim(modelOf({ shape: pooled }));
  assert.equal(plain.shapeRow(B, 8, 50, 0).levelFilledP50[0], 10);
  // the flow rows: the same chain, an exact queue bucket first, then the pooled table's nearest queue bucket
  const fm = modelOf({ shape: pooled, flow: [frow({ offset: 0, qi: 1, add: 1 }), frow({ offset: 0, qi: 4, add: 9 })], byAsset: { BTC: { shape: btc, stress: { edges: [0.2, 1], n: 900 },
    flow: [frow({ offset: 0, qi: 1, add: 2 }), frow({ offset: 0, qi: 1, si: 0, add: 3 }), frow({ offset: 0, qi: 1, si: 1, add: 4, seconds: MIN_FLOW_SECONDS })] } } });
  const fs2 = new DepthSim(fm);
  assert.equal(MIN_FLOW_SECONDS, 60);
  assert.equal(fs2.flowRow(B, 0, 5, 0)!.addPerSec, 3, 'the (asset, stress) flow row (queue 5 is bucket 1)');
  assert.equal(fs2.flowRow(B, 0, 5, 1)!.addPerSec, 2, 'a flow row of exactly MIN_FLOW_SECONDS is thin: the asset row');
  assert.equal(fs2.flowRow(B, 0, 5, 2)!.addPerSec, 2, 'no stress row: the asset row');
  assert.equal(fs2.flowRow(B, 0, 5)!.addPerSec, 2);
  assert.equal(fs2.flowRow(E, 0, 5, 0)!.addPerSec, 1, 'an asset with no block: pooled');
  assert.equal(fs2.flowRow(B, 0, 400, 0)!.addPerSec, 9, 'no row of the asset at queue bucket 3: the pooled table, its nearest queue bucket (4)');
  assert.equal(fs2.flowRow(B, 5, 5, 0), undefined, 'nothing anywhere');
  // the picks: each quarter-minute says which row fed it
  const t0 = 1_000_000 * MIN;
  sim.play(B, t0, 0.49, 0.51, t0 + 15_000, t0 + 8 * MIN);
  sim.play(E, t0, 0.49, 0.51, t0 + 15_000, t0 + 8 * MIN);
  sim.play('KXDOGE15M-26NOV11-D', t0, 0.49, 0.51, t0 + 15_000, t0 + 8 * MIN);
  assert.deepEqual(sim.picks, { stress: [0, 0, 0], asset: 2, pooled: 0 }, 'BTC (no stress yet) and ETH from the asset rows; DOGE has no block, so nothing is picked or counted');
});

test('the asset of a ticker comes from the bot\'s own series helper, over the model\'s assets', () => {
  assert.deepEqual([...DEPTH_ASSETS], ['BTC', 'ETH', 'SOL', 'XRP']);
  for (const [t, a] of [['KXBTC15M-26NOV11-A', 'BTC'], ['KXETH15M-26NOV11-A', 'ETH'], ['KXSOL15M-26NOV11-0000', 'SOL'], ['KXXRP15M-26NOV11-1', 'XRP'], ['KXBTCD-26NOV1117-T98000', 'BTC']] as const) assert.equal(assetOfTicker(t), a, t);
  for (const t of ['KXDOGE15M-26NOV11-A', 'SYN-1', 'KXBTCMAXY-26-X', 'BTC-26']) assert.equal(assetOfTicker(t), undefined, t);
  assert.equal(assetOfTicker('KXDOGE15M-26NOV11-A', ['DOGE']), 'DOGE', 'over the model\'s own assets');
});

test('the stress: the mean absolute change of the minute mid over the last three completed minutes, bucketed with the model\'s edges', () => {
  const mids = [50, 50, 50.5, 53, 53, 53, 53];
  const at = (m: number) => minuteStress((k) => (k < 0 || k > m ? undefined : mids[k]), m);
  assert.equal(at(0), undefined, 'a contract in its first minute has no stress: the asset row');
  assert.equal(at(1), 0, 'the one change it has');
  assert.equal(at(2), 0.25, 'two changes: (0.5 + 0) / 2');
  assert.equal(at(3), 1, '(2.5 + 0.5 + 0) / 3');
  assert.equal(at(4), 1, 'the three last changes: (0 + 2.5 + 0.5) / 3');
  assert.equal(at(5), 0.833333, 'the change of minute 2 -> 3 is still among the last three at minute 5');
  assert.equal(at(6), 0, 'and out of them at minute 6');
  // a missing minute mid leaves its two changes out; a stress of nothing is none
  assert.equal(minuteStress((k) => (k === 4 ? undefined : mids[k]), 5), 2.5, 'minute 4 unquoted: its two changes are left out, and the change 2 -> 3 is the one left');
  assert.equal(minuteStress((k) => (k === 5 ? undefined : mids[k]), 5), 1.25, 'the stamp\'s own minute unquoted: (0 + 2.5) / 2, the pairs that exist');
  assert.equal(minuteStress(() => undefined, 9), undefined);
  // the edges are the grid values the study cut at, a stress ON an edge is in the lower bucket, and a float-noisy one is on it too
  const edges: [number, number] = [0.2, 1];
  assert.deepEqual([0, 0.2, 0.2000001, 1, 1.0000001, 7].map((v) => stressBucket(edges, v)), [0, 0, 1, 1, 2, 2]);
  assert.equal(minuteStress((k) => [50, 50.1, 50.2, 50.3][k], 3), 0.1, 'the mean of three changes of 0.1 (and its float noise) is on the edge 0.1');
  assert.equal(stressBucket([0.1, 1], minuteStress((k) => [50, 50.1, 50.2, 50.3][k], 3)!), 0);
});

/** One contract's quotes every 15 s over `minutes` minutes: the minute `m`'s mid (cents) is `mid(m)`, a bid and an ask a cent each side of it. */
function flatQuotes(ticker: string, open: number, minutes: number, mid: (m: number) => number): Ev[] {
  const close = open + minutes * MIN, out: Ev[] = [{ t: open - MIN, k: 'market', ticker, series: ticker.split('-')[0], kind: 'updown', openTime: open, closeTime: close, strike: 1, cap: null, hist: 1 } as Ev];
  for (let t = open; t < close; t += 15_000) { const c = mid(Math.floor((t - open) / MIN)); out.push({ t, k: 'book', ticker, bids: [{ price: +(c / 100 - 0.01).toFixed(3), size: 100 }], asks: [{ price: +(c / 100 + 0.01).toFixed(3), size: 100 }], ts: t } as Ev); }
  out.push({ t: close + 1000, k: 'result', ticker, result: 'yes' } as Ev);
  return out;
}
import type { Ev } from '../research/goLiveTally';
/** A model with a row per stress bucket for every minutes-to-close bucket at the 40-60c mid bucket, each bucket's top size its own number. */
const stressModel = (o: { gap?: number; lives?: { n: number; unquotedShare: number; leadSlots?: number } } = {}): DepthModel => modelOf({
  shape: [row({ ti: 3, mi: 3, p50: 10 })],
  byAsset: { BTC: { stress: { edges: [0.2, 1], n: 900 }, flow: [], ...(o.lives ? { lives: o.lives } : {}), shape: [0, 1, 2, 3, 4, 5].flatMap((ti) => [2, 3].flatMap((mi) => [row({ ti, mi, p50: 1000, trades: 30, gap: o.gap }), row({ ti, mi, si: 0, p50: 500, trades: 30, gap: o.gap }), row({ ti, mi, si: 1, p50: 1500, trades: 30, gap: o.gap }), row({ ti, mi, si: 2, p50: 2500, trades: 30, gap: o.gap })])) } },
});

test('the stress path in the simulator: the first minute has the asset row, then each anchor reads the stress its past minutes give and the model\'s edges bucket it', () => {
  const t0 = 1_000_000 * MIN, T = 'KXBTC15M-26NOV11-STRESS', mids = [50, 50.5, 53, 53, 53, 53];
  const sim = new DepthSim(stressModel());
  const quotes = flatQuotes(T, t0, 6, (m) => mids[m]).filter((e) => e.k === 'book');
  const seen: string[] = [];
  for (const e of quotes) {
    const was = JSON.stringify(sim.picks);
    const ev = sim.play(T, e.t, e.bids![0].price, e.asks![0].price, e.t + 15_000, t0 + 6 * MIN) as Array<Record<string, any>>;
    const now = sim.picks, prev = JSON.parse(was) as typeof sim.picks;
    seen.push(now.asset > prev.asset ? 'asset' : String(now.stress.findIndex((n, k) => n > prev.stress[k])));
    if (seen.length === 1) assert.equal(top(ev), 1000, 'the first book is drawn from the asset row (the books after it keep their levels and move back toward the row\'s sizes)');
  }
  // minute 0: none; minute 1: |50.5 - 50| = 0.5 (normal); minute 2: (2.5 + 0.5) / 2 = 1.5 (active); minutes 3 and 4: 1 and 0.83 (normal, on the
  // edge and under it); minute 5: 0 (calm)
  const rep = (x: string, n = 4) => Array(n).fill(x);
  assert.deepEqual(seen, [...rep('asset'), ...rep('1'), ...rep('2'), ...rep('1'), ...rep('1'), ...rep('0')]);
  assert.deepEqual(sim.picks, { stress: [4, 12, 4], asset: 4, pooled: 0 });
});

test('no look-ahead: change a contract\'s quotes from a minute stamp on, and every book and trade before that stamp is bit-identical (the stress path included)', () => {
  const t0 = 1_000_000 * MIN, T = 'KXBTC15M-26NOV11-SHIFT', U = 'KXETH15M-26NOV11-SHIFT', stamp = t0 + 3 * MIN;
  const sameUntil = [50, 50.5, 53, 53, 53, 53], future = (m: number) => (m < 3 ? sameUntil[m] : 41 + 7 * (m % 2));
  // a model that trades, so there is something to differ: every row has a rate, a trade size and a gap share
  const m = stressModel({ gap: 0.3 });
  m.byAsset!.BTC.shape.forEach((r) => { r.tradesPerMin = quant(60); r.tradeSize = quant(3, 6); });
  const day = (mid: (m: number) => number) => [...flatQuotes(T, t0, 6, mid), ...flatQuotes(U, t0, 6, sameUntil.length ? (mm) => sameUntil[mm] : () => 50)].sort((a, b) => a.t - b.t);
  const a = day((mm) => sameUntil[mm]), b = day(future);
  assert.notDeepEqual(a, b);
  const before = (evs: Array<Record<string, any>>) => evs.filter((e) => e.t < stamp);
  // (1) DepthSim.play anchor by anchor, as the stream filler calls it, the next quote's mid passed along
  const viaPlay = (events: Ev[]) => playAnchors(DepthSim as never, events, m).out as Array<Record<string, any>>;
  const pa = viaPlay(a), pb = viaPlay(b);
  assert.ok(before(pa).length > 500 && before(pa).filter((e) => e.k === 'trade').length > 100, 'there is something before the stamp');
  assert.deepEqual(before(pa), before(pb), 'play: every record before the stamp is bit-identical');
  assert.notDeepEqual(pa.filter((e) => e.t >= stamp), pb.filter((e) => e.t >= stamp), 'and the future differs (the shift is real)');
  // (2) the whole fill-in as the twin and the tally run it
  const fa = fillQuotes(a, { how: 'depth' }, m) as Array<Record<string, any>>, fb = fillQuotes(b, { how: 'depth' }, m) as Array<Record<string, any>>;
  assert.deepEqual(before(fa).filter((e) => e.ticker === T), before(fb).filter((e) => e.ticker === T));
  assert.ok(before(fa).filter((e) => e.ticker === T && e.sim).length > 500);
  assert.deepEqual(before(fa).filter((e) => e.ticker === U), before(fb).filter((e) => e.ticker === U), 'and a contract whose quotes did not change is unchanged throughout');
  assert.deepEqual(fa.filter((e) => e.ticker === U), fb.filter((e) => e.ticker === U));
  // the stress path is on that path: the contract draws from stress rows before the stamp
  const sim = new DepthSim(m);
  for (const e of a.filter((x) => x.k === 'book' && x.ticker === T && x.t < stamp)) sim.play(T, e.t, e.bids![0].price, e.asks![0].price, e.t + 15_000, t0 + 6 * MIN);
  assert.ok(sim.picks.stress.reduce((x, y) => x + y, 0) >= 8, `${JSON.stringify(sim.picks)}`);
  // the quote AT the stamp is already the future of every book before it, and the first book it feeds is the one at the stamp
  const at = (evs: Array<Record<string, any>>) => evs.filter((e) => e.t >= stamp && e.t < stamp + 15_000 && e.k === 'book' && e.ticker === T);
  assert.notDeepEqual(at(pa), at(pb));
});

test('a model WITHOUT blocks, a model whose blocks are empty and a ticker with no block for its asset all play the very stream the pooled rows give; the same input twice is the same stream', () => {
  const events = synthRequoteDay({ day: '2026-11-11', assets: ['BTC', 'ETH'], windows: 2 }), model = goldenModel();
  const pooledHash = eventsHash(playAnchors(DepthSim as never, events, model).out);
  assert.equal(pooledHash, eventsHash(playAnchors(DepthSim as never, events, { ...model, schema: 2 }).out));
  assert.equal(pooledHash, eventsHash(playAnchors(DepthSim as never, events, { ...model, schema: 2, byAsset: {} }).out), 'a byAsset without a block');
  assert.equal(pooledHash, eventsHash(playAnchors(DepthSim as never, events, { ...model, schema: 2, byAsset: { BTC: { shape: [], flow: [] }, ETH: { shape: [], flow: [], stress: { edges: [0.1, 1], n: 1000 } } } }).out), 'blocks with no rows back off to the pooled rows all the way');
  assert.equal(pooledHash, eventsHash(playAnchors(DepthSim as never, events, { ...model, schema: 2, byAsset: { DOGE: { shape: model.shape.map((c) => ({ ...c, samples: 999 })), flow: [] } } }).out), 'a block of another asset');
  // and fillQuotes with the golden params still has the base commit's hash (a model with no `schema` at all)
  const sim = (m: DepthModel) => eventsHash(fillQuotes(events, { how: 'depth' }, m, BASE_PARAMS));
  assert.equal(sim(model), sim({ ...model, schema: 2, byAsset: { SOL: { shape: [], flow: [] } } }));
  // a block that DOES hold rows changes the stream (the check above is not vacuous)
  assert.notEqual(pooledHash, eventsHash(playAnchors(DepthSim as never, events, { ...model, schema: 2, byAsset: { BTC: { shape: model.shape.map((c) => ({ ...c, levelFilledP50: c.levelFilledP50.map((x) => x * 3) })), flow: [] } } }).out));
  // determinism: the stream of a model with blocks and stress rows is the same twice, and does not depend on the order contracts are played in
  const sm = stressModel({ gap: 0.2 });
  const t0 = 1_000_000 * MIN, q = [...flatQuotes('KXBTC15M-26NOV11-D1', t0, 5, (m) => 50 + (m % 3)), ...flatQuotes('KXBTC15M-26NOV11-D2', t0, 5, (m) => 50 + 2 * (m % 2))].sort((x, y) => x.t - y.t);
  const h1 = eventsHash(playAnchors(DepthSim as never, q, sm).out), h2 = eventsHash(playAnchors(DepthSim as never, q, sm).out);
  assert.equal(h1, h2);
  const only = (tk: string) => eventsHash(playAnchors(DepthSim as never, q.filter((e) => e.ticker === tk || e.ticker === undefined), sm).out);
  const both = playAnchors(DepthSim as never, q, sm).out;
  assert.equal(eventsHash(both.filter((e) => e.ticker === 'KXBTC15M-26NOV11-D1')), only('KXBTC15M-26NOV11-D1'), 'a contract plays the same alone and beside another');
});

test('the scale of each asset: a model fitted on a BTC-sized and an ETH-sized market plays BTC about as many times busier and deeper as the model says', async () => {
  const dir = tmpDir(), file = path.join(dir, 'md-2026-11-11.jsonl.gz');
  writeRecording(file, synthRecording([{ name: 'BTC', size: 4000, trades: 30 }, { name: 'ETH', size: 200, trades: 3 }]).events);
  const fit = await depthStudy([file], '15m');
  const model = { days: ['2026-11-11'], ...fit } as unknown as DepthModel;
  validateDepthModel(model);
  assert.equal(modelSchema(model), DEPTH_MODEL_SCHEMA);
  const rows = (a: string) => model.byAsset![a].shape.filter((x) => x.si === undefined && x.mi === 3 && Number.isFinite(x.tradesPerMin.mean));
  const mean = (xs: number[]) => xs.reduce((s, x) => s + x, 0) / xs.length;
  // what the model says: the ratio of BTC to ETH in each of the asset rows' trade rate and top-10 depth, at the same minutes to close
  const sayTrades = mean(rows('BTC').map((r) => r.tradesPerMin.mean / rows('ETH').find((e) => e.ti === r.ti)!.tradesPerMin.mean));
  const sayDepth = mean(rows('BTC').map((r) => (r as unknown as { depth10: { p50: number } }).depth10.p50 / (rows('ETH').find((e) => e.ti === r.ti) as unknown as { depth10: { p50: number } }).depth10.p50));
  assert.ok(Math.abs(sayTrades - 10) < 0.5 && sayDepth > 15 && sayDepth < 25, `the model says ${sayTrades.toFixed(1)}x trades, ${sayDepth.toFixed(1)}x depth`);
  // what the simulator plays: 6 contracts of each asset, every one at the 50c mid (calm), 15 minutes. activitySd is the contract-to-contract
  // spread of the trade rate (0.6 by default: the ratio of two single contracts is anything from 0.3x to 3x of the model's); with 6
  // contracts a side and 0.15 the played ratio is the model's within a few percent (measured: 10.08 against 10, 20.1 against 20.0), the
  // tolerance below (15%) leaves room for the Poisson draws, the sweeps and a change of the seeds
  const t0 = 1_000_000 * MIN, play = (a: string) => {
    const sim = new DepthSim(model, { activitySd: 0.15 });
    let trades = 0, depth = 0, books = 0;
    for (let i = 0; i < 6; i++) {
      const T = `KX${a}15M-26NOV11-S${i}`;
      for (const e of flatQuotes(T, t0, 15, () => 50).filter((x) => x.k === 'book')) {
        for (const ev of sim.play(T, e.t, e.bids![0].price, e.asks![0].price, e.t + 15_000, t0 + 15 * MIN) as Array<Record<string, any>>) {
          if (ev.k === 'trade') trades++;
          else if (ev.k === 'book') { depth += (ev.bids as Array<{ size: number }>).reduce((s, l) => s + l.size, 0); books++; }
        }
      }
    }
    return { perMin: trades / (6 * 15), depth: depth / books };
  };
  const b = play('BTC'), e = play('ETH');
  const gotTrades = b.perMin / e.perMin, gotDepth = b.depth / e.depth;
  assert.ok(gotTrades > sayTrades * 0.85 && gotTrades < sayTrades * 1.15, `trades: played ${gotTrades.toFixed(2)}x, the model says ${sayTrades.toFixed(2)}x`);
  assert.ok(gotDepth > sayDepth * 0.85 && gotDepth < sayDepth * 1.15, `depth: played ${gotDepth.toFixed(2)}x, the model says ${sayDepth.toFixed(2)}x`);
});

test('an empty side at the end of a quarter-minute, at the share the row says, on the side the price is running out of; the twin\'s quotedShare feature moves with it', () => {
  const t0 = 1_000_000 * MIN, T = 'KXBTC15M-26NOV11-GAP';
  const played = (gap: number | undefined, mid: number) => {
    const sim = new DepthSim(stressModel({ gap }));
    const ev: Array<Record<string, any>> = [];
    for (const e of flatQuotes(T, t0, 15, () => mid).filter((x) => x.k === 'book')) ev.push(...(sim.play(T, e.t, e.bids![0].price, e.asks![0].price, e.t + 15_000, t0 + 15 * MIN) as Array<Record<string, any>>));
    return ev;
  };
  /** The book as each quarter-minute's last millisecond leaves it, rebuilt from the records. */
  const ends = (ev: Array<Record<string, any>>) => {
    const bids = new Map<number, number>(), asks = new Map<number, number>(), out: Array<{ bid: number; ask: number }> = [];
    for (let i = 0; i < ev.length; i++) {
      const e = ev[i];
      if (e.k === 'book') { bids.clear(); asks.clear(); for (const l of e.bids) bids.set(Math.round(l.price * 1000), l.size); for (const l of e.asks) asks.set(Math.round(l.price * 1000), l.size); }
      else if (e.k === 'delta') { const m = e.side === 'bid' ? bids : asks, p = Math.round(e.price * 1000), n = (m.get(p) ?? 0) + e.delta; if (n > 0) m.set(p, n); else m.delete(p); }
      const next = ev[i + 1];
      if (!next || next.k === 'book') out.push({ bid: bids.size, ask: asks.size });
    }
    return out;
  };
  const e0 = ends(played(undefined, 50)), e1 = ends(played(1, 50)), eHalf = ends(played(0.5, 50)), low = ends(played(1, 30));
  assert.ok(e0.length >= 59 && e0.every((x) => x.bid > 0 && x.ask > 0), 'no share: two-sided every time');
  assert.ok(e1.every((x) => x.bid > 0 && x.ask === 0), 'a share of 1 at a mid of 50c or more: the ask side is left empty');
  assert.ok(low.every((x) => x.bid === 0 && x.ask > 0), 'under 50c: the bid side');
  const share = eHalf.filter((x) => x.ask === 0).length / eHalf.length;
  assert.ok(share > 0.3 && share < 0.7 && eHalf.every((x) => x.bid > 0), `half the share: ${share.toFixed(2)} of the quarter-minutes end one-sided`);
  assert.equal(eventsHash(played(0, 50)), eventsHash(played(undefined, 50)), 'a share of 0 draws nothing');
  // the judged feature: quotedShare = quoted slots / all slots, every 15 s from the open to the close, just before that instant's records
  const day = '2026-11-11', d0 = Date.parse(`${day}T00:00:00Z`), open = d0 + 6 * 3_600_000;
  const feature = (gap: number | undefined) => {
    const input = flatQuotes(T, open, 15, () => 50);
    const filled = fillQuotes(input, { how: 'depth' }, stressModel({ gap }));
    const rb = rowBuilder(day, 'depth', new Map([[T, 'yes']]));
    for (const e of filled) rb.push(e as Record<string, any>);
    return rb.finish()[0].f[3];
  };
  const none = feature(undefined), some = feature(0.3);
  assert.ok(none > 0.95, `no empty sides: quotedShare ${none.toFixed(3)} (the open's slot has no book yet)`);
  assert.ok(some < none - 0.15 && some > none - 0.45, `a share of 0.3: quotedShare ${some.toFixed(3)} against ${none.toFixed(3)}`);
});

test('the model file: a schema newer than this code, byAsset without schema 2, and stress rows without edges are refused; an old model and a pooled-only schema 2 one read', () => {
  const f = (m: unknown) => { const file = path.join(tmpDir(), 'depth_model.json'); fs.writeFileSync(file, JSON.stringify(m)); return readDepthModel(file); };
  const base = synthModel();
  assert.ok(f(base), 'no schema: 0, the pooled tables');
  assert.ok(f({ ...base, schema: 2 }));
  assert.equal(modelSchema(base), 0);
  assert.equal(f({ ...base, schema: DEPTH_MODEL_SCHEMA + 1 }), undefined, 'a model of a newer code: refit it');
  assert.throws(() => new DepthSim({ ...base, schema: DEPTH_MODEL_SCHEMA + 1 }), /schema \d+ and this code reads up to schema 2/);
  assert.equal(f({ ...base, byAsset: { BTC: { shape: base.shape, flow: [] } } }), undefined, 'blocks without schema 2');
  assert.throws(() => validateDepthModel({ ...base, schema: 1, byAsset: {} }), /need schema 2 or more/);
  assert.equal(f({ ...base, schema: 2, byAsset: { BTC: { shape: [{ ...base.shape[0], si: 1 }], flow: [] } } }), undefined, 'stress rows without the asset\'s edges');
  assert.equal(f({ ...base, schema: 2, byAsset: { BTC: { shape: [{ ...base.shape[0], si: 3 }], flow: [], stress: { edges: [0, 1], n: 9 } } } }), undefined, 'a stress bucket of 3');
  assert.equal(f({ ...base, schema: 2, byAsset: { BTC: { shape: base.shape, flow: [], stress: { edges: [2, 1], n: 9 } } } })?.byAsset?.BTC?.stress?.edges[0], 2, 'edges are only checked where stress rows use them');
  assert.equal(f({ ...base, schema: 2, byAsset: { BTC: { shape: [{ ...base.shape[0], si: 1 }], flow: [], stress: { edges: [2, 1], n: 9 } } } }), undefined, 'descending edges');
  assert.ok(f({ ...base, schema: 2, byAsset: { BTC: { shape: [{ ...base.shape[0], si: 1 }, base.shape[0]], flow: [], stress: { edges: [0.2, 1], n: 900 } } } }));
  assert.throws(() => validateDepthModel({ schema: 1.5 } as never), /whole number/);
  assert.equal(DEPTH_MODEL_SCHEMA, 2);
});

test('the study and the simulator bucket the same instants alike: the simulator, played on the quotes a recording\'s contracts had, draws from each stress bucket as often as the study sampled it', async () => {
  const file = path.join(tmpDir(), 'md-2026-11-11.jsonl.gz');
  const rec = synthRecording([{ name: 'BTC', size: 4000, trades: 30 }, { name: 'ETH', size: 200, trades: 3 }]);
  writeRecording(file, rec.events);
  const fit = await depthStudy([file], '15m');
  const model = { days: ['2026-11-11'], ...fit } as unknown as DepthModel;
  // the quote the history keeps at an instant is the book just BEFORE the instant's own records (a candle's close): the recording's
  // sample at 15 s instant j sees the snapshot of quarter j-1, and so does the quote the simulator is given at j
  const snaps = new Map<string, Array<Record<string, any>>>(), close = new Map<string, number>();
  for (const e of rec.events) { if (e.k === 'book') (snaps.get(e.ticker) ?? snaps.set(e.ticker, []).get(e.ticker)!).push(e); else if (e.k === 'market') close.set(e.ticker, e.closeTime); }
  for (const a of ['BTC', 'ETH']) {
    const sim = new DepthSim(model);
    for (const [ticker, list] of snaps) {
      if (!ticker.startsWith(`KX${a}`)) continue;
      list.forEach((e, j) => { const q = list[Math.max(j - 1, 0)]; sim.play(ticker, e.t, q.bids[0].price, q.asks[0].price, e.t + 15_000, close.get(ticker)!); });
    }
    const rows = (fit.byAsset[a].shape as unknown as Array<{ si?: number; samples: number }>);
    const study = [0, 1, 2].map((b) => rows.filter((r) => r.si === b).reduce((s, r) => s + r.samples, 0));
    assert.deepEqual(sim.picks.stress, study, `${a}: the anchors drawn from stress rows 0, 1, 2 against the study's samples of them`);
    assert.equal(sim.picks.asset, 4 * 24, `${a}: the first minute of each of its 24 contracts has no stress yet: the asset row`);
    assert.equal(sim.picks.pooled, 0);
  }
});

// ---------------------------------------------------------------------------------------------------------------
// R1 fix round 1 (Nov 22): the empty-side draw is netted against the unquoted lead the twin already has.
import { gapScale, LIFE_SLOTS, meanGapShare } from '../research/history/depthSim';

/** A contract as the twin has it: the requote layer's first candle ends a minute after the open, so its first quote is at open + 60 s, then every
 *  15 s to the close (the market record is made a minute before the open). */
const twinQuotes = (ticker: string, open: number, minutes: number, mid: (m: number) => number): Ev[] => flatQuotes(ticker, open, minutes, mid).filter((e) => e.k !== 'book' || e.t >= open + 60_000);

test('the empty-side draw is netted against the twin\'s own unquoted lead: a twin-shaped contract (first quote a minute after its open) keeps the real mean quotedShare, and not less', () => {
  const day = '2026-11-11', d0 = Date.parse(`${day}T00:00:00Z`), N = 24, S = LIFE_SLOTS;
  assert.equal(S, 61);
  /** The mean judged quotedShare of N twin-shaped contracts (and the stream hash of the first one) through the fill-in and the judge's rowBuilder. */
  const play = (m: DepthModel, first = 60_000) => {
    let sum = 0, hash = '';
    for (let i = 0; i < N; i++) {
      const T = `KXBTC15M-26NOV11-NET${i}`, open = d0 + 6 * 3_600_000 + i * 15 * MIN;
      const input = flatQuotes(T, open, 15, () => 50).filter((e) => e.k !== 'book' || e.t >= open + first);
      const filled = fillQuotes(input, { how: 'depth' }, m) as Array<Record<string, any>>;
      const rb = rowBuilder(day, 'depth', new Map([[T, 'yes']]), undefined, false);
      for (const e of filled) rb.push(e);
      sum += rb.finish()[0].f[3];
      if (i === 0) hash = eventsHash(filled);
    }
    return { mean: sum / N, hash };
  };
  const gap = 0.12, real = (slots: number) => ({ n: 500, unquotedShare: slots / S, leadSlots: 2 });
  const none = play(stressModel());
  assert.ok(Math.abs(none.mean - 56 / 61) < 1e-9, `no gap rows: the twin's own 5 unquoted slots of 61, ${none.mean}`);
  // the base case this fixes: the real share drawn on top of the lead (no `lives` in the model: the rows as measured)
  const unnetted = play(stressModel({ gap }));
  assert.ok(none.mean - unnetted.mean > 0.07, `drawn on top of the lead: ${unnetted.mean.toFixed(3)} against ${none.mean.toFixed(3)}`);
  // netted: the real mean life has 5.5 unquoted slots (as B0's real quotedShare 0.915 mean, p10 0.85, p90 0.966 put it); the twin has 5 already
  const netted = play(stressModel({ gap, lives: real(5.5) }));
  assert.ok(Math.abs(netted.mean - (1 - 5.5 / S)) < 0.01, `netted: the twin's quotedShare ${netted.mean.toFixed(4)} against the real ${(1 - 5.5 / S).toFixed(4)}`);
  const shortfall = none.mean - netted.mean, structural = 5.5 / S - 5 / S;
  assert.ok(shortfall > 0 && Math.abs(shortfall - structural) < 0.008, `below the no-gap mean by ${shortfall.toFixed(4)}, the real-minus-twin structural difference is ${structural.toFixed(4)}`);
  // a first quote at the open (a lead of 1 slot, not 5): the same real total is made up with more draws, so the mean is the real one in both
  const early = play(stressModel({ gap, lives: real(5.5) }), 0);
  // (60 draws a contract at 0.075: the mean of 24 contracts is within 0.02 of the real 0.9098 at three standard deviations; unnetted it is 0.866)
  assert.ok(Math.abs(early.mean - (1 - 5.5 / S)) < 0.02, `a lead of 1: ${early.mean.toFixed(4)}`);
  // a real life with LESS unquoted time than the twin's lead (3 slots against 5): nothing is drawn, the stream is the no-gap one, bit for bit
  const less = play(stressModel({ gap, lives: real(3) }));
  assert.equal(less.hash, none.hash, 'a real unquoted mass under the twin\'s lead draws no empty side');
  assert.ok(Math.abs(less.mean - none.mean) < 1e-9);
  // a real life with MORE than the rows' own share can make up (30 slots): never above what the study measured, the rows as measured, bit for bit
  const more = play(stressModel({ gap, lives: real(30) }));
  assert.equal(more.hash, unnetted.hash, 'the draw is never above the rows\' own empty-side share');
});

test('gapScale and meanGapShare: the share of the rows\' empty-side draw a contract plays', () => {
  const S = LIFE_SLOTS;
  // 5.5 real unquoted slots, 5 already in the twin's lead: p = 0.5 / 56 of the slots after the first quote
  assert.ok(Math.abs(gapScale(5.5 / S, 0.06, 5) - (0.5 / 56) / 0.06) < 1e-12);
  assert.equal(gapScale(5.5 / S, 0.06, 5) < 1, true);
  assert.equal(gapScale(undefined, 0.06, 5), 1, 'a model without lives: the rows as measured');
  assert.equal(gapScale(5.5 / S, 0, 5), 1, 'rows with no share: nothing to scale');
  assert.equal(gapScale(3 / S, 0.06, 5), 0, 'a real unquoted mass under the twin\'s lead: none');
  assert.equal(gapScale(0.5, 0.06, 5), 1, 'never above 1');
  assert.ok(Math.abs(gapScale(5.5 / S, 0.12, 1) - (4.5 / 60) / 0.12) < 1e-12, 'a contract quoted at its open (a lead of 1) plays more');
  assert.equal(gapScale(5.5 / S, 0.06, 0), gapScale(5.5 / S, 0.06, 1), 'a lead under one slot is one (the slot at the open is taken before its first quote)');
  assert.equal(gapScale(1, 0.06, 500), 1, 'a lead over the life is the life less one slot: the one slot left is drawn whole, nothing divides by zero');
  // the rows' mean share weighs each row by the instants it stands for (its samples over one minus its share)
  assert.ok(Math.abs(meanGapShare([{ samples: 100, gapShare: 0 }, { samples: 80, gapShare: 0.2 }]) - 0.2 * 100 / 200) < 1e-12);
  assert.equal(meanGapShare([{ samples: 100 }, { samples: 80 }]), 0);
  assert.equal(meanGapShare([]), 0);
});

test('the netting asks nothing of the future: the scale is set by the first quote\'s own time, so changing a contract\'s later quotes leaves every book before them as it was', () => {
  const t0 = 1_000_000 * MIN, T = 'KXBTC15M-26NOV11-NETSHIFT', stamp = t0 + 6 * MIN, m = stressModel({ gap: 0.12, lives: { n: 500, unquotedShare: 9 / LIFE_SLOTS, leadSlots: 2 } });
  const run = (mid: (k: number) => number) => playAnchors(DepthSim as never, flatQuotes(T, t0, 15, mid).filter((e) => e.k !== 'book' || e.t >= t0 + 60_000), m).out as Array<Record<string, any>>;
  const a = run(() => 50), b = run((k) => (k < 6 ? 50 : 41 + 7 * (k % 2)));
  assert.deepEqual(a.filter((e) => e.t < stamp), b.filter((e) => e.t < stamp));
  assert.notDeepEqual(a.filter((e) => e.t >= stamp), b.filter((e) => e.t >= stamp));
});

test('the model file\'s lives: the study writes them next to the rows, the simulator reads only a sensible share, and an older model without them still plays', () => {
  const base = stressModel({ gap: 0.1, lives: { n: 500, unquotedShare: 0.09, leadSlots: 2 } });
  assert.doesNotThrow(() => validateDepthModel(base));
  for (const bad of [-0.1, 1.2, NaN]) assert.throws(() => validateDepthModel({ ...base, byAsset: { BTC: { ...base.byAsset!.BTC, lives: { n: 5, unquotedShare: bad } } } }), /unquoted share of a life must be a number from 0 to 1/, String(bad));
  assert.throws(() => validateDepthModel({ ...base, lives: { n: 5, unquotedShare: 2 } }), /the depth model's lives/);
  assert.doesNotThrow(() => validateDepthModel({ schema: 2, lives: { n: 10, unquotedShare: 0.1 } }), 'pooled lives alone');
  assert.doesNotThrow(() => new DepthSim(stressModel({ gap: 0.1 })), 'no lives: the rows as measured');
  // the pooled rows are netted with the pooled lives: a ticker with no asset block draws the pooled rows' empty side scaled by them
  const t0 = 1_000_000 * MIN, T = 'KXSOL15M-26NOV11-POOLED';
  const pooled = (lives?: { n: number; unquotedShare: number }) => modelOf({ shape: [row({ ti: 0, mi: 0, gap: 0.5 })].concat([1, 2, 3, 4, 5, 6].flatMap((ti) => [0, 1, 2, 3, 4, 5, 6].map((mi) => row({ ti, mi, gap: 0.5 })))), ...(lives ? { lives } : {}) });
  /** The quarter-minutes (of the contract's 56 after its first quote) whose last millisecond leaves a side of the book empty, from the records. */
  const oneSided = (mdl: DepthModel) => {
    const sim = new DepthSim(mdl), bids = new Map<number, number>(), asks = new Map<number, number>();
    let n = 0;
    for (const e of flatQuotes(T, t0, 15, () => 50).filter((x) => x.k === 'book' && x.t >= t0 + 60_000)) {
      const ev = sim.play(T, e.t, e.bids![0].price, e.asks![0].price, e.t + 15_000, t0 + 15 * MIN) as Array<Record<string, any>>;
      for (const x of ev) {
        if (x.k === 'book') { bids.clear(); asks.clear(); for (const l of x.bids) bids.set(Math.round(l.price * 1000), l.size); for (const l of x.asks) asks.set(Math.round(l.price * 1000), l.size); }
        else if (x.k === 'delta') { const m = x.side === 'bid' ? bids : asks, p = Math.round(x.price * 1000), v = (m.get(p) ?? 0) + x.delta; if (v > 0) m.set(p, v); else m.delete(p); }
      }
      if (!bids.size || !asks.size) n++;
    }
    return n;
  };
  assert.ok(oneSided(pooled()) > 15, `as measured: half the quarter-minutes end one-sided (${oneSided(pooled())} of 56)`);
  assert.equal(oneSided(pooled({ n: 500, unquotedShare: 3 / LIFE_SLOTS })), 0, 'a real unquoted mass under the lead: none');
  const some = oneSided(pooled({ n: 500, unquotedShare: 9 / LIFE_SLOTS }));
  assert.ok(some > 0 && some < oneSided(pooled()), `9 real unquoted slots against the lead's 5: a few, ${some}`);
});

test('from a recording to the twin: a model fitted on it (its lives included) plays twin-shaped contracts whose quotedShare is the recording\'s own, where the rows alone would play it far too low', async () => {
  // 48 BTC contracts, every record 0.5 s after the 15 s mark (as a real recording's stamps are), a side empty in every fifth quarter-minute from minute 2: each
  // real life has the slot at its open (before its first snapshot) and 11 empty-side slots unquoted, 12 of 61
  const day = '2026-11-11', dir = tmpDir(), file = path.join(dir, `md-${day}.jsonl.gz`);
  const { SYNTH_OPEN } = await import('./depthStudySynth');
  const rec = synthRecording([{ name: 'BTC', size: 500, trades: 3 }], { perClass: 16 });
  const q = (e: Record<string, any>) => Math.floor((e.t - SYNTH_OPEN) / 15_000), gap = (e: Record<string, any>) => q(e) % 5 === 4 && q(e) >= 8;
  const events = rec.events.filter((e) => !(gap(e) && e.k === 'delta' && e.side === 'ask')).map((e) => (e.k === 'market' || e.k === 'result' ? e : { ...e, t: e.t + 500, ...(gap(e) && e.k === 'book' ? { asks: [] } : {}) }));
  writeRecording(file, events);
  const rb = rowBuilder(day, 'real', new Map(), undefined, false);
  for (const e of events) rb.push(e);
  const real = rb.finish(), realMean = real.reduce((s, r) => s + r.f[3], 0) / real.length;
  assert.equal(real.length, 48);
  assert.ok(Math.abs(realMean - (1 - 12 / 61)) < 1e-9, `the recording's own quotedShare ${realMean}`);
  const fit = await depthStudy([file], '15m');
  const model = { days: [day], ...fit } as unknown as DepthModel;
  validateDepthModel(model);
  assert.ok(Math.abs(model.byAsset!.BTC.lives!.unquotedShare - 11 / 60) < 1e-3 && model.byAsset!.BTC.lives!.leadSlots === 1, JSON.stringify(model.byAsset!.BTC.lives));
  const twin = (m: DepthModel) => {
    let sum = 0;
    for (let i = 0; i < 48; i++) {
      const T = `KXBTC15M-26NOV11-E2E${i}`, open = Date.parse(`${day}T06:00:00Z`) + i * 15 * MIN;
      const rbt = rowBuilder(day, 'depth', new Map([[T, 'yes']]), undefined, false);
      for (const e of fillQuotes(twinQuotes(T, open, 15, () => 50), { how: 'depth' }, m) as Array<Record<string, any>>) rbt.push(e);
      sum += rbt.finish()[0].f[3];
    }
    return sum / 48;
  };
  const netted = twin(model), unnetted = twin({ ...model, lives: undefined, byAsset: { BTC: { ...model.byAsset!.BTC, lives: undefined } } });
  // within 0.03: the study samples 60 of the 61 slots (not the one at the close), and the draws have a binomial spread (0.006 over 48 contracts)
  assert.ok(Math.abs(netted - realMean) < 0.03, `the twin's quotedShare ${netted.toFixed(4)} against the recording's ${realMean.toFixed(4)}`);
  assert.ok(realMean - unnetted > 0.05, `the rows alone: ${unnetted.toFixed(4)}, ${(realMean - unnetted).toFixed(3)} below the recording's`);
});
