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
