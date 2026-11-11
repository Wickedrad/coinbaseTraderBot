import assert from 'node:assert/strict';
import path from 'path';
import { test } from 'node:test';
import { loadConfig, type StrategyConfig } from '../bot/config';
import { DEFAULT_FEES, orderFee } from '../bot/fees';
import { MetaModel } from '../bot/model/metaModel';
import { decide, netProfitAtBid, tradeNetAtBid, type MarketView } from '../bot/strategy/fairValueStrategy';
import { HOLD_EXIT_JOIN_SLACK_MS, HOLD_EXIT_MAX_GAP_MS, HoldExits, type HoldExitConfig, type HoldReading } from '../bot/strategy/holdExit';
import { runBacktest } from '../research/backtest';
import { writeSyntheticRecordings } from '../research/synthetic';
import { tmpDir } from './helpers';

// Steven's rule (Nov 11): $1.50 after fees for 10 s in all, and $1.00 after fees for the last 3 s in a row, both at once.
const CFG: HoldExitConfig = { enabled: true, usd: 1.5, sec: 10, runUsd: 1, runSec: 3, reentryShare: 0.5, lineAfterFails: 5 };
const T0 = 1_700_000_000_000;

/** Feeds `nets` one a second (or at the given offsets in ms) and returns every reading. */
function feed(h: HoldExits, nets: Array<number | undefined>, o: { position?: number; from?: number; at?: number[] } = {}): HoldReading[] {
  return nets.map((n, i) => h.sample('T', o.position ?? 10, n, (o.from ?? T0) + (o.at ? o.at[i] : i * 1000)));
}

test('settings: on by default at $1.50 for 10 s in all, $1.00 for 3 s in a row, re-entry while more than half the window is left', () => {
  const env = { DASHBOARD_TOKEN: 'x'.repeat(32) };
  assert.deepEqual(loadConfig(env).strategy.holdExit, CFG);
  assert.equal(loadConfig({ ...env, HOLD_EXIT: 'false' }).strategy.holdExit.enabled, false);
  assert.deepEqual(loadConfig({ ...env, HOLD_EXIT_USD: '2', HOLD_EXIT_SEC: '20', HOLD_EXIT_RUN_USD: '1.25', HOLD_EXIT_RUN_SEC: '5', HOLD_EXIT_REENTRY_SHARE: '0.25' }).strategy.holdExit,
    { enabled: true, usd: 2, sec: 20, runUsd: 1.25, runSec: 5, reentryShare: 0.25, lineAfterFails: 5 });
  assert.throws(() => loadConfig({ ...env, HOLD_EXIT_REENTRY_SHARE: '1.5' }), /HOLD_EXIT_REENTRY_SHARE/);
  assert.throws(() => loadConfig({ ...env, HOLD_EXIT_SEC: '-1' }), /HOLD_EXIT_SEC/);
});

test('hold exit: 11 evaluations a second apart at $1.50 or more are 10 s in profit and a live run: it sells at the 11th, not before', () => {
  const r = feed(new HoldExits(CFG), Array(11).fill(1.62));
  assert.deepEqual(r.slice(0, 10).map((x) => x.fire), Array(10).fill(false));
  assert.deepEqual(r[9], { fire: false, cumSec: 9, runSec: 9 });
  assert.deepEqual(r[10], { fire: true, cumSec: 10, runSec: 10 });
});

test('hold exit: the 10 s are counted in all, not in a row: a dip below $1.50 pauses the count and never resets it', () => {
  // 5 s at +$1.62, a dip to +$0.80, then back: the count goes on from 5 s.
  const r = feed(new HoldExits(CFG), [1.62, 1.62, 1.62, 1.62, 1.62, 1.62, 0.8, 0.8, 1.62, 1.62, 1.62, 1.62, 1.62, 1.62]);
  assert.equal(r[5].cumSec, 5);
  assert.equal(r[7].cumSec, 5, 'the dip adds nothing');
  assert.equal(r[8].cumSec, 5, 'a stretch counts only when both ends are at $1.50: 0.80 -> 1.62 adds nothing');
  assert.equal(r[12].cumSec, 9);
  assert.equal(r[12].fire, false);
  assert.deepEqual(r[13], { fire: true, cumSec: 10, runSec: 5 });
  // Between $1.00 and $1.50: not counted toward the 10 s, but the run goes on.
  const mid = feed(new HoldExits(CFG), [1.62, 1.62, 1.2, 1.2, 1.2, 1.62]);
  assert.deepEqual(mid.map((x) => x.cumSec), [0, 1, 1, 1, 1, 1]);
  assert.deepEqual(mid.map((x) => x.runSec), [0, 1, 2, 3, 4, 5]);
});

test('hold exit: the 3 s run is in a row at $1.00 or more; one evaluation below $1.00 restarts it, and it must be live at the sale', () => {
  const r = feed(new HoldExits(CFG), [1.2, 1.2, 1.2, 1.2, 0.99, 1.2, 1.2]);
  assert.deepEqual(r.map((x) => x.runSec), [0, 1, 2, 3, 0, 0, 1]);
  // 10 s in all reached during runs that never last 3 s: no sale until a run does.
  const h = new HoldExits(CFG);
  const nets: number[] = [];
  for (let k = 0; k < 6; k++) nets.push(1.62, 1.62, 1.62, 0.5); // 2 s counted per cycle, runs of 2 s
  const cut = feed(h, nets);
  assert.ok(cut.at(-1)!.cumSec >= 10, `cumulative ${cut.at(-1)!.cumSec}`);
  assert.ok(cut.every((x) => !x.fire && x.runSec <= 2), 'no live 3 s run, no sale');
  const after = feed(h, [1.62, 1.62, 1.62, 1.62], { from: T0 + nets.length * 1000 });
  assert.deepEqual(after.map((x) => x.fire), [false, false, false, true], 'sold once the run reaches 3 s');
  // Both met, then the latest evaluation falls below $1.00: the run is gone, no sale.
  const h2 = new HoldExits(CFG);
  feed(h2, Array(11).fill(1.62));
  assert.equal(h2.sample('T', 10, 0.95, T0 + 11_000).fire, false);
  // A 3 s run alone (at +$1.20, never $1.50) never sells.
  assert.ok(feed(new HoldExits(CFG), Array(30).fill(1.2)).every((x) => !x.fire && x.cumSec === 0));
});

test('hold exit: time is from timestamps; a gap counts nothing and restarts the run; no profit measure is not in profit', () => {
  assert.equal(HOLD_EXIT_MAX_GAP_MS, 2000);
  // Evaluations at 0, 1 s, then a 10 s data gap or stalled loop, then 1 s apart: the gap adds nothing nobody saw.
  const r = feed(new HoldExits(CFG), [1.62, 1.62, 1.62, 1.62], { at: [0, 1000, 11_000, 12_000] });
  assert.deepEqual(r.map((x) => x.cumSec), [0, 1, 1, 2]);
  assert.deepEqual(r.map((x) => x.runSec), [0, 1, 0, 1], 'the run starts again after the gap');
  // Uneven ticks count their real length, not one tick each.
  assert.deepEqual(feed(new HoldExits(CFG), [1.62, 1.62, 1.62], { at: [0, 1500, 1800] }).map((x) => x.cumSec), [0, 1.5, 1.8]);
  // A repeated instant adds nothing.
  assert.deepEqual(feed(new HoldExits(CFG), [1.62, 1.62, 1.62], { at: [0, 1000, 1000] }).map((x) => x.cumSec), [0, 1, 1]);
  // No bid (undefined) is not in profit: no time counted across it, and the run restarts.
  const u = feed(new HoldExits(CFG), [1.62, 1.62, undefined, 1.62, 1.62]);
  assert.deepEqual(u.map((x) => x.cumSec), [0, 1, 1, 1, 2]);
  assert.deepEqual(u.map((x) => x.runSec), [0, 1, 0, 0, 1]);
  assert.equal(new HoldExits(CFG).sample('T', 10, Number.NaN, T0).runSec, 0);
});

test('hold exit: a market skipped one tick as busy (samples a little over 2 s apart) keeps its run and sells; an older evaluation changes nothing', () => {
  assert.equal(HOLD_EXIT_JOIN_SLACK_MS, 500);
  // Every other tick skipped: samples 2001-2050 ms apart at +$2.00 for 60 s. Each stretch counts 2 s and the run holds.
  const at: number[] = [0];
  for (let i = 1; at.at(-1)! < 60_000; i++) at.push(at.at(-1)! + 2001 + ((i * 7) % 50));
  const r = feed(new HoldExits(CFG), at.map(() => 2), { at });
  const first = r.findIndex((x) => x.fire);
  assert.equal(first, 5, JSON.stringify(r.slice(0, 7)));
  assert.equal(r[first].cumSec, 10);
  assert.ok(r[first].runSec > 10, `run ${r[first].runSec}`);
  // One skipped tick inside a run does not restart it; at most 2 s of the stretch is counted.
  const s = feed(new HoldExits(CFG), [1.62, 1.62, 1.62, 1.62], { at: [0, 1000, 3040, 4050] });
  assert.deepEqual(s.map((x) => x.runSec), [0, 1, 3.04, 4.05]);
  assert.deepEqual(s.map((x) => x.cumSec), [0, 1, 3, 4.01]);
  // Past the slack it is a gap.
  assert.deepEqual(feed(new HoldExits(CFG), [1.62, 1.62], { at: [0, 2501] })[1], { fire: false, cumSec: 0, runSec: 0 });
  // Overlapping ticks evaluate out of order (now 2 s before 1 s): the older one counts nothing again and sells nothing.
  const o = feed(new HoldExits(CFG), Array(10).fill(1.62), { at: [0, 2000, 1000, 3000, 4000, 5000, 6000, 7000, 8000, 9000] });
  assert.deepEqual(o[2], { fire: false, cumSec: 2, runSec: 2 }, 'the older evaluation reads as the last one');
  assert.equal(o[8].cumSec, 8, '8 s of time, 8 s counted');
  const late = new HoldExits(CFG);
  assert.equal(feed(late, Array(11).fill(1.62)).at(-1)!.fire, true);
  assert.equal(late.sample('T', 10, 1.62, T0 + 9500).fire, false, 'an older evaluation does not sell again');
});

test('hold exit: a position that went flat or reversed between two evaluations and reopened on the same side starts from nothing', () => {
  const h = new HoldExits(CFG);
  assert.equal(feed(h, Array(11).fill(1.62)).at(-1)!.fire, true);
  // The sale fills (10 -> 0), and a resting same-side bid fills 10 more before the next evaluation: never sampled flat.
  h.onFill('T', 10, 0);
  h.onFill('T', 0, 10);
  assert.deepEqual(h.sample('T', 10, 1.09, T0 + 11_000), { fire: false, cumSec: 0, runSec: 0 });
  // Reversed in one fill and back in the next, between two evaluations: from nothing as well.
  feed(h, Array(11).fill(1.62), { from: T0 + 12_000 });
  h.onFill('T', 10, -5);
  h.onFill('T', -5, 10);
  assert.deepEqual(h.sample('T', 10, 1.62, T0 + 24_000), { fire: false, cumSec: 0, runSec: 0 });
  // A partial sale or an add keeps the count.
  feed(h, Array(5).fill(1.62), { from: T0 + 25_000 });
  h.onFill('T', 10, 6);
  h.onFill('T', 6, 12);
  assert.equal(h.sample('T', 12, 1.62, T0 + 30_000).cumSec, 6);
});

test('hold exit: once its sale took part of the position (a thin bid), the rest is sold at the next bids while not at a loss', () => {
  const h = new HoldExits(CFG);
  assert.equal(feed(h, Array(11).fill(1.62)).at(-1)!.fire, true);
  // 4 of 10 sold at the 0.59 bid; the 6 left are worth +$0.75 at the next bid, under the run's $1.00.
  h.onFill('T', 10, 6);
  h.soldBy('T', T0 + 600_000, T0 + 10_000, true);
  assert.deepEqual(h.sample('T', 6, 0.75, T0 + 11_000), { fire: true, cumSec: 10, runSec: 0, rest: true });
  assert.equal(h.sample('T', 6, -0.1, T0 + 12_000).fire, false, 'at a loss after fees: not sold');
  assert.equal(h.sample('T', 6, 0, T0 + 13_000).fire, true, 'break-even: sold');
  // A quota snipe's partial sale (the hold exit had not fired) leaves the rest to the rules as before.
  const s = new HoldExits(CFG);
  feed(s, [1.62, 1.62]);
  s.onFill('T', 10, 6);
  s.soldBy('T', T0 + 600_000, T0 + 2000, false);
  assert.equal(s.sample('T', 6, 0.75, T0 + 2000).fire, false);
  // The hold exit fired but filled nothing (the bid was pulled): no sale at a profit under $1.00.
  const z = new HoldExits(CFG);
  feed(z, Array(11).fill(1.62));
  assert.equal(z.sample('T', 10, 0.75, T0 + 11_000).fire, false);
});

test('hold exit: a flat position or a reversed one starts from nothing; other contracts are kept apart', () => {
  const h = new HoldExits(CFG);
  feed(h, Array(6).fill(1.62));
  assert.equal(h.sample('U', 5, 1.62, T0 + 5000).cumSec, 0, 'another contract has its own count');
  assert.equal(h.sample('T', 10, 1.62, T0 + 6000).cumSec, 6);
  assert.equal(h.sample('T', 4, 1.62, T0 + 7000).cumSec, 7, 'a partial sale keeps the count');
  assert.deepEqual(h.sample('T', -10, 1.62, T0 + 8000), { fire: false, cumSec: 0, runSec: 0 }, 'reversed: from nothing');
  assert.equal(h.sample('T', -10, 1.62, T0 + 9000).cumSec, 1);
  assert.deepEqual(h.sample('T', 0, undefined, T0 + 10_000), { fire: false, cumSec: 0, runSec: 0 });
  assert.equal(h.sample('T', 10, 1.62, T0 + 11_000).cumSec, 0, 'flat in between: from nothing');
  h.forget('T');
  assert.equal(h.sample('T', 10, 1.62, T0 + 12_000).cumSec, 0);
});

// Failed tries (Steven's idea, Nov 11 9:15 AM EST / 14:15 UTC, his card 9:21 AM EST / 14:21 UTC): reached $1.00, then under it
// for 3 s in a row without touching $1.50 on the way.
test('failed tries: reaching $1.00 and then 3 s in a row under it, never touching $1.50, is one; touching $1.50 is none', () => {
  const fails = (r: HoldReading[]) => r.map((x) => x.fails ?? 0);
  // Read at the evaluation that completes the 3 s under $1.00 (1 s, 2 s, 3 s after the first one under), and kept after.
  assert.deepEqual(fails(feed(new HoldExits(CFG), [1.2, 0.8, 0.8, 0.8, 0.8, 0.8])), [0, 0, 0, 0, 1, 1]);
  assert.deepEqual(fails(feed(new HoldExits(CFG), [1.0, 0.99, 0.99, 0.99, 0.99])), [0, 0, 0, 0, 1], 'exactly $1.00 starts a try');
  // Touching $1.50 on the way up, or between two dips: no failure.
  assert.ok(feed(new HoldExits(CFG), [1.2, 1.5, 1.2, 0.8, 0.8, 0.8, 0.8, 0.8]).every((x) => !x.fails));
  assert.ok(feed(new HoldExits(CFG), [1.2, 0.8, 0.8, 1.62, 0.8, 0.8, 0.8, 0.8]).every((x) => !x.fails));
  // Never at $1.00: no try, no failure.
  assert.ok(feed(new HoldExits(CFG), Array(20).fill(0.8)).every((x) => !x.fails));
  // Each try counts once; the next rise to $1.00 starts a new one.
  const cycle = [1.15, 0.85, 0.85, 0.85, 0.85];
  assert.deepEqual(fails(feed(new HoldExits(CFG), [...cycle, ...cycle, ...cycle])), [0, 0, 0, 0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3]);
});

test('failed tries: one-tick wiggles under $1.00 for less than 3 s are no failure; a gap restarts the 3 s; no bid is under $1.00', () => {
  // A tick under and back, then 2 s under and back: the same try goes on, nothing failed.
  const h = new HoldExits(CFG);
  const w = feed(h, [1.05, 0.95, 1.05, 0.95, 0.95, 0.95, 1.05, 0.95, 1.0]);
  assert.ok(w.every((x) => !x.fails), JSON.stringify(w));
  // Uneven ticks: 2.9 s under is not 3 s.
  assert.ok(feed(new HoldExits(CFG), [1.2, 0.8, 0.8, 0.8], { at: [0, 1000, 2500, 3900] }).every((x) => !x.fails));
  // The same try, now 3 s under: one failure.
  assert.equal(feed(h, [0.95, 0.95, 0.95, 0.95], { from: T0 + 9000 }).at(-1)!.fails, 1);
  // A data gap (or a stalled loop) counts nothing: the 3 s start again after it.
  const g = new HoldExits(CFG);
  assert.ok(feed(g, [1.2, 0.8, 0.8, 0.8, 0.8], { at: [0, 1000, 2000, 6000, 7000] }).every((x) => !x.fails));
  assert.deepEqual(feed(g, [0.8, 0.8], { from: T0 + 8000 }).map((x) => x.fails ?? 0), [0, 1], '3 s after the gap');
  // No profit measure (no bid) is under $1.00, as for the run.
  assert.equal(feed(new HoldExits(CFG), [1.2, undefined, undefined, undefined, undefined]).at(-1)!.fails, 1);
});

test('failed tries: counted on the position; a partial sale keeps them, flat or the other side starts from nothing', () => {
  const cycle = [1.15, 0.85, 0.85, 0.85, 0.85];
  const h = new HoldExits(CFG);
  assert.equal(feed(h, [...cycle, ...cycle]).at(-1)!.fails, 2);
  assert.equal(h.sample('U', 10, 0.85, T0 + 10_000).fails, undefined, 'another contract has its own count');
  h.onFill('T', 10, 6);
  assert.equal(h.sample('T', 6, 0.85, T0 + 10_000).fails, 2, 'a partial sale keeps the count');
  h.onFill('T', 6, 0);
  h.onFill('T', 0, 10);
  assert.equal(h.sample('T', 10, 0.85, T0 + 11_000).fails, undefined, 'flat in between: from nothing');
  assert.equal(feed(h, [...cycle], { from: T0 + 12_000 }).at(-1)!.fails, 1);
  assert.equal(h.sample('T', -10, 0.85, T0 + 17_000).fails, undefined, 'reversed: from nothing');
});

test('re-entry: after a hold exit or a quota snipe, the same contract only while more than half its window is left; others unaffected', () => {
  const h = new HoldExits(CFG);
  // A 15-minute contract: a 900 s window, half of it 450 s.
  assert.equal(h.reentryBlock('T', 300, 900), undefined, 'nothing sold here: no limit');
  h.soldBy('T', T0 + 900_000, T0);
  assert.equal(h.reentryBlock('T', 451, 900), undefined, 'more than half left');
  assert.match(h.reentryBlock('T', 450, 900) ?? '', /^re-entry after a hold exit, quota snipe or profit ratchet: 450 s of the 900 s window left, not more than 50%/);
  assert.ok(h.reentryBlock('T', 120, 900));
  assert.equal(h.reentryBlock('U', 120, 900), undefined, 'another contract is not affected');
  assert.equal(h.reentryBlock('T', 120, undefined), undefined, 'no window known: no limit');
  assert.equal(new HoldExits({ ...CFG, enabled: false }).reentryBlock('T', 120, 900), undefined);
  const off = new HoldExits({ ...CFG, reentryShare: 0 });
  off.soldBy('T', T0 + 900_000, T0);
  assert.equal(off.reentryBlock('T', 1, 900), undefined, 'HOLD_EXIT_REENTRY_SHARE=0: no limit');
  // A flat position keeps the mark (it is about entering again); settlement clears it.
  h.sample('T', 0, undefined, T0);
  assert.ok(h.reentryBlock('T', 120, 900));
  h.forget('T');
  assert.equal(h.reentryBlock('T', 120, 900), undefined);
});

test('re-entry marks: saved and restored across a restart until the market closes; a market no longer watched keeps its mark', () => {
  const file = path.join(tmpDir(), 'hold_exit_state.json');
  const close = T0 + 900_000;
  const a = new HoldExits(CFG, file, T0);
  a.soldBy('T', close, T0 + 400_000);
  a.unwatch('T');
  assert.ok(a.reentryBlock('T', 400, 900), 'not evaluated for a while: the mark stays');
  const b = new HoldExits(CFG, file, T0 + 500_000);
  assert.match(b.reentryBlock('T', 400, 900) ?? '', /^re-entry after a hold exit, quota snipe or profit ratchet/, 'restarted with 400 s left: still marked');
  assert.equal(new HoldExits(CFG, file, close).reentryBlock('T', 0, 900), undefined, 'market closed: not restored');
  b.forget('T');
  assert.equal(new HoldExits(CFG, file, T0 + 500_000).reentryBlock('T', 400, 900), undefined, 'settled: gone from the file too');
  assert.equal(new HoldExits(CFG, path.join(tmpDir(), 'none.json'), T0).reentryBlock('T', 400, 900), undefined, 'no file: no marks');
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
const FIRE: HoldReading = { fire: true, cumSec: 10, runSec: 3 };
const sale = (v: MarketView, o: Parameters<typeof decide>[2] = {}) => decide(v, cfg, { exits: false, ...o }).place.find((p) => p.purpose === 'exit' && p.timeInForce === 'immediate_or_cancel');

test('hold exit sale: the whole position at the bid, reduce-only, as the quota snipe sells; nothing without its reading', () => {
  const net = 1.8 - orderFee(10, 0.58, true, DEFAULT_FEES);
  assert.ok(Math.abs(netProfitAtBid(long())! - net) < 1e-9);
  const e = sale(long(), { holdExit: FIRE })!;
  assert.deepEqual([e.side, e.price, e.count, e.reduceOnly, e.postOnly, e.purpose, e.timeInForce], ['ask', 0.58, 10, true, false, 'exit', 'immediate_or_cancel']);
  assert.equal(e.why, `hold exit: +$${net.toFixed(2)} net on 10 at bid 0.58, 10.0 s in all at +$1.50 or more, the last 3.0 s in a row at +$1.00 or more`);
  assert.deepEqual(e.liquidation, { hold: true }, 'it liquidates: its fill marks the contract and the rest is sold too');
  const rest = sale(long(), { holdExit: { fire: true, cumSec: 10, runSec: 0, rest: true } })!;
  assert.deepEqual([rest.count, rest.liquidation], [10, { hold: true }]);
  assert.equal(rest.why, `hold exit, the rest: +$${net.toFixed(2)} net on 10 at bid 0.58; the rule fired and a thin bid took part of the position`);
  assert.equal(sale(long()), undefined, 'HOLD_EXIT off (no reading): the hold policy keeps it, as before');
  const counting = decide(long(), cfg, { exits: false, holdExit: { fire: false, cumSec: 6, runSec: 2 } });
  assert.equal(counting.place.find((p) => p.purpose === 'exit'), undefined);
  assert.ok(counting.notes.includes('hold exit: 6.0 of 10 s in all at +$1.50 or more, 2.0 of 3 s in a row at +$1.00 or more'), counting.notes.join(' | '));
  // A thin bid takes what it can; the rest is judged again next evaluation.
  assert.equal(sale(long({ bestBid: { price: 0.58, size: 4 } }), { holdExit: FIRE })!.count, 4);
  // Long NO: 10 NO at 0.40; the YES ask 0.42 makes the NO bid 0.58.
  const s = sale(long({ position: -10, pYes: 0.45, bestBid: { price: 0.4, size: 50 }, bestAsk: { price: 0.42, size: 50 } }), { holdExit: FIRE })!;
  assert.deepEqual([s.side, s.price, s.count, s.purpose], ['bid', 0.42, 10, 'exit']);
  assert.match(s.why, /^hold exit: \+\$1\.6\d net on 10 NO at bid 0\.58, 10\.0 s in all/);
});

test('hold exit sale: where the quota snipe could not sell, neither can it; a hunt, the model or a higher target do not hold it', () => {
  assert.equal(sale(long({ exitWindowOpen: false }), { holdExit: FIRE }), undefined, 'the final minute rides to settlement');
  assert.equal(sale(long({ settleShare: true }), { holdExit: FIRE }), undefined, 'in profit in the last share of the window: rides to settlement');
  assert.equal(sale(long(), { holdExit: FIRE, armedOnly: true }), undefined, 'the exit-only lane: no hold exit, as no quota snipe');
  assert.equal(sale(long({ entrySidePrice: undefined }), { holdExit: FIRE }), undefined, 'no entry cost known: nothing');
  assert.ok(sale(long(), { holdExit: FIRE, blockReductions: true }), 'a hunt trailing its stop does not stop it');
  // The model values YES at 0.90 and the take-profit is riding: under PACER_FLOOR=riding the quota only arms a floor, but the
  // hold exit is its own rule and sells.
  const riding: StrategyConfig = { ...cfg, exitPolicy: 'fair_value', pacer: { ...cfg.pacer, floor: 'riding' } };
  const out = decide(long({ pYes: 0.9 }), riding, { exits: true, pacerUsd: 0.75, holdExit: FIRE });
  assert.ok(out.pacerArm, 'the quota floor arms');
  assert.match(out.place.find((p) => p.purpose === 'exit')?.why ?? '', /^hold exit: /);
});

test('hold exit sale: the quota snipe is unchanged and still sells at once; on the same evaluation it keeps its name', () => {
  // No hold time at all: the snipe sells as soon as the profit covers what the hour needs.
  assert.match(sale(long(), { pacerUsd: 0.75 })!.why, /^quota snipe: \+\$1\.6\d net on 10 at bid 0\.58 covers the \$0\.75 the hour needs/);
  assert.match(sale(long(), { pacerUsd: 0.75, holdExit: { fire: false, cumSec: 0, runSec: 0 } })!.why, /^quota snipe: /);
  assert.match(sale(long(), { pacerUsd: 0.75, holdExit: FIRE })!.why, /^quota snipe: /);
  assert.deepEqual(sale(long(), { pacerUsd: 0.75 })!.liquidation, { hold: false }, 'a snipe liquidates as well');
  assert.deepEqual(sale(long(), { pacerUsd: 0.75, holdExit: FIRE })!.liquidation, { hold: true });
  // A take-profit selling on the evaluation the hold exit fires keeps its name, and the sale still counts as the hold exit's.
  const tp = decide(long({ profitPeakSidePrice: 0.75 }), { ...cfg, exitPolicy: 'take_profit' }, { exits: true, holdExit: FIRE }).place.find((p) => p.purpose === 'exit')!;
  assert.match(tp.why, /^take-profit/);
  assert.deepEqual(tp.liquidation, { hold: true });
  assert.equal(decide(long({ profitPeakSidePrice: 0.75 }), { ...cfg, exitPolicy: 'take_profit' }, { exits: true }).place.find((p) => p.purpose === 'exit')!.liquidation, undefined, 'a take-profit alone does not');
  // The snipe's target not reached: the hold exit sells.
  assert.match(sale(long(), { pacerUsd: 4.5, holdExit: FIRE })!.why, /^hold exit: /);
  assert.equal(decide(long(), cfg, { exits: false, pacerUsd: 4.5, holdExit: FIRE }).place.filter((p) => p.purpose === 'exit').length, 1, 'one sale');
});

test('hold exit and ratchet sales after a partial sale: the trade\'s net (banked plus the rest); the quota snipe still sees the rest alone', () => {
  // 6 of 10 left (YES at 0.40); the 4 sold earlier banked +$0.60 after fees (openBankedUsd).
  const v = long({ position: 6, bankedUsd: 0.6 });
  const rest = netProfitAtBid(v)!;
  const trade = rest + 0.6;
  assert.ok(Math.abs(tradeNetAtBid(v)! - trade) < 1e-9);
  assert.equal(tradeNetAtBid(long({ bestBid: undefined, bankedUsd: 0.6 })), undefined, 'no bid: no measure');
  const h = sale(v, { holdExit: FIRE })!;
  assert.deepEqual([h.count, h.liquidation], [6, { hold: true }]);
  assert.equal(h.why, `hold exit: +$${trade.toFixed(2)} net (+$0.60 banked by partial sales) on 6 at bid 0.58, 10.0 s in all at +$1.50 or more, the last 3.0 s in a row at +$1.00 or more`);
  assert.equal(sale(v, { holdExit: { fire: true, cumSec: 10, runSec: 0, rest: true } })!.why, `hold exit, the rest: +$${trade.toFixed(2)} net (+$0.60 banked by partial sales) on 6 at bid 0.58; the rule fired and a thin bid took part of the position`);
  const r = sale(v, { ratchet: { armed: true, best: 2.3, stop: 1.8, sell: true } })!;
  assert.equal(r.why, `profit ratchet: +$${trade.toFixed(2)} net (+$0.60 banked by partial sales) on 6 at bid 0.58 is at or under its stop +$1.80 (best +$2.30)`);
  // The quota snipe measures what selling now brings, the rest alone: +$1.20 needed, the rest has less, so nothing.
  assert.ok(rest < 1.2 && trade > 1.2, `${rest} ${trade}`);
  assert.equal(sale(v, { pacerUsd: 1.2 }), undefined);
  assert.ok(sale(v, { pacerUsd: 0.75 })!.why.startsWith(`quota snipe: +$${rest.toFixed(2)} net on 6 at bid 0.58 covers`));
  // Nothing banked: no note, as before.
  assert.doesNotMatch(sale(long(), { holdExit: FIRE })!.why, /banked/);
});

// ---- The replay (research/backtest.ts) ------------------------------------------------------------------------------------

test('replay: the same hold exit and re-entry rule as the engine; HOLD_EXIT=false sells nothing early under the hold policy', async () => {
  const dir = path.join(tmpDir(), 'rec');
  writeSyntheticRecordings(dir, { windows: 8, seed: 9, marketNoise: 0.05 });
  // EXIT_POLICY=hold with the quota snipe, the profit mandate and the profit ratchet off: every early sale is the hold exit's.
  // (With the ratchet: the test after next.)
  const env = { DASHBOARD_TOKEN: 'x'.repeat(32), STRATEGY_STYLE: 'both', STRATEGY_CADENCE: 'continuous', PROFIT_MANDATE: 'false', PACER: 'false', RATCHET: 'false' };
  const run = (holdExit: string) => { const c = loadConfig({ ...env, HOLD_EXIT: holdExit }); return runBacktest(dir, MetaModel.identity(), c.strategy, c.risk, 200, { exitPolicy: 'hold', fillLog: true }); };
  const off = await run('false');
  assert.deepEqual([off.exits.orders, off.exits.holdExits, off.exits.reentryBlocks], [0, 0, 0]);
  const on = await run('true');
  assert.ok(on.exits.holdExits! > 0, `hold exits ${on.exits.holdExits}`);
  const exitFills = (on.fillLog ?? []).filter((f) => f.coid?.includes('-exit-'));
  assert.ok(exitFills.length > 0 && exitFills.every((f) => f.coid!.endsWith('-exit-hold')), JSON.stringify(exitFills.map((f) => f.coid).slice(0, 5)));
  assert.ok(on.exits.reentryBlocks! > 0, 'the re-entry rule closed entry evaluations');
  // Synthetic markets: 15 minutes each, the first opening 600 s in. Every order that entered a market again after its hold exit,
  // or was placed on the evaluation that decided the sale (a replay second before it went out) or later, whenever it filled,
  // was placed while more than half of its window was left.
  const start = Date.parse('2026-01-01T00:00:00Z');
  const closeOf = (ticker: string) => start + (600 + 900 * Number(ticker.split('-')[1])) * 1000 + 900_000;
  const sold = new Map<string, number>();
  for (const f of on.fillLog ?? []) if (f.coid?.endsWith('-exit-hold') && !sold.has(f.ticker)) sold.set(f.ticker, f.t);
  let again = 0;
  for (const f of on.fillLog ?? []) {
    const at = sold.get(f.ticker);
    if (at === undefined || f.coid?.includes('-exit-')) continue;
    const placed = Number(/-(\d{13})-(?:bid|ask)-/.exec(f.coid ?? '')?.[1]);
    if (f.t < at && placed < at - 1000) continue;
    again++;
    assert.ok(closeOf(f.ticker) - placed > 450_000, `${f.coid}: placed ${(closeOf(f.ticker) - placed) / 1000} s before the close`);
  }
  assert.ok(again > 0, 'some markets were entered again in their first half');
});

test('replay: a hunt stop queued on the evaluation where the hold exit fires gives way to it, as the engine drops it', async () => {
  const dir = path.join(tmpDir(), 'rec');
  writeSyntheticRecordings(dir, { windows: 8, seed: 3, marketNoise: 0.05 });
  // EXIT_POLICY=confluence_ratchet with a hunt that starts easily and sells at the bid every tick once it has (the lock sale):
  // its stop and the hold exit meet on some evaluations. The quota snipe and the profit ratchet are off: every liquidation is
  // the hold exit's.
  const env = { DASHBOARD_TOKEN: 'x'.repeat(32), STRATEGY_STYLE: 'both', STRATEGY_CADENCE: 'continuous', PROFIT_MANDATE: 'false', PACER: 'false', RATCHET: 'false' };
  const run = (holdExit: string) => {
    const c = loadConfig({ ...env, HOLD_EXIT: holdExit });
    return runBacktest(dir, MetaModel.identity(), c.strategy, c.risk, 200, { exitPolicy: 'confluence_ratchet', fillLog: true, hunt: { targetMargin: 0.005, minConfluence: 0, lockSale: 'fair_value', lockSaleElse: 'exit', lockSaleAt: 'lock' } });
  };
  const on = await run('true');
  assert.ok(on.exits.huntYielded! > 0, `hunt stops that gave way: ${on.exits.huntYielded}`);
  assert.ok(on.exits.huntYielded! <= (on.fillLog ?? []).filter((f) => f.coid?.endsWith('-exit-hold')).length, 'each one a hold exit sent and filled instead');
  assert.equal((await run('false')).exits.huntYielded, 0);
});
