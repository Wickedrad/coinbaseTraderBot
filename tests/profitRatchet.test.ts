// The profit ratchet (bot/strategy/profitRatchet.ts; Steven, Nov 11 2026, 8:53 AM EST / 13:53 UTC and 8:58 AM EST / 13:58
// UTC): one ratchet for every position, in dollars for the whole position after both fees. It arms at +$1.50, its stop is
// max($1.00, best - $0.50) and never lowered, and the position is sold once the profit is at or under the stop. While it is
// armed and the profit set a new best in the last 3 s, the hold exit stands aside.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { loadConfig, type StrategyConfig } from '../bot/config';
import { DEFAULT_FEES, orderFee } from '../bot/fees';
import { MetaModel } from '../bot/model/metaModel';
import { PlanPositions } from '../bot/plan/planPositions';
import { exitOnlyPlan } from '../bot/strategy/exitOnlyLane';
import { decide, netProfitAtBid, type MarketView } from '../bot/strategy/fairValueStrategy';
import { HoldExits, type HoldExitConfig, type HoldReading } from '../bot/strategy/holdExit';
import { assertStopNotLowered, ProfitRatchets, ratchetStep, ratchetStopFor, type RatchetReading, type RatchetSettings, type RatchetState } from '../bot/strategy/profitRatchet';
import { runBacktest } from '../research/backtest';
import { writeSyntheticRecordings } from '../research/synthetic';
import { tmpDir } from './helpers';

const S: RatchetSettings = { armUsd: 1.5, stopMinUsd: 1, trailUsd: 0.5 };
const T0 = 1_700_000_000_000;

/** The core over `nets`, one a second from an unarmed state; every step. */
function walk(nets: number[], s: RatchetSettings = S, breakEvenUsd = 0) {
  let st: RatchetState = { armed: false };
  return nets.map((n, i) => {
    const r = ratchetStep(st, n, s, T0 + i * 1000, breakEvenUsd);
    st = r.state;
    return r;
  });
}

function liveEnv(): Record<string, string> {
  const key = path.join(tmpDir(), 'k.pem');
  fs.writeFileSync(key, 'x', { mode: 0o600 });
  return { TRADING_MODE: 'live', KALSHI_KEY_ID: 'id', KALSHI_PRIVATE_KEY_PATH: key, KALSHI_ENV: 'prod', LIVE_TRADING_ACKNOWLEDGED: 'I_ACCEPT_REAL_MONEY_RISK' };
}

test('settings: RATCHET on by default, arming at $1.50 with the stop at least $1.00 and $0.50 under the best; the same in paper and live; the plan ratchet takes them; the old cents settings stop the start', () => {
  const env = { DASHBOARD_TOKEN: 'x'.repeat(32) };
  const paper = loadConfig(env);
  assert.deepEqual(paper.strategy.profitRatchet, { enabled: true, ...S });
  assert.deepEqual(loadConfig({ ...env, ...liveEnv() }).strategy.profitRatchet, paper.strategy.profitRatchet);
  assert.equal(loadConfig({ ...env, RATCHET: 'false' }).strategy.profitRatchet.enabled, false);
  assert.deepEqual(loadConfig({ ...env, RATCHET_ARM_USD: '2', RATCHET_STOP_MIN_USD: '1.25', RATCHET_TRAIL_USD: '0.75' }).strategy.profitRatchet, { enabled: true, armUsd: 2, stopMinUsd: 1.25, trailUsd: 0.75 });
  assert.throws(() => loadConfig({ ...env, RATCHET_STOP_MIN_USD: '1.5' }), /RATCHET_STOP_MIN_USD=1\.5 must be under RATCHET_ARM_USD=1\.5/);
  assert.throws(() => loadConfig({ ...env, RATCHET_TRAIL_USD: '-0.5' }), /RATCHET_TRAIL_USD/);
  assert.throws(() => loadConfig({ ...env, RATCHET: 'maybe' }), /RATCHET=maybe must be true or false/);
  for (const k of ['PLAN_RATCHET_ARM_C', 'PLAN_RATCHET_TRAIL_C']) assert.throws(() => loadConfig({ ...env, [k]: '6' }), new RegExp(`${k} is retired`));
  // A plan position is tagged with these settings (and its rule may give its own).
  const plans = new PlanPositions(paper.strategy.profitRatchet);
  plans.tag({ ticker: 'T', side: 'yes', ruleId: 'r' }, T0);
  assert.deepEqual(plans.get('T')?.settings, { ...S, clock: 'tick' });
});

test('core: arms at +$1.50 and not a cent under; the stop starts at the $1.00 minimum, then trails $0.50 under the best', () => {
  const r = walk([1.49, 1.5, 1.55, 1.6, 1.75, 2.1, 2.4, 2.2]);
  assert.deepEqual(r.map((x) => x.state.armed), [false, true, true, true, true, true, true, true]);
  assert.deepEqual(r.map((x) => x.event), [undefined, 'arm', 'raise', 'raise', 'raise', 'raise', 'raise', undefined]);
  assert.deepEqual(r.map((x) => x.state.best), [undefined, 1.5, 1.55, 1.6, 1.75, 2.1, 2.4, 2.4]);
  // max($1.00, best - $0.50): the $1.00 minimum at arming, then the trail (past +$1.50 it is over the minimum).
  assert.deepEqual(r.map((x) => x.state.stop), [undefined, 1, 1.05, 1.1, 1.25, 1.6, 1.9, 1.9]);
  assert.deepEqual(r.map((x) => x.sell), Array(8).fill(false));
  assert.deepEqual([r[3].prevStop, r[3].state.stop], [1.05, 1.1]);
  assert.equal(r[1].state.armedAt, T0 + 1000);
  // The input state is never changed.
  const st: RatchetState = { armed: false };
  ratchetStep(st, 2, S, T0);
  assert.deepEqual(st, { armed: false });
  assert.equal(ratchetStopFor(1.5, S), 1);
  assert.equal(ratchetStopFor(3, S), 2.5);
});

test('core: sells at or under the stop, not above it; once armed a fall far under sells at once', () => {
  const r = walk([1.6, 2.4, 1.91, 1.9]);
  assert.deepEqual(r.map((x) => [x.state.stop, x.sell]), [[1.1, false], [1.9, false], [1.9, false], [1.9, true]]);
  // Armed and the next evaluation gaps down: sold, whatever the net.
  assert.equal(walk([1.5, 0.2])[1].sell, true);
  // Never armed: never sold by the ratchet, however low.
  assert.ok(walk([1.49, 0.5, -2, 1.2]).every((x) => !x.sell && !x.state.armed));
});

test('core: the stop is never lowered, on a random walk and when a computation would', () => {
  let seed = 7;
  const rand = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
  for (let k = 0; k < 50; k++) {
    let net = 1 + rand();
    const nets = Array.from({ length: 200 }, () => (net += (rand() - 0.5) * 0.3));
    let prev: number | undefined;
    for (const x of walk(nets)) {
      if (prev !== undefined) assert.ok(x.state.stop! >= prev - 1e-9, `stop ${x.state.stop} after ${prev}`);
      if (x.state.armed) assert.ok(x.state.stop! >= 1 - 1e-9 && x.state.stop! >= x.state.best! - 0.5 - 1e-9);
      prev = x.state.stop;
    }
  }
  assert.throws(() => assertStopNotLowered(1.5, 1.4), /profit ratchet: stop lowered from 1\.5 to 1\.4/);
  assert.throws(() => assertStopNotLowered(1.5, undefined), /stop lowered/);
  assert.doesNotThrow(() => assertStopNotLowered(undefined, 1));
  // Settings changed under an armed stop (a lower minimum): the stop it has stays.
  const armed = walk([2.2])[0].state;
  assert.equal(ratchetStep(armed, 2, { armUsd: 1.5, stopMinUsd: 0.5, trailUsd: 1.5 }, T0).state.stop, 1.7);
});

test('core: never under the fee break-even: the stop is at least $0 and at least the net at the fee floor price when given', () => {
  // A rule with no minimum and a trail wider than its arm level: the stop would be under $0.
  const loose: RatchetSettings = { armUsd: 0.3, stopMinUsd: 0, trailUsd: 0.5 };
  const r = walk([0.3, 0.45, 0.04, 0], loose);
  assert.deepEqual(r.map((x) => x.state.stop), [0, 0, 0, 0]);
  assert.deepEqual(r.map((x) => x.sell), [false, false, false, true]);
  // The smallest net at or above $0 the position can sell for is +$0.05 (the price grid): the stop holds there.
  assert.deepEqual(walk([0.3, 0.45, 0.06, 0.05], loose, 0.05).map((x) => [x.state.stop, x.sell]), [[0.05, false], [0.05, false], [0.05, false], [0.05, true]]);
});

test('ProfitRatchets: per market; once its stop is reached the sale goes on until flat; flat, reversed or a fill that empties it starts from nothing', () => {
  const p = new ProfitRatchets(S);
  assert.deepEqual(p.step('T', 10, 1.6, T0), { armed: true, best: 1.6, stop: 1.1, sell: false, event: 'arm' });
  assert.deepEqual(p.step('U', -5, 0.4, T0), { armed: false, sell: false }, 'another market apart');
  assert.deepEqual(p.step('T', 10, 2.2, T0 + 1000), { armed: true, best: 2.2, stop: 1.7, sell: false, event: 'raise', prevStop: 1.1 });
  // No bid: nothing is decided. An older evaluation changes nothing.
  assert.deepEqual(p.step('T', 10, undefined, T0 + 2000), { armed: true, best: 2.2, stop: 1.7, sell: false });
  assert.deepEqual(p.step('T', 10, 0.5, T0 + 500), { armed: true, best: 2.2, stop: 1.7, sell: false });
  assert.deepEqual(p.step('T', 10, 1.7, T0 + 3000), { armed: true, best: 2.2, stop: 1.7, sell: true });
  // A thin bid took 4: the rest goes, whatever its own profit now.
  assert.deepEqual(p.step('T', 6, 1.4, T0 + 4000), { armed: true, best: 2.2, stop: 1.7, sell: true, rest: true });
  assert.deepEqual(p.step('T', 6, 3, T0 + 5000), { armed: true, best: 2.2, stop: 1.7, sell: true, rest: true });
  // Flat: from nothing.
  assert.deepEqual(p.step('T', 0, undefined, T0 + 6000), { armed: false, sell: false });
  assert.deepEqual(p.step('T', 10, 1.2, T0 + 7000), { armed: false, sell: false });
  // Reversed: from nothing.
  p.step('T', 10, 2, T0 + 8000);
  assert.deepEqual(p.step('T', -10, 1.2, T0 + 9000), { armed: false, sell: false });
  // A fill that emptied it between two evaluations, and a same-side one that reopened it: from nothing.
  p.step('T', -10, 2, T0 + 10_000);
  p.onFill('T', -10, 0);
  p.onFill('T', 0, -10);
  assert.deepEqual(p.step('T', -10, 1.2, T0 + 11_000), { armed: false, sell: false });
  // A partial sale or an add keeps it.
  p.step('T', -10, 2, T0 + 12_000);
  p.onFill('T', -10, -6);
  assert.equal(p.step('T', -6, 1.6, T0 + 13_000).armed, true);
  p.forget('T');
  assert.equal(p.step('T', -6, 1.2, T0 + 14_000).armed, false);
});

// ---- The hold exit standing aside (bot/strategy/holdExit.ts) ---------------------------------------------------------------

const HOLD: HoldExitConfig = { enabled: true, usd: 1.5, sec: 10, runUsd: 1, runSec: 3, reentryShare: 0.5 };
const feed = (h: HoldExits, nets: number[], armed: boolean, from = T0): HoldReading[] => nets.map((n, i) => h.sample('T', 10, n, from + i * 1000, armed));

test('hold exit beside the ratchet: a runner setting a new best every second is not sold at 10 s; it is once the best is 3 s old; a sitter is sold at 10 s', () => {
  const runner = Array.from({ length: 14 }, (_, i) => 1.6 + 0.1 * i);
  const r = feed(new HoldExits(HOLD), runner, true);
  assert.ok(r.every((x) => !x.fire), JSON.stringify(r.at(-1)));
  assert.deepEqual(r[10], { fire: false, cumSec: 10, runSec: 10, climbing: true });
  // The ratchet not armed (RATCHET=false, or under +$1.50): nothing stands aside, the hold exit sells at 10 s.
  assert.deepEqual(feed(new HoldExits(HOLD), runner, false)[10], { fire: true, cumSec: 10, runSec: 10 });
  // The runner stalls at its best: 3 s after the last new best the hold exit sells.
  const h = new HoldExits(HOLD);
  const top = runner.at(-1)!;
  const stall = feed(h, [...runner, top, top, top], true);
  assert.deepEqual(stall.slice(-3).map((x) => [x.fire, x.climbing ?? false]), [[false, true], [false, true], [true, false]]);
  // A sitter (+$1.56 to +$1.66): its best is set once, early; sold at 10 s.
  const sit = feed(new HoldExits(HOLD), Array.from({ length: 11 }, (_, i) => (i % 2 ? 1.66 : 1.56)), true);
  assert.deepEqual(sit.map((x) => x.fire), [...Array(10).fill(false), true]);
  assert.equal(sit[10].climbing, undefined);
  // Under the 10 s nothing stands aside: the reading says nothing of climbing, and the count goes on.
  assert.deepEqual(r[5], { fire: false, cumSec: 5, runSec: 5 });
});

test('hold exit beside the ratchet: the rest after a thin bid is sold even while the profit climbs', () => {
  const h = new HoldExits(HOLD);
  feed(h, Array(11).fill(1.62), true);
  h.soldBy('T', T0 + 900_000, T0 + 10_000, true);
  // 4 left; their profit climbs to a new best: the rule decided to sell the whole position, so nothing stands aside.
  h.onFill('T', 10, 4);
  assert.deepEqual(h.sample('T', 4, 2.5, T0 + 11_000, true), { fire: true, cumSec: 11, runSec: 11 });
});

// ---- The sale (decide(), bot/strategy/fairValueStrategy.ts) --------------------------------------------------------------

const base = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), STRATEGY_CADENCE: 'continuous' }).strategy;
const cfg: StrategyConfig = { ...base, style: 'maker', exitPolicy: 'hold' };
// Long 10 YES at 0.40 (a maker fill, no entry fee); the 0.58 bid sells them for +$1.80 less the taker fee.
const long = (o: Partial<MarketView> = {}): MarketView => ({
  ticker: 'T', pYes: 0.55, bestBid: { price: 0.58, size: 50 }, bestAsk: { price: 0.6, size: 50 }, position: 10, bankroll: 200, maxOrderRiskUsd: 4,
  maxContracts: 10, minSidePrice: 0.1, tauSec: 400, noEntryBeforeCloseSec: 15, fastMove: false, tickSize: 0.01, fees: DEFAULT_FEES, nowSec: 1000,
  closeSec: 1400, entrySidePrice: 0.4, entryFeePerContract: 0, ...o,
});
const SELL: RatchetReading = { armed: true, best: 2.3, stop: 1.8, sell: true };
const sale = (v: MarketView, o: Parameters<typeof decide>[2] = {}, c = cfg) => decide(v, c, { exits: false, ...o }).place.find((p) => p.purpose === 'exit' && p.timeInForce === 'immediate_or_cancel');

test('ratchet sale: the whole position at the bid, reduce-only, immediate-or-cancel, protective, liquidating; nothing without its reading', () => {
  const net = 1.8 - orderFee(10, 0.58, true, DEFAULT_FEES);
  assert.ok(Math.abs(netProfitAtBid(long())! - net) < 1e-9);
  const e = sale(long(), { ratchet: SELL })!;
  assert.deepEqual([e.side, e.price, e.count, e.reduceOnly, e.postOnly, e.purpose, e.timeInForce, e.protective], ['ask', 0.58, 10, true, false, 'exit', 'immediate_or_cancel', true]);
  assert.equal(e.why, `profit ratchet: +$${net.toFixed(2)} net on 10 at bid 0.58 is at or under its stop +$1.80 (best +$2.30)`);
  assert.deepEqual(e.liquidation, { hold: false, ratchet: true });
  const rest = sale(long({ position: 4 }), { ratchet: { ...SELL, rest: true } })!;
  assert.equal(rest.count, 4);
  assert.match(rest.why, /^profit ratchet, the rest: \+\$0\.\d\d net on 4 at bid 0\.58; its stop \+\$1\.80 was reached and the sale goes on until flat$/);
  // Armed, not at the stop: nothing sold, a note.
  const armed = decide(long(), cfg, { exits: false, ratchet: { armed: true, best: 2.3, stop: 1.8, sell: false } });
  assert.equal(armed.place.find((p) => p.purpose === 'exit'), undefined);
  assert.ok(armed.notes.includes('profit ratchet armed: best +$2.30, stop +$1.80; sold at or under the stop'), armed.notes.join(' | '));
  assert.equal(sale(long()), undefined, 'RATCHET off (no reading): the hold policy keeps it');
  // A thin bid takes what it can.
  assert.equal(sale(long({ bestBid: { price: 0.58, size: 4 } }), { ratchet: SELL })!.count, 4);
  // Long NO: 10 NO at 0.40; the YES ask 0.42 makes the NO bid 0.58.
  const s = sale(long({ position: -10, pYes: 0.45, bestBid: { price: 0.4, size: 50 }, bestAsk: { price: 0.42, size: 50 } }), { ratchet: SELL })!;
  assert.deepEqual([s.side, s.price, s.count, s.purpose, s.liquidation], ['bid', 0.42, 10, 'exit', { hold: false, ratchet: true }]);
  assert.match(s.why, /^profit ratchet: \+\$1\.6\d net on 10 NO at bid 0\.58 is at or under its stop/);
});

test('ratchet sale: where the quota snipe could not sell, neither can it; the hunt, the model and a plan position\'s own rules', () => {
  assert.equal(sale(long({ exitWindowOpen: false }), { ratchet: SELL }), undefined, 'the final minute rides to settlement');
  assert.equal(sale(long({ settleShare: true }), { ratchet: SELL }), undefined, 'in profit in the last share of the window: rides to settlement');
  assert.equal(sale(long({ entrySidePrice: undefined }), { ratchet: SELL }), undefined, 'no entry cost known: nothing');
  assert.equal(sale(long(), { ratchet: SELL, planHeld: true }), undefined, 'a plan position: the plan\'s own ratchet sells it');
  assert.ok(sale(long(), { ratchet: SELL, blockReductions: true }), 'a hunt trailing its stop does not hold it');
  assert.ok(sale(long(), { ratchet: SELL, armedOnly: true }), 'the exit-only lane: it is a stop, as the quota floor');
  // The model values YES at 0.90 and the take-profit rides: the ratchet is its own rule and sells.
  const fv: StrategyConfig = { ...cfg, exitPolicy: 'fair_value' };
  assert.match(sale(long({ pYes: 0.9 }), { exits: true, ratchet: SELL }, fv)?.why ?? '', /^profit ratchet: /);
});

test('ratchet sale beside the other exits: the quota snipe and floor are unchanged and keep their names; it outranks the hold exit\'s name; one sale', () => {
  assert.match(sale(long(), { pacerUsd: 0.75, ratchet: SELL })!.why, /^quota snipe: /);
  assert.deepEqual(sale(long(), { pacerUsd: 0.75, ratchet: SELL })!.liquidation, { hold: false, ratchet: true });
  assert.match(sale(long(), { pacerUsd: 4.5, ratchet: SELL })!.why, /^profit ratchet: /, 'the snipe\'s target not reached');
  // The quota floor (PACER_FLOOR): a profit under an armed floor sells, labelled the floor's; the ratchet is a second stop.
  const fl: StrategyConfig = { ...cfg, pacer: { ...cfg.pacer!, floor: 'riding', floorTicks: 0 } };
  assert.match(sale(long(), { pacerUsd: 4.5, pacerFloor: 1.7 }, fl)!.why, /^quota snipe \(floor\)/);
  assert.match(sale(long(), { pacerUsd: 4.5, pacerFloor: 1.7, ratchet: SELL }, fl)!.why, /^quota snipe \(floor\)/);
  // With the hold exit firing on the same evaluation: the ratchet's name, the hold exit's rest rule.
  const both = sale(long(), { ratchet: SELL, holdExit: { fire: true, cumSec: 10, runSec: 3 } })!;
  assert.match(both.why, /^profit ratchet: /);
  assert.deepEqual(both.liquidation, { hold: true, ratchet: true });
  assert.equal(decide(long(), cfg, { exits: false, pacerUsd: 4.5, ratchet: SELL, holdExit: { fire: true, cumSec: 10, runSec: 3 } }).place.filter((p) => p.purpose === 'exit').length, 1, 'one sale');
  // The hold exit standing aside: its note says why.
  const climbing = decide(long(), cfg, { exits: false, holdExit: { fire: false, cumSec: 11, runSec: 11, climbing: true }, ratchet: { armed: true, best: 1.71, stop: 1.21, sell: false } });
  assert.equal(climbing.place.find((p) => p.purpose === 'exit'), undefined);
  assert.ok(climbing.notes.includes('hold exit: 11.0 s in all at +$1.50 or more and 11.0 s in a row at +$1.00 or more, but the profit set a new best in the last 3 s: it rides the profit ratchet'), climbing.notes.join(' | '));
});

test('exit-only lane: the ratchet\'s stop sells there as the quota floor does, alone (no hunt stop beside it)', () => {
  const lane = exitOnlyPlan(long(), cfg, { why: 'volatility warming up', exits: false, ratchet: SELL });
  assert.ok(lane.ratchetSale, lane.plan.notes.join(' | '));
  assert.deepEqual(lane.plan.place.map((p) => p.why), [lane.ratchetSale!.why]);
  assert.match(lane.ratchetSale!.why, /^profit ratchet: /);
  assert.ok(lane.plan.notes.some((n) => n.includes('profit ratchet')), lane.plan.notes.join(' | '));
  assert.equal(exitOnlyPlan(long(), cfg, { why: 'volatility warming up', exits: false }).ratchetSale, undefined);
});

// ---- The replay (research/backtest.ts) ------------------------------------------------------------------------------------

test('replay: the same ratchet as the engine sells positions on synthetic data; RATCHET=false sells none; beside the hold exit nothing else sells early', async () => {
  const dir = path.join(tmpDir(), 'rec');
  writeSyntheticRecordings(dir, { windows: 8, seed: 9, marketNoise: 0.05 });
  // EXIT_POLICY=hold with the quota snipe, the profit mandate and the hold exit off: every early sale is the ratchet's.
  const env = { DASHBOARD_TOKEN: 'x'.repeat(32), STRATEGY_STYLE: 'both', STRATEGY_CADENCE: 'continuous', PROFIT_MANDATE: 'false', PACER: 'false', HOLD_EXIT: 'false' };
  const run = (ratchet: string) => { const c = loadConfig({ ...env, RATCHET: ratchet }); return runBacktest(dir, MetaModel.identity(), c.strategy, c.risk, 200, { exitPolicy: 'hold', fillLog: true }); };
  const off = await run('false');
  assert.deepEqual([off.exits.orders, off.exits.ratchetArms, off.exits.profitRatchets], [0, 0, 0]);
  const on = await run('true');
  assert.ok(on.exits.ratchetArms! > 0 && on.exits.profitRatchets! > 0, `arms ${on.exits.ratchetArms}, sales ${on.exits.profitRatchets}`);
  const exitFills = (on.fillLog ?? []).filter((f) => f.coid?.includes('-exit-'));
  assert.ok(exitFills.length > 0 && exitFills.every((f) => f.coid!.endsWith('-exit-ratchet')), JSON.stringify(exitFills.map((f) => f.coid).slice(0, 5)));
  assert.equal(on.exits.profitRatchetContracts, exitFills.reduce((a, f) => a + f.count, 0));
  // With the hold exit on (the default): the two share the sales, and nothing else sells early.
  const both = await runBacktest(dir, MetaModel.identity(), loadConfig({ ...env, HOLD_EXIT: 'true' }).strategy, loadConfig(env).risk, 200, { exitPolicy: 'hold', fillLog: true });
  const kinds = new Set((both.fillLog ?? []).filter((f) => f.coid?.includes('-exit-')).map((f) => f.coid!.replace(/^.*-exit-/, '')));
  assert.ok([...kinds].every((k) => k === 'ratchet' || k === 'hold') && kinds.has('ratchet'), [...kinds].join(', '));
});
