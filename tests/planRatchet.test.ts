// The plan's ratchet and its end rule (bot/plan/planRatchet.ts), its position registry (bot/plan/planPositions.ts) and the
// PLAN_RULES switch (bot/config.ts). Since Nov 11 (Steven, 8:53-8:58 AM EST / 13:53-13:58 UTC) the ratchet is the one profit
// ratchet (bot/strategy/profitRatchet.ts) in dollars for the whole position: arm at +$1.50 after both fees, stop at +$1.00
// then $0.50 under the best, never lowered. The plan keeps its own sale (the bid less 2 ticks, retries, the alert, gaps), its
// minute clock and its end rule.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { loadConfig } from '../bot/config';
import { PlanPositions, PLAN_TAG_UNFILLED_MS } from '../bot/plan/planPositions';
import {
  assertPlanStopNotLowered, freshPlanState, planEndWindow, planFeeFloorPrice, planMarkTried, planNetAt, planStep,
  type PlanRatchetSettings, type PlanRatchetState, type PlanStepInput, type PlanStepResult,
} from '../bot/plan/planRatchet';
import { shareWindowSec } from '../bot/strategy/fairValueStrategy';
import { tmpDir } from './helpers';

const T0 = Date.parse('2026-11-11T15:00:30Z'); // Nov 11, 10:00:30 AM EST
const TICK = 0.01;
const RATCHET: PlanRatchetSettings = { armUsd: 1.5, stopMinUsd: 1, trailUsd: 0.5, clock: 'tick' };
const DEFAULTS = { armUsd: 1.5, stopMinUsd: 1, trailUsd: 0.5 };

/** A plan position walked through a series of books: 10 YES bought at 0.40 (maker: no entry fee) unless `o` says otherwise.
 *  Its net after both fees, whole position: 0.42 +$0.02 (the fee floor price), 0.52 +$1.02, 0.56 +$1.42, 0.57 +$1.52,
 *  0.58 +$1.62, 0.60 +$1.83, 0.62 +$2.03, 0.65 +$2.34. */
class Walk {
  state: PlanRatchetState = freshPlanState();
  last!: PlanStepResult;
  readonly all: PlanStepResult[] = [];
  constructor(private readonly o: Partial<PlanStepInput> = {}) {}
  /** One evaluation at the held side's bid (YES held: the YES bid; NO held: the NO bid, so the YES ask is 1 - it). */
  at(sideBid: number, o: Partial<PlanStepInput> = {}): PlanStepResult {
    const position = o.position ?? this.o.position ?? 10;
    const book = position > 0 ? { bid: { price: sideBid, size: 50 }, ask: { price: Math.min(0.99, sideBid + 0.02), size: 50 } } : { bid: { price: Math.max(0.01, Math.round((1 - sideBid - 0.02) * 100) / 100), size: 50 }, ask: { price: Math.round((1 - sideBid) * 100) / 100, size: 50 } };
    this.last = planStep({
      ticker: 'KXBTC15M-T', side: position > 0 ? 'yes' : 'no', ruleId: 'dummy', position, ...book, entryPrice: 0.4, entryFeePerContract: 0, tick: TICK,
      now: T0, tauSec: 600, windowSec: 900, settings: RATCHET, ...this.o, ...o, state: this.state,
    });
    this.state = this.last.state;
    this.all.push(this.last);
    return this.last;
  }
  /** The sale went out (the engine and the replay call this once they send it): a gap it carries is listed. */
  sent(now = T0): void { this.state = planMarkTried(this.state, now, this.last.sale); }
  events(name?: string) { return this.all.flatMap((r) => r.events).filter((e) => !name || e.event === name); }
}

test('fee floor price: the lowest tick whose net after both fees is at least 0; net counts the entry fee and the taker exit fee on the whole position', () => {
  // 10 YES at 0.40, no entry fee: at 0.41 the 17c taker fee on 10 leaves -0.7c a contract; at 0.42 (18c fee) +0.2c.
  assert.equal(Math.round(planNetAt(10, 0.41, 0.4, 0) * 1e4) / 1e4, -0.007);
  assert.equal(Math.round(planNetAt(10, 0.42, 0.4, 0) * 1e4) / 1e4, 0.002);
  assert.equal(planFeeFloorPrice(10, 0.4, 0, TICK), 0.42);
  // A 1.8c entry fee a contract moves it to 0.44.
  assert.equal(planFeeFloorPrice(10, 0.4, 0.018, TICK), 0.44);
  // Against brute force over prices and sizes: net there >= 0, a tick lower < 0.
  for (const n of [1, 3, 10, 37, 100]) for (const c of [0.05, 0.2, 0.37, 0.5, 0.81, 0.95]) {
    const f = planFeeFloorPrice(n, c, 0.01, TICK);
    if (f === undefined) { assert.ok(planNetAt(n, 0.99, c, 0.01) < 0, `${n}@${c}`); continue; }
    assert.ok(planNetAt(n, f, c, 0.01) >= -1e-9 && planNetAt(n, Math.round((f - TICK) * 100) / 100, c, 0.01) < 0, `${n}@${c}: ${f}`);
  }
  assert.equal(planFeeFloorPrice(10, 0.99, 0, TICK), undefined, 'bought at 99c: nothing under $1 breaks even');
});

test('arm at +$1.50 after fees for the whole position: best = net, stop = max(+$1.00, best - $0.50); nothing before it', () => {
  const w = new Walk();
  // +$1.32 at 0.55 and +$1.42 at 0.56: under $1.50.
  w.at(0.55); w.at(0.56);
  assert.equal(w.state.armed, false);
  assert.equal(w.events().length, 0);
  assert.match(w.last.notes.join(' | '), /plan ratchet: net \+\$1\.42, arms at \+\$1\.50 \(tick clock\)/);
  // +$1.52 at 0.57: armed. best - trail is +$1.02, over the $1.00 minimum: the stop is +$1.02.
  w.at(0.57, { now: T0 + 1000 });
  assert.deepEqual([w.state.armed, w.state.armedAt, w.state.best, w.state.stop], [true, T0 + 1000, 1.52, 1.02]);
  const arm = w.events('plan_ratchet_arm');
  assert.equal(arm.length, 1);
  assert.deepEqual([arm[0].ticker, arm[0].side, arm[0].bid, arm[0].net, arm[0].stop, arm[0].feeFloor, arm[0].best, arm[0].limit, arm[0].at], ['KXBTC15M-T', 'yes', 0.57, 1.52, 1.02, 0.42, 1.52, null, T0 + 1000]);
  assert.deepEqual([arm[0].armUsd, arm[0].stopMinUsd, arm[0].trailUsd], [1.5, 1, 0.5]);
  assert.equal(w.last.sale, undefined);
  // A wider trail ($1.00 under +$1.52): the stop starts at its +$1.00 minimum.
  const wide = new Walk({ settings: { ...RATCHET, trailUsd: 1 } });
  wide.at(0.57);
  assert.deepEqual([wide.state.armed, wide.state.stop], [true, 1]);
});

test('raise-only trail: the stop follows the best net less $0.50 and is never lowered; at or under it the whole position sells at the bid less 2 ticks', () => {
  const w = new Walk();
  w.at(0.57);
  w.at(0.62);
  assert.deepEqual([w.state.best, w.state.stop], [2.03, 1.53]);
  assert.deepEqual(w.events('plan_ratchet_raise').map((e) => [e.prevStop, e.stop, e.best]), [[1.02, 1.53, 2.03]]);
  // Back to 0.60 (+$1.83) and 0.58 (+$1.62): above the stop, held; the stop stays at +$1.53 and no raise is reported.
  for (const b of [0.6, 0.58]) { w.at(b); assert.equal(w.last.sale, undefined); assert.equal(w.state.stop, 1.53); }
  assert.equal(w.events('plan_ratchet_raise').length, 1);
  // 0.57 (+$1.52): at or under the stop. One reduce-only sale of all 10 at 0.55 (YES sold at the ask side's limit).
  const r = w.at(0.57, { now: T0 + 9000 });
  assert.deepEqual([r.sale?.side, r.sale?.price, r.sale?.sideLimit, r.sale?.count, r.sale?.kind, r.sale?.ticks], ['ask', 0.55, 0.55, 10, 'ratchet', 2]);
  const sell = w.events('plan_ratchet_sell');
  assert.equal(sell.length, 1);
  assert.deepEqual([sell[0].bid, sell[0].stop, sell[0].limit, sell[0].net, sell[0].since, sell[0].at], [0.57, 1.53, 0.55, 1.52, T0 + 9000, T0 + 9000]);
  assert.ok(sell[0].net! >= 0, 'an armed sale at or above the fee floor price is not below fees');
  assert.equal(w.events('plan_ratchet_gap').length, 0);
  assert.match(r.sale!.why, /^plan ratchet: net \+\$1\.52 at bid 0\.57 at or under its stop \+\$1\.53 \(best \+\$2\.03\); limit 0\.55 \(bid less 2 ticks\)$/);
  assert.throws(() => assertPlanStopNotLowered(1.53, 1.52), /stop lowered/);
  assert.doesNotThrow(() => assertPlanStopNotLowered(1.53, 1.53));
});

test('the stop never drops: on any walk of the bid, armed stops only rise and stay at or above the fee break-even', () => {
  let seed = 7;
  const rand = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
  for (let run = 0; run < 40; run++) {
    const armUsd = Math.round((0.5 + rand() * 2) * 100) / 100;
    const settings: PlanRatchetSettings = { armUsd, stopMinUsd: Math.round(rand() * 0.9 * armUsd * 100) / 100, trailUsd: Math.round((0.1 + rand() * 1.2) * 100) / 100, clock: 'tick' };
    const w = new Walk({ settings });
    let bid = 0.45;
    let prev: number | undefined;
    for (let i = 0; i < 300 && !w.state.selling; i++) {
      bid = Math.min(0.97, Math.max(0.03, Math.round((bid + (Math.floor(rand() * 5) - 2) * 0.01) * 100) / 100));
      w.at(bid, { now: T0 + i * 1000 });
      if (w.state.stop !== undefined) {
        assert.ok(prev === undefined || w.state.stop >= prev - 1e-9, `run ${run}: stop ${prev} -> ${w.state.stop}`);
        // +$0.02: the net at the 0.42 fee floor price.
        assert.ok(w.state.stop >= Math.max(settings.stopMinUsd, 0.02) - 1e-9, `run ${run}: stop ${w.state.stop} under its minimum or the fee break-even`);
        prev = w.state.stop;
      }
    }
    // Every armed sale is at or above the fee floor price, or listed as a gap with its shortfall.
    for (const s of w.events('plan_ratchet_sell')) {
      const gaps = w.events('plan_ratchet_gap');
      assert.ok(s.bid! >= 0.42 - 1e-9 || gaps.some((g) => g.at === s.at && g.shortfallC === Math.round((0.42 - s.bid!) * 1e4) / 100), `run ${run}: ${JSON.stringify(s)}`);
    }
  }
});

test('never below the fee break-even: with no stop minimum and a wide trail the stop holds at the net of the fee floor price, and sells there in profit after fees', () => {
  const w = new Walk({ settings: { armUsd: 1.5, stopMinUsd: 0, trailUsd: 3, clock: 'tick' } });
  w.at(0.57); w.at(0.6);
  assert.equal(w.state.stop, 0.02, 'best +$1.83 less $3 is under $0: the break-even holds it at +$0.02, the net at the 0.42 fee floor price');
  w.at(0.43);
  assert.equal(w.last.sale, undefined);
  const r = w.at(0.42);
  assert.equal(r.sale?.sideLimit, 0.4);
  const sell = w.events('plan_ratchet_sell')[0];
  assert.ok(sell.net! >= 0, `net ${sell.net}`);
  assert.equal(w.events('plan_ratchet_gap').length, 0);
});

test('a price gap under the fee floor still sells, and the gap is listed with its shortfall', () => {
  const w = new Walk();
  w.at(0.57); w.at(0.6);
  assert.equal(w.state.stop, 1.33);
  // 0.60 straight to 0.38: 4c under the 0.42 fee floor price.
  const r = w.at(0.38, { now: T0 + 5000 });
  assert.deepEqual([r.sale?.side, r.sale?.price, r.sale?.kind], ['ask', 0.36, 'ratchet']);
  const gap = w.events('plan_ratchet_gap');
  assert.equal(gap.length, 1);
  assert.deepEqual([gap[0].bid, gap[0].feeFloor, gap[0].shortfallC, gap[0].net, gap[0].limit, gap[0].at], [0.38, 0.42, 4, -0.37, 0.36, T0 + 5000]);
  assert.equal(w.events('plan_ratchet_sell').length, 1);
  // The state lists the gap once the try goes out (the engine's planRecord, the replay's fireExit).
  assert.deepEqual(w.state.gaps, []);
  w.sent(T0 + 5000);
  assert.deepEqual(w.state.gaps, [{ at: T0 + 5000, bid: 0.38, feeFloor: 0.42, shortfallC: 4, net: -0.37 }]);
});

test('minute clock: arm, raise and sell only on the first evaluation after each minute close; the end rule every evaluation', () => {
  const w = new Walk({ settings: { ...RATCHET, clock: 'minute' } });
  const minute = (k: number, s: number) => Date.parse('2026-11-11T15:00:00Z') + k * 60_000 + s * 1000;
  // 15:00:30 (10:00:30 AM EST): first sighting at +$1.52; the decision waits for the minute close.
  w.at(0.57, { now: minute(0, 30) });
  w.at(0.58, { now: minute(0, 59) });
  assert.equal(w.state.armed, false);
  // 15:01:00.5: the first evaluation after the close arms.
  w.at(0.58, { now: minute(1, 0.5) });
  assert.deepEqual([w.state.armed, w.state.armedAt, w.state.best], [true, minute(1, 0.5), 1.62]);
  // Inside the minute nothing is decided: a new best is not taken, a net under the stop is not sold.
  w.at(0.65, { now: minute(1, 20) });
  assert.equal(w.state.best, 1.62);
  w.at(0.52, { now: minute(1, 40) });
  assert.equal(w.last.sale, undefined);
  // 15:02:01: the decision sells at that evaluation's bid (+$1.02 under the +$1.12 stop).
  const r = w.at(0.52, { now: minute(2, 1) });
  assert.deepEqual([r.sale?.kind, r.sale?.sideLimit], ['ratchet', 0.5]);
  assert.equal(w.events('plan_ratchet_sell')[0].at, minute(2, 1));
  // The end rule does not wait for the clock: a loser at 90 s to the close of a 15-minute window, mid-minute.
  const e = new Walk({ settings: { ...RATCHET, clock: 'minute' } });
  e.at(0.45, { now: minute(0, 10), tauSec: 120 });
  assert.equal(e.last.sale, undefined);
  const end = e.at(0.38, { now: minute(0, 40), tauSec: 90 });
  assert.equal(end.sale?.kind, 'end');
});

test('retries: a try that leaves the position open fails and goes again; at 3 failed tries an alert and the bid less 3 ticks', () => {
  const w = new Walk();
  w.at(0.57); w.at(0.62);
  assert.equal(w.at(0.57).sale?.sideLimit, 0.55);
  w.sent(T0 + 1);
  // An order still working is waited for: neither a failure nor a new try.
  const wait = w.at(0.57, { orderInFlight: true });
  assert.deepEqual([wait.sale, w.state.failedTries], [undefined, 0]);
  // Still held at the next evaluation: failed try 1, retried at the bid less 2 ticks; the net back above the stop does not
  // call the sale off.
  const tries: Array<[number, number | undefined, string | undefined]> = [];
  for (const b of [0.6, 0.56, 0.55, 0.54, 0.54]) {
    const r = w.at(b);
    tries.push([w.state.failedTries, r.sale?.sideLimit, r.alert]);
    w.sent();
  }
  assert.deepEqual(tries.map((t) => t.slice(0, 2)), [[1, 0.58], [2, 0.54], [3, 0.52], [4, 0.51], [5, 0.51]]);
  assert.match(tries[2][2] ?? '', /^Plan ratchet sale of 10 YES in KXBTC15M-T: 3 failed tries; now selling at the bid less 3 ticks$/);
  assert.deepEqual(tries.map((t) => Boolean(t[2])), [false, false, true, false, false], 'one alert');
  assert.deepEqual(w.events('plan_ratchet_retry').map((e) => [e.failedTries, e.limit]), [[1, 0.58], [2, 0.54], [3, 0.52], [4, 0.51], [5, 0.51]]);
  assert.equal(w.state.selling?.tries, 6);
  // A sale that did not go out (the kill switch's 30 s throttle) is not a failed try.
  const k = new Walk();
  k.at(0.57); k.at(0.62); k.at(0.57);
  k.at(0.57);
  assert.equal(k.state.failedTries, 0);
  assert.equal(k.last.sale?.sideLimit, 0.55);
  assert.deepEqual(k.events('plan_ratchet_retry').map((e) => [e.resend, e.failedTries]), [[true, 0]]);
  // A third failure counted while the held side has no bid: the alert goes with the next try that has one.
  const nb = new Walk();
  nb.at(0.57); nb.at(0.62); nb.at(0.57); nb.sent();
  for (const b of [0.57, 0.57]) { assert.equal(nb.at(b).alert, undefined); nb.sent(); }
  const none = planStep({ ticker: 'KXBTC15M-T', side: 'yes', ruleId: 'dummy', position: 10, bid: undefined, ask: { price: 0.6, size: 50 }, entryPrice: 0.4, entryFeePerContract: 0, tick: TICK, now: T0, tauSec: 600, windowSec: 900, settings: RATCHET, state: nb.state });
  assert.deepEqual([none.sale, none.alert, none.state.failedTries], [undefined, undefined, 3]);
  nb.state = none.state;
  const next = nb.at(0.56);
  assert.deepEqual([next.sale?.sideLimit, next.sale?.ticks], [0.53, 3]);
  assert.match(next.alert ?? '', /3 failed tries; now selling at the bid less 3 ticks/);
  // The limit is never below 1 tick: 10 bought at 0.01, armed at 0.20 (+$1.78), raised at 0.25 (+$2.26), sold at 0.02.
  const low = new Walk({ entryPrice: 0.01 });
  low.at(0.2); low.at(0.25);
  assert.equal(low.at(0.02).sale?.sideLimit, 0.01);
});

test('a retry whose bid fell under the fee floor price is listed as a gap, as a first try would be', () => {
  // 10 YES at 0.40 (fee floor price 0.42): armed at 0.57, stop +$1.53 after 0.62. The first try, at 0.57, is not a gap.
  const w = new Walk();
  w.at(0.57); w.at(0.62);
  w.at(0.57, { now: T0 + 1000 });
  assert.deepEqual(w.events('plan_ratchet_gap'), []);
  w.sent(T0 + 1000);
  // It did not fill, and the bid is 0.36 at the next evaluation: the retry sells at 0.34, 6c under the fee floor price.
  const r = w.at(0.36, { now: T0 + 2000 });
  assert.deepEqual([r.sale?.kind, r.sale?.sideLimit], ['ratchet', 0.34]);
  assert.deepEqual(w.events('plan_ratchet_gap').map((e) => [e.bid, e.feeFloor, e.shortfallC, e.net, e.limit, e.at, e.resend]), [[0.36, 0.42, 6, -0.57, 0.34, T0 + 2000, undefined]]);
  w.sent(T0 + 2000);
  assert.deepEqual(w.state.gaps.map((x) => [x.bid, x.shortfallC]), [[0.36, 6]]);
  // And on to the escalated try (3 failed: the bid less 3 ticks).
  for (const [k, b] of [[3, 0.35], [4, 0.34]] as const) { w.at(b, { now: T0 + k * 1000 }); w.sent(T0 + k * 1000); }
  assert.equal(w.last.sale?.ticks, 3);
  assert.deepEqual(w.state.gaps.map((x) => [x.bid, x.shortfallC]), [[0.36, 6], [0.35, 7], [0.34, 8]]);
  assert.equal(w.events('plan_ratchet_gap').length, 3);
});

test('a sale decided but never sent (the kill switch\'s throttle, a refusal) goes again as a resend: no failed try, and its gap is listed only once it goes', () => {
  const w = new Walk();
  w.at(0.57); w.at(0.62);
  // Decided at 0.57 (under the +$1.53 stop), held back (not marked as sent); at the next evaluation the bid is 0.40, under the
  // fee floor.
  w.at(0.57, { now: T0 + 1000 });
  const r = w.at(0.4, { now: T0 + 2000 });
  assert.deepEqual([r.sale?.sideLimit, w.state.failedTries, w.state.selling?.tries], [0.38, 0, 0]);
  assert.deepEqual(w.events('plan_ratchet_retry').map((e) => [e.resend, e.failedTries, e.limit, e.since, e.at]), [[true, 0, 0.38, T0 + 1000, T0 + 2000]]);
  assert.deepEqual(w.events('plan_ratchet_gap').map((e) => [e.resend, e.shortfallC, e.limit]), [[true, 2, 0.38]]);
  const listed = (x: PlanRatchetState) => x.gaps.map((g) => g.bid);
  assert.deepEqual(listed(w.state), [], 'not listed before it goes out');
  w.sent(T0 + 2000);
  assert.deepEqual([w.state.selling?.tries, listed(w.state)], [1, [0.4]]);
  // A try that went out and failed is a retry, not a resend.
  w.at(0.4, { now: T0 + 3000 });
  assert.deepEqual(w.events('plan_ratchet_retry').map((e) => [e.resend ?? false, e.failedTries]), [[true, 0], [false, 1]]);
});

test('end rule: a try that failed is called off once the position is back in profit after fees, so a retry never sells a winner', () => {
  const w = new Walk();
  // 10 YES at 0.40, 90 s to the close of a 15-minute window, bid 0.38 (-$0.37 after fees): sold at 0.36. It did not fill.
  assert.equal(w.at(0.38, { tauSec: 90, now: T0 }).sale?.kind, 'end');
  w.sent(T0);
  // 85 s: the bid is back at 0.47 (+$0.52 after both fees): no sale; the end rule's sale is called off and the position rides.
  const r = w.at(0.47, { tauSec: 85, now: T0 + 5000 });
  assert.equal(r.sale, undefined);
  assert.equal(w.state.selling, undefined);
  assert.equal(w.state.failedTries, 1, 'the try that failed still counts');
  assert.deepEqual(w.events('plan_end_rule_cancel').map((e) => [e.bid, e.net, e.limit, e.failedTries, e.since, e.at]), [[0.47, 0.52, null, 1, T0, T0 + 5000]]);
  assert.deepEqual(w.events('plan_ratchet_retry'), []);
  assert.match(r.notes.join(' | '), /^plan end rule: back in profit after fees \(net \+\$0\.52 at bid 0\.47\): its sale is called off \| .* \| plan end rule: 85 s to the close, in profit after fees: rides$/);
  // Under water again at 80 s: a new end-rule sale.
  assert.equal(w.at(0.39, { tauSec: 80, now: T0 + 10_000 }).sale?.kind, 'end');
  assert.equal(w.events('plan_end_rule_sell').length, 2);
  // Exactly break-even after fees (0.42) is not out of profit: called off too.
  w.sent(T0 + 10_000);
  assert.equal(w.at(0.42, { tauSec: 75, now: T0 + 15_000 }).sale, undefined);
  assert.equal(w.events('plan_end_rule_cancel').length, 2);
  // A ratchet sale is not called off by a bounce (its retries go on: see the retries test above).
});

test('NO side: the held side\'s bid is 1 - the YES ask; the sale buys YES at 1 - (NO bid less 2 ticks)', () => {
  // 10 NO bought at 0.40 (YES sold at 0.60). The NO bid 0.57 (YES ask 0.43): +$1.52, armed.
  const w = new Walk({ position: -10 });
  w.at(0.56);
  assert.equal(w.state.armed, false);
  w.at(0.57);
  assert.deepEqual([w.state.armed, w.state.best, w.state.stop], [true, 1.52, 1.02]);
  assert.equal(w.events('plan_ratchet_arm')[0].side, 'no');
  // The NO bid 0.65: +$2.34, the stop +$1.84; back to 0.58 (+$1.62): sold.
  w.at(0.65);
  assert.equal(w.state.stop, 1.84);
  const r = w.at(0.58);
  assert.deepEqual([r.sale?.side, r.sale?.price, r.sale?.sideLimit, r.sale?.count], ['bid', 0.44, 0.56, 10]);
  assert.match(r.sale!.why, /limit NO 0\.56 \(bid less 2 ticks\)/);
});

test('end rule: in the last tenth of the window a loser is sold the same way, a winner rides', () => {
  // A 15-minute window: 90 s.
  assert.deepEqual([planEndWindow(91, 900), planEndWindow(90, 900), planEndWindow(5, 900)], [false, true, true]);
  // An hourly listed a day before it closes is measured on its last hour (STRATEGY_SHARE_WINDOW_MAX_SEC): 6 minutes.
  const close = T0 + 3_600_000;
  assert.equal(shareWindowSec(close - 86_400_000, close, 3600), 3600);
  assert.deepEqual([planEndWindow(361, 3600), planEndWindow(360, 3600)], [false, true]);
  // 10 YES at 0.40, bid 0.38: -$0.37 after fees. At 100 s to the close: held. At 90 s: sold at 0.36.
  const w = new Walk();
  assert.equal(w.at(0.38, { tauSec: 100 }).sale, undefined);
  const r = w.at(0.38, { tauSec: 90, now: T0 + 10_000 });
  assert.deepEqual([r.sale?.kind, r.sale?.side, r.sale?.price, r.sale?.count], ['end', 'ask', 0.36, 10]);
  const e = w.events('plan_end_rule_sell');
  assert.deepEqual([e.length, e[0].bid, e[0].net, e[0].limit, e[0].tauSec, e[0].at], [1, 0.38, -0.37, 0.36, 90, T0 + 10_000]);
  // Its retries follow the same rule as the ratchet's.
  w.sent();
  assert.equal(w.at(0.37, { tauSec: 89 }).sale?.kind, 'end');
  assert.equal(w.state.failedTries, 1);
  // A winner (+$0.22 at 0.44, not armed) rides through the end window, to the last second.
  const win = new Walk();
  for (const tau of [90, 30, 1]) assert.equal(win.at(0.44, { tauSec: tau }).sale, undefined);
  assert.match(win.last.notes.join(' | '), /plan end rule: 1 s to the close, in profit after fees: rides/);
  // Exactly break-even is not out of profit.
  assert.equal(new Walk().at(0.42, { tauSec: 30 }).sale, undefined);
  // The ratchet keeps running in the end window and in the final seconds: an armed winner falling to its stop is sold.
  const armed = new Walk();
  armed.at(0.57, { tauSec: 200 }); armed.at(0.62, { tauSec: 100 });
  assert.equal(armed.at(0.57, { tauSec: 20 }).sale?.kind, 'ratchet');
});

test('plan positions: tag with the default settings, read, clear when flat, reversed or never filled; the state survives a restart', () => {
  const dir = tmpDir();
  const file = path.join(dir, 'plan_positions.json');
  const reg = new PlanPositions(DEFAULTS, file);
  const p = reg.tag({ ticker: 'A', side: 'yes', ruleId: 'heat-btc-15m' }, T0);
  assert.deepEqual([p.side, p.ruleId, p.openedAt, p.settings], ['yes', 'heat-btc-15m', T0, { armUsd: 1.5, stopMinUsd: 1, trailUsd: 0.5, clock: 'tick' }]);
  assert.deepEqual(reg.tag({ ticker: 'B', side: 'no', ruleId: 'r2', settings: { armUsd: 2, clock: 'minute' } }, T0).settings, { armUsd: 2, stopMinUsd: 1, trailUsd: 0.5, clock: 'minute' });
  // A tag made before its entry fills waits for it (flat but never seen open), up to 5 minutes.
  assert.equal(reg.sync('A', 0, T0 + 1000), undefined);
  assert.ok(reg.get('A'), 'not cleared before its entry filled');
  assert.equal(reg.sync('A', 10, T0 + 2000)?.ruleId, 'heat-btc-15m');
  // The ratchet's state is saved and read back by a new registry (a restart).
  const armed: PlanRatchetState = { ...freshPlanState(), armed: true, armedAt: T0 + 3000, best: 2.03, stop: 1.53, failedTries: 1, gaps: [{ at: T0, bid: 0.38, feeFloor: 0.42, shortfallC: 4, net: -0.37 }], selling: { kind: 'ratchet', since: T0 + 4000, tries: 1, lastTryAt: T0 + 4000 } };
  reg.setState('A', armed);
  const again = new PlanPositions(DEFAULTS, file);
  assert.deepEqual(again.get('A')?.state, armed);
  assert.deepEqual([again.get('A')?.seenOpen, again.get('B')?.settings.clock], [true, 'minute']);
  // Flat after it was open: cleared, on disk too.
  assert.equal(again.sync('A', 0, T0 + 5000), undefined);
  assert.equal(again.get('A'), undefined);
  assert.equal(new PlanPositions(DEFAULTS, file).get('A'), undefined);
  // Reversed to the other side: cleared.
  again.sync('B', -5, T0);
  assert.equal(again.sync('B', 3, T0), undefined);
  assert.equal(again.get('B'), undefined);
  // Never filled: dropped after 5 minutes.
  again.tag({ ticker: 'C', side: 'yes', ruleId: 'r3' }, T0);
  again.sync('C', 0, T0 + PLAN_TAG_UNFILLED_MS);
  assert.ok(again.get('C'));
  again.sync('C', 0, T0 + PLAN_TAG_UNFILLED_MS + 1);
  assert.equal(again.get('C'), undefined);
  // A fill leaving the market flat clears a tag that was open (the engine's and the replay's fill handlers call this).
  again.tag({ ticker: 'D', side: 'yes', ruleId: 'r4' }, T0);
  again.flat('D');
  assert.ok(again.get('D'), 'never open: kept for its entry');
  again.sync('D', 4, T0);
  again.flat('D');
  assert.equal(again.get('D'), undefined);
  // The position before the flattening fill shows it was open on the tag's side (PLAN_RULES off: no evaluation saw it).
  again.tag({ ticker: 'F', side: 'no', ruleId: 'r6' }, T0);
  again.flat('F', 3);
  assert.ok(again.get('F'), 'a YES position before the fill is not the NO tag\'s');
  again.flat('F', -3);
  assert.equal(again.get('F'), undefined);
  // In memory without a file (the replay).
  const mem = new PlanPositions(DEFAULTS);
  mem.tag({ ticker: 'E', side: 'yes', ruleId: 'r5' }, T0);
  assert.equal(mem.get('E')?.ruleId, 'r5');
  assert.deepEqual(fs.readdirSync(dir).filter((f) => !f.startsWith('plan_positions.json')), []);
});

test('plan positions: a file saved before the dollar ratchet keeps its tags with today\'s settings and a fresh ratchet (its floor was a price)', () => {
  const file = path.join(tmpDir(), 'plan_positions.json');
  fs.writeFileSync(file, JSON.stringify({ v: 1, positions: [{ ticker: 'A', side: 'yes', ruleId: 'r1', openedAt: T0, seenOpen: true, settings: { armC: 6, trailC: 8, clock: 'minute' }, state: { armed: true, armedAt: T0, peakBid: 0.55, floor: 0.47, failedTries: 0, gaps: [] } }] }));
  const p = new PlanPositions(DEFAULTS, file).get('A');
  assert.deepEqual([p?.ruleId, p?.seenOpen, p?.settings, p?.state], ['r1', true, { armUsd: 1.5, stopMinUsd: 1, trailUsd: 0.5, clock: 'minute' }, freshPlanState()]);
});

test('plan positions: a second tag on a plan position open on the same side keeps it, its armed stop and settings; the other side or a tag never filled is replaced', () => {
  const file = path.join(tmpDir(), 'plan_positions.json');
  const reg = new PlanPositions(DEFAULTS, file);
  reg.tag({ ticker: 'A', side: 'yes', ruleId: 'r1', settings: { trailUsd: 0.3 } }, T0);
  reg.sync('A', 10, T0 + 1000);
  const armed: PlanRatchetState = { ...freshPlanState(), armed: true, armedAt: T0 + 2000, best: 2.5, stop: 2.2 };
  reg.setState('A', armed);
  // The entry lane adds to it under another rule: the position keeps its tag (a fresh ratchet would drop the +$2.20 stop).
  const again = reg.tag({ ticker: 'A', side: 'yes', ruleId: 'r2' }, T0 + 3000);
  assert.deepEqual([again.ruleId, again.openedAt, again.settings, again.state], ['r1', T0, { armUsd: 1.5, stopMinUsd: 1, trailUsd: 0.3, clock: 'tick' }, armed]);
  assert.deepEqual(new PlanPositions(DEFAULTS, file).get('A')?.state, armed);
  // A tag whose entry was never seen open is replaced.
  reg.tag({ ticker: 'B', side: 'yes', ruleId: 'r1' }, T0);
  assert.equal(reg.tag({ ticker: 'B', side: 'yes', ruleId: 'r2' }, T0 + 1).ruleId, 'r2');
  // A tag on the other side replaces it.
  const other = reg.tag({ ticker: 'A', side: 'no', ruleId: 'r3' }, T0 + 4000);
  assert.deepEqual([other.side, other.ruleId, reg.get('A')?.state.armed], ['no', 'r3', false]);
});

test('PLAN_RULES: off by default in paper and live, read the same in both; cfg.plan is the strategy\'s; the plan ratchet takes the profit ratchet\'s dollars, and the retired cents settings stop the start', () => {
  const key = path.join(tmpDir(), 'k.pem');
  fs.writeFileSync(key, 'x', { mode: 0o600 });
  const envs = {
    paper: { DASHBOARD_TOKEN: 'x'.repeat(40) },
    live: { DASHBOARD_TOKEN: 'x'.repeat(40), TRADING_MODE: 'live', KALSHI_KEY_ID: 'id', KALSHI_PRIVATE_KEY_PATH: key, KALSHI_ENV: 'prod', LIVE_TRADING_ACKNOWLEDGED: 'I_ACCEPT_REAL_MONEY_RISK' },
  };
  for (const [mode, env] of Object.entries(envs)) {
    const off = loadConfig(env);
    assert.equal(off.mode, mode);
    assert.deepEqual(off.plan, { enabled: false }, mode);
    assert.equal(off.plan, off.strategy.plan);
    assert.deepEqual(off.strategy.profitRatchet, { enabled: true, armUsd: 1.5, stopMinUsd: 1, trailUsd: 0.5 }, mode);
    const on = loadConfig({ ...env, PLAN_RULES: 'true', RATCHET_ARM_USD: '2', RATCHET_TRAIL_USD: '0.75' });
    assert.deepEqual(on.strategy.plan, { enabled: true }, mode);
    assert.deepEqual(on.strategy.profitRatchet, { enabled: true, armUsd: 2, stopMinUsd: 1, trailUsd: 0.75 }, mode);
    // A cent a contract is a different amount on every position: the old settings are not read as something else.
    assert.throws(() => loadConfig({ ...env, PLAN_RATCHET_ARM_C: '5' }), /PLAN_RATCHET_ARM_C is retired: the ratchet is in dollars for the whole position/);
    assert.throws(() => loadConfig({ ...env, PLAN_RATCHET_TRAIL_C: '10' }), /PLAN_RATCHET_TRAIL_C is retired/);
  }
  assert.throws(() => loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), PLAN_RULES: 'yes' }), /PLAN_RULES=yes must be true or false/);
});
