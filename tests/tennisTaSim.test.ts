import assert from 'node:assert/strict';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { test } from 'node:test';
import { loadConfig, paperEnv } from '../bot/config';
import { orderFee, type FeeSchedule } from '../bot/fees';
import { OrderBook } from '../bot/marketdata/orderBook';
import { PositionBook } from '../bot/oms/positions';
import { HourlyQuotaPacer, QuotaFloors } from '../bot/risk/quotaPacer';
import { breakEvenExit, positionNetAtBid } from '../bot/strategy/fairValueStrategy';
import type { MatchMarket, TennisPlan } from '../bot/tennis/tennisStrategy';
import { buildHistoryReplay } from '../research/history/historyReplay';
import { ConfigSim, FEES, feedTimeline, PLACEBO_RESERVOIR, PlaceboReservoir, phaseLabel, RESYNC_WINDOW_MS, rng, runSweep, sigBits, type SimSpec } from '../research/tennisTaSim';
import type { MatchGrid } from '../research/tennisTaTypes';
import { comeback, writeRecordingLines, writeScriptedHistory, writeTaHistory, writeTaRecording, type RecordedFeed } from './tennisTaFixture';

const MIN = 60_000;
const LOOSE = { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0, TENNIS_ENTRY_MIN_SIGNALS_LIVE: 0, TENNIS_FAV_ENTRY_MIN_SIGNALS: 0 };
const T0 = Date.parse('2026-03-02T16:00:00Z');

async function replayDir(): Promise<string> {
  const hist = fs.mkdtempSync(path.join(os.tmpdir(), 'tta-')), out = path.join(hist, 'replay');
  writeTaHistory(hist);
  await buildHistoryReplay({ historyDir: hist, outDir: out, assets: [], fromDay: '2026-03-02', toDay: '2026-03-03', tennisSeries: ['KXATPMATCH'], log: () => {} });
  return out;
}

// ---- ConfigSim units: hand-built books, plans and prints -------------------------------------------------------------

const TK = 'KXATPMATCH-U1-A';
const bookOf = (bid: number, ask: number, size = 100, ts = 0) => { const b = new OrderBook(TK); b.applySnapshot({ bids: [{ price: bid, size }], asks: [{ price: ask, size }] }, ts); return b; };
const plan = (p: Partial<TennisPlan>): TennisPlan => ({ ticker: TK, side: 'bid', price: 0.2, count: 10, postOnly: true, reduceOnly: false, timeInForce: 'good_till_canceled', leg: 'underdog_entry', why: 'test', ...p });
const ioc = (p: Partial<TennisPlan>): TennisPlan => plan({ postOnly: false, timeInForce: 'immediate_or_cancel', leg: 'fav_entry', ...p });
const simOf = (fill: 'F0' | 'F1' | 'F2', overrides: SimSpec['overrides'] = {}, id = `u-${fill}`) => new ConfigSim({ id, overrides, fill });
const yes = (s: ConfigSim) => s.pos.get(TK)?.yes ?? 0;
/** Place at `now` and, under F1/F2, let the latency pass against `book`. */
function placeActive(s: ConfigSim, p: TennisPlan, book: OrderBook, now: number, activeBook = book): void {
  s.place(p, book, now, Infinity, 'E', 0.01);
  s.activateDue(now + s.latency, () => activeBook, () => 'E');
}
type FillOrder = Parameters<ConfigSim['fill']>[0];
const order = (side: 'bid' | 'ask', n: number, price: number, leg: TennisPlan['leg'] = side === 'bid' ? 'fav_entry' : 'fav_trail'): FillOrder =>
  ({ id: 0, ticker: TK, side, price, remaining: n, initial: n, postOnly: false, reduceOnly: side === 'ask', ioc: true, placedTs: 0, activeTs: 0, queueAhead: 0, expiry: Infinity, leg, entryCounted: false }) as FillOrder;

test('phase labels: pre, the first 20 live minutes, then progress terciles', () => {
  assert.equal(phaseLabel(undefined, 0, 0), 'pre');
  assert.equal(phaseLabel(0, 19 * MIN, 0.5), 'e20');
  assert.deepEqual([0.1, 0.5, 0.9].map((p) => phaseLabel(0, 30 * MIN, p)), ['p1', 'p2', 'p3']);
});

test('F1 fills a resting maker order only on a later print strictly through its price; F0 fills at the price once the queue is eaten', () => {
  for (const fill of ['F0', 'F1'] as const) {
    const s = simOf(fill);
    placeActive(s, plan({ price: 0.2 }), bookOf(0.19, 0.22), 1000);
    assert.equal(s.resting.get(TK)?.length, 1, `${fill}: the bid rests`);
    s.onTrade(TK, 0.2, 50, 'no', 5000, 'E');
    assert.equal(yes(s), fill === 'F0' ? 10 : 0, `${fill}: a print AT the price`);
  }
  const s = simOf('F1');
  placeActive(s, plan({ price: 0.2 }), bookOf(0.19, 0.22), 1000);
  s.onTrade(TK, 0.19, 4, 'no', 5000, 'E');
  assert.equal(yes(s), 4, 'a print through fills up to its size');
  s.onTrade(TK, 0.19, 50, 'yes', 5001, 'E');
  assert.equal(yes(s), 4, 'a YES-taker print never fills a resting bid');
  s.onTrade(TK, 0.18, 50, 'no', 5002, 'E');
  assert.equal(yes(s), 10);
  assert.equal(s.resting.get(TK), undefined, 'a filled order leaves the book');
});

test('F1: a print without a taker side never fills (F0 takes it)', () => {
  for (const fill of ['F0', 'F1'] as const) {
    const s = simOf(fill);
    placeActive(s, plan({ price: 0.2 }), bookOf(0.19, 0.22), 1000);
    s.onTrade(TK, 0.18, 50, undefined, 5000, 'E');
    assert.equal(yes(s), fill === 'F0' ? 10 : 0, fill);
  }
});

test('F1: an order acts 1 s after the decision; a print stamped before its activeTs never fills it', () => {
  const s = simOf('F1');
  s.place(plan({ price: 0.2 }), bookOf(0.19, 0.22), 1000, Infinity, 'E', 0.01);
  assert.equal(s.pending.length, 1);
  assert.equal(s.pending[0].activeTs, 2000);
  s.activateDue(1999, () => bookOf(0.19, 0.22), () => 'E');
  assert.equal(s.pending.length, 1, 'still in flight at activeTs - 1');
  s.activateDue(2000, () => bookOf(0.19, 0.22), () => 'E');
  assert.equal(s.resting.get(TK)?.length, 1);
  s.onTrade(TK, 0.18, 50, 'no', 1999, 'E');
  assert.equal(yes(s), 0, 'a print at activeTs - 1');
  s.onTrade(TK, 0.18, 50, 'no', 2000, 'E');
  assert.equal(yes(s), 10, 'a print at activeTs');
  const lat = simOf('F1', { HARNESS_LATENCY_MS: 500 });
  lat.place(plan({ price: 0.2 }), bookOf(0.19, 0.22), 1000, Infinity, 'E', 0.01);
  assert.equal(lat.pending[0].activeTs, 2500, 'HARNESS_LATENCY_MS adds to the latency');
});

test('post-only: rejected at placement when it would cross, and at activation when the market moved into it', () => {
  const s = simOf('F1');
  s.place(plan({ price: 0.22 }), bookOf(0.19, 0.22), 1000, Infinity, 'E', 0.01);
  assert.equal(s.pending.length, 0, 'crosses at placement');
  placeActive(s, plan({ price: 0.21 }), bookOf(0.19, 0.22), 1000, bookOf(0.19, 0.21));
  assert.equal(s.pending.length, 0);
  assert.equal(s.resting.get(TK), undefined, 'rejected at activation');
  assert.equal(yes(s), 0);
});

test('reduce-only: clamped to the position at placement and again at activation; never goes short', () => {
  const f0 = simOf('F0');
  placeActive(f0, ioc({ price: 0.22, count: 5 }), bookOf(0.19, 0.22), 1000);
  assert.equal(yes(f0), 5);
  placeActive(f0, ioc({ side: 'ask', price: 0.19, count: 10, reduceOnly: true, leg: 'end_cut' }), bookOf(0.19, 0.22), 2000);
  assert.equal(yes(f0), 0, 'sold 5 of a 10-lot plan');
  assert.equal(f0.pos.get(TK)!.netCash, -5 * 0.22 + 5 * 0.19);
  const f1 = simOf('F1');
  placeActive(f1, ioc({ price: 0.22, count: 5 }), bookOf(0.19, 0.22), 1000);
  assert.equal(yes(f1), 5);
  f1.place(ioc({ side: 'ask', price: 0.19, count: 5, reduceOnly: true, leg: 'end_cut' }), bookOf(0.19, 0.22), 3000, Infinity, 'E', 0.01);
  f1.fill(order('ask', 3, 0.2), 3, 0.2, true, 'E', 3500); // the position shrank while the exit was in flight
  f1.activateDue(4000, () => bookOf(0.19, 0.22), () => 'E');
  assert.equal(yes(f1), 0, 'clamped to the 2 left');
});

test('an order whose book is not usable when it acts is dropped (no fill against a stale or invalidated book)', () => {
  const s = simOf('F1');
  s.place(ioc({ price: 0.22, count: 5 }), bookOf(0.19, 0.22), 1000, Infinity, 'E', 0.01);
  s.activateDue(2000, () => undefined, () => 'E');
  assert.equal(s.pending.length, 0);
  assert.equal(yes(s), 0);
  s.place(ioc({ price: 0.22, count: 5 }), undefined, 3000, Infinity, 'E', 0.01);
  assert.equal(s.pending.length, 0, 'nothing is placed without a usable book');
});

test('a spec with no overrides gets the profit rules exactly as bot/engine.ts builds them', () => {
  const cfg = loadConfig(paperEnv({}));
  const s = simOf('F1');
  const r = s.rulesAt(T0);
  assert.deepEqual(Object.keys(r).sort(), ['endEntryMargin', 'endLoserCut', 'floorMode', 'floorTicks', 'floors', 'loserStopFrac', 'pacerUsd', 'settleFrac']);
  assert.equal(r.pacerUsd, new HourlyQuotaPacer(cfg.strategy.pacer, T0).neededUsd(T0));
  assert.equal(r.settleFrac, cfg.tennis.settleFrac);
  assert.equal(r.endLoserCut, true);
  assert.equal(r.endEntryMargin, cfg.tennis.endEntryMargin);
  assert.equal(r.floorMode, cfg.strategy.pacer.floor);
  assert.equal(r.floorTicks, cfg.strategy.pacer.floorTicks);
  assert.ok(r.floors instanceof QuotaFloors);
  assert.equal(r.loserStopFrac, undefined);
  const off = simOf('F1', { HARNESS_PACER: 'off', TENNIS_END_LOSER_CUT: false, HARNESS_LOSER_STOP: 0.3 }).rulesAt(T0);
  assert.equal(off.pacerUsd, undefined, 'HARNESS_PACER=off');
  assert.equal(off.endLoserCut, false);
  assert.equal(off.loserStopFrac, 0.3);
  assert.equal(off.floorMode, cfg.strategy.pacer.floor, 'the floors are passed as production passes them');
  assert.throws(() => simOf('F1', { HARNESS_LOSER_CUT: false }), /HARNESS_LOSER_CUT/);
});

test('netAtBid, breakEven and avgEntry match the engine on the same fills (round-trip basis); costPer is the open lot only', () => {
  for (const mult of [1, 1.25]) {
    const s = simOf('F1', mult === 1 ? { HARNESS_LOSER_STOP: 0.3 } : { HARNESS_LOSER_STOP: 0.3, HARNESS_FEE_MULT: mult });
    const fees: FeeSchedule = { ...FEES, takerMultiplier: FEES.takerMultiplier * mult, makerMultiplier: FEES.makerMultiplier * mult };
    const book = new PositionBook();
    const fills: Array<[side: 'bid' | 'ask', n: number, px: number, taker: boolean]> = [['bid', 7, 0.33, false], ['bid', 3.5, 0.35, true], ['ask', 4, 0.41, true], ['ask', 6.5, 0.47, true], ['bid', 6, 0.45, false], ['bid', 2.25, 0.46, true]];
    const quotes: Array<[number, number]> = [[0.3, 0.32], [0.36, 0.38], [0.5, 0.52], [0.12, 0.14]];
    for (const [i, [side, n, px, taker]] of fills.entries()) {
      s.fill(order(side, n, px), n, px, taker, 'E', 1000 * (i + 1));
      book.applyFill({ ticker: TK, side, count: n, price: px, fee: orderFee(n, px, taker, fees) });
      const pos = book.get(TK)!;
      assert.equal(yes(s), pos.yes);
      for (const [b, a] of quotes) {
        const sim = s.held(TK, { price: b }, { price: a });
        if (!(pos.yes > 0)) { assert.equal(sim, undefined); continue; }
        // bot/engine.ts tennisTick, verbatim.
        const engine = {
          position: pos.yes, avgEntry: -pos.netCash / pos.yes,
          netAtBid: positionNetAtBid(pos.yes, (pos.fees - pos.netCash) / pos.yes, { price: b }, { price: a }, fees),
          breakEven: breakEvenExit(pos.yes, (pos.fees - pos.netCash) / pos.yes, fees),
        };
        assert.deepEqual({ position: sim!.position, avgEntry: sim!.avgEntry, netAtBid: sim!.netAtBid, breakEven: sim!.breakEven }, engine, `fill ${i} quote ${b}/${a} x${mult}`);
      }
    }
    // The re-entry's lot: its own cost (fees in), unlike the round trip that carries the first episode's profit.
    const p = s.pos.get(TK)!;
    const lotFees = orderFee(6, 0.45, false, fees) + orderFee(2.25, 0.46, true, fees);
    assert.ok(Math.abs(s.held(TK, undefined, undefined)!.costPer! - (6 * 0.45 + 2.25 * 0.46 + lotFees) / 8.25) < 1e-9);
    assert.ok((p.fees - p.netCash) / p.yes < s.held(TK, undefined, undefined)!.costPer! - 0.01, 'the round-trip basis is lower after a profitable episode');
  }
  // No positive lot cost (a lot that already took more than it cost): no costPer, so the loser stop cannot misfire.
  const s = simOf('F1', { HARNESS_LOSER_STOP: 0.3 });
  s.fill(order('bid', 10, 0.2), 10, 0.2, false, 'E', 1000);
  s.fill(order('ask', 5, 0.9), 5, 0.9, true, 'E', 2000);
  assert.equal(s.held(TK, { price: 0.5 }, { price: 0.52 })!.costPer, undefined);
  assert.equal(simOf('F1').held(TK, undefined, undefined), undefined);
  const off = simOf('F1');
  off.fill(order('bid', 10, 0.2), 10, 0.2, false, 'E', 1000);
  assert.equal(off.held(TK, { price: 0.5 }, { price: 0.52 })!.costPer, undefined, 'costPer only for the research loser stop');
});

test('the pacer is fed by the config\'s fills, settlements and dropped positions', () => {
  const s = simOf('F0');
  const need0 = s.rulesAt(T0).pacerUsd!;
  const realized = () => s.pacer!.status(T0 + 60_000).realized24hUsd;
  assert.equal(realized(), 0);
  placeActive(s, ioc({ price: 0.52, count: 10 }), bookOf(0.5, 0.52), T0 + 1000);
  assert.equal(realized(), 0, 'an entry credits nothing');
  placeActive(s, ioc({ side: 'ask', price: 0.7, count: 10, reduceOnly: true, leg: 'fav_trail' }), bookOf(0.7, 0.72), T0 + 2000);
  const p = s.pos.get(TK)!;
  assert.ok(Math.abs(realized() - (p.netCash - p.fees)) < 1e-3, `a profitable exit is credited (${realized()})`);
  const need1 = s.rulesAt(T0 + 3000).pacerUsd!;
  assert.ok(need1 < need0 - 1, `the hour's need falls after the exit (${need0} -> ${need1})`);
  // Settlement credits what the fills have not.
  const T2 = 'KXATPMATCH-U2-A';
  s.fill({ ...order('bid', 5, 0.4), ticker: T2 }, 5, 0.4, false, 'E2', T0 + 4000);
  const before = realized();
  s.settle(T2, 'yes', 'E2', T0 + 5000);
  assert.ok(Math.abs(realized() - before - (5 * 0.6 - orderFee(5, 0.4, false, FEES))) < 1e-3, 'settlement credited');
  // A match that never settles: its open position's realized P&L (the cost) reaches the pacer as a settlement would.
  const T3 = 'KXATPMATCH-U3-A';
  s.fill({ ...order('bid', 5, 0.4), ticker: T3 }, 5, 0.4, false, 'E3', T0 + 6000);
  const b3 = realized();
  s.finish('E3', [T3], '2026-03-02', true, T0 + 7000);
  assert.ok(Math.abs(realized() - b3 + 5 * 0.4 + orderFee(5, 0.4, false, FEES)) < 1e-3, 'the drop is debited');
  assert.equal(s.run('H').days[0].breaches, 1, 'and counted as a breach');
  assert.equal(simOf('F0', { HARNESS_PACER: 'off' }).pacer, undefined);
});

test('settlement audit: a position nobody judged since it opened is a breach (the verdict dies when a position goes flat or opens)', () => {
  const s = simOf('F0');
  placeActive(s, ioc({ price: 0.52, count: 5 }), bookOf(0.5, 0.52), 1000);
  s.rideOk.set(TK, true); // a decision in the last share found it in profit
  placeActive(s, ioc({ side: 'ask', price: 0.5, count: 5, reduceOnly: true, leg: 'quota_snipe' }), bookOf(0.5, 0.52), 2000);
  assert.equal(s.rideOk.has(TK), false, 'flat: the verdict is gone');
  s.rideOk.set(TK, true);
  placeActive(s, ioc({ price: 0.52, count: 5 }), bookOf(0.5, 0.52), 3000);
  assert.equal(s.rideOk.has(TK), false, 'reopened: no verdict until a decision judges it');
  s.settle(TK, 'yes', 'E', 4000);
  const T2 = 'KXATPMATCH-U1-B';
  s.fill({ ...order('bid', 5, 0.3), ticker: T2 }, 5, 0.3, false, 'E', 4500);
  s.rideOk.set(T2, true);
  s.settle(T2, 'no', 'E', 5000);
  s.finish('E', [TK, T2], '2026-03-02', false, 6000);
  const run = s.run('H');
  assert.equal(run.days[0].breaches, 1, 'only the unjudged one, though it won');
  assert.deepEqual(run.episodes.map((e) => [e.x, e.br ?? 0]), [['quota_snipe', 0], ['settle', 1], ['settle', 0]]);
});

test('coin placebo: never the reading it replaces; a whole past reading of another match, strictly earlier', () => {
  const ALL = { score: 4, momentum: true, flow: true, depth: true, crossMarket: true };
  const NONE = { score: 0, momentum: false, flow: false, depth: false, crossMarket: false };
  const s = new ConfigSim({ id: 'coin-unit', overrides: {}, fill: 'F1', placebo: 'coin' });
  const hook = (event: string) => s.tracker(event).signalHook!;
  assert.deepEqual(hook('E1')(ALL, 'E1-A', 0), NONE, 'empty reservoir: no signal, whatever the real reading');
  // E1's real signal fires at every evaluation, and its readings fill the reservoir: none is ever drawn for E1 itself.
  for (let t = 1; t < 400; t++) assert.deepEqual(hook('E1')(ALL, 'E1-A', t * 1000), NONE, `E1 at ${t} s`);
  assert.equal(s.placebo!.count, 399);
  // ...while another match draws them.
  assert.deepEqual(hook('E9')(NONE, 'E9-A', 500_000), ALL);
  const s2 = new ConfigSim({ id: 'coin-unit-2', overrides: {}, fill: 'F1', placebo: 'coin' });
  const h2 = (event: string) => s2.tracker(event).signalHook!;
  for (let t = 0; t < 100; t++) h2('E1')(NONE, 'E1-A', t * 1000);
  assert.deepEqual(h2('E2')(ALL, 'E2-A', 200_000), NONE, 'E2 fires only now: its own reading is not in the reservoir yet');
  assert.deepEqual(h2('E3')(NONE, 'E3-A', 200_000), NONE, 'nor for another match at the same instant (not strictly earlier)');
  assert.deepEqual(h2('E2')(NONE, 'E2-A', 200_001), NONE, 'nor later for its own match');
  // E1 draws only from E2 and E3; E2's single firing is now in the reservoir.
  let fired = 0;
  for (let k = 0; k < 400; k++) fired += +(h2('E1')(NONE, 'E1-A', 300_000 + k).score === 4);
  assert.ok(fired > 0 && fired < 400, `E1 drew E2's past firing ${fired}/400 times`);
  // Strictly earlier: a reading made at the same instant by another match is not drawn, even when it is the only one.
  const s3 = new ConfigSim({ id: 'coin-unit-3', overrides: {}, fill: 'F1', placebo: 'coin' });
  assert.deepEqual(s3.tracker('E2').signalHook!(ALL, 'E2-A', 200_000), NONE);
  assert.deepEqual(s3.tracker('E3').signalHook!(NONE, 'E3-A', 200_000), NONE, 'same instant');
  assert.deepEqual(s3.tracker('E3').signalHook!(NONE, 'E3-A', 200_001), ALL, 'a millisecond later it is the past');
  // Its own match never: a match that fired all along draws only the other match's (silent) readings, by either draw path.
  for (const others of [1, 10]) {
    const s4 = new ConfigSim({ id: `coin-unit-4-${others}`, overrides: {}, fill: 'F1', placebo: 'coin' });
    for (let t = 0; t < others; t++) s4.tracker('E5').signalHook!(NONE, 'E5-A', t);
    for (let t = 0; t < 300; t++) s4.tracker('E6').signalHook!(ALL, 'E6-A', 100 + t);
    for (let k = 0; k < 100; k++) assert.deepEqual(s4.tracker('E6').signalHook!(ALL, 'E6-A', 1000 + k), NONE, `E6 draw ${k} (${others} other readings)`);
  }
});

test('settlement audit verdict: production\'s ride rule on the progress of the tick (not the furthest), and a net above zero', () => {
  const s = simOf('F1');
  const now = Date.parse('2026-03-02T15:00:00Z');
  const mk = (net: number | undefined, pa = 0.6): MatchMarket[] => [
    { ticker: TK, position: 5, netAtBid: net, quote: { bid: pa - 0.01, ask: pa + 0.01 } },
    { ticker: 'KXATPMATCH-U1-B', position: 0, quote: { bid: 1 - pa - 0.01, ask: 1 - pa + 0.01 } },
  ];
  const tr = s.tracker('E');
  tr.observe({ event: 'E', now: now - 1000, startTime: now - 10 * MIN, markets: mk(1), closeTime: now + 3_600_000 });
  tr.progressHigh = 1; // the match was all but over before a comeback
  assert.ok(tr.progress(now, mk(1)) < 0.7);
  s.audit(tr, mk(1), now);
  assert.equal(s.rideOk.get(TK), false, 'early in the match by the progress of the tick: may not ride');
  // Two hours in, the price gone from 60c to 97c: the last share.
  const late = s.tracker('L');
  late.observe({ event: 'L', now: now - 60_000, startTime: now - 2 * 3_600_000, markets: mk(1), closeTime: now + 3_600_000 });
  late.observe({ event: 'L', now, startTime: now - 2 * 3_600_000, markets: mk(1, 0.97), closeTime: now + 3_600_000 });
  assert.ok(late.progress(now, mk(1, 0.97)) >= 0.7);
  for (const [net, ok] of [[1, true], [0, false], [-1, false], [undefined, false]] as const) {
    s.audit(late, mk(net, 0.97), now);
    assert.equal(s.rideOk.get(TK), ok, `last share, net ${net}`);
  }
  assert.equal(s.rideOk.has('KXATPMATCH-U1-B'), false, 'only held markets are judged');
});

test('coin placebo: the joint firing distribution is kept; the reservoir is bounded and seeded by the spec id', () => {
  const draws = (seed: number) => {
    const r = new PlaceboReservoir(rng(seed));
    const both = sigBits({ momentum: true, flow: true, depth: false, crossMarket: false });
    for (let t = 0; t < 10_000; t++) r.draw('E1', t, t % 2 ? both : 0);
    const out: number[] = [];
    for (let t = 0; t < 2000; t++) out.push(r.draw('E2', 10_000 + t, 0));
    return { out, count: r.count, both };
  };
  const a = draws(7);
  assert.equal(a.count, PLACEBO_RESERVOIR);
  assert.ok(a.out.every((b) => b === 0 || b === a.both), 'momentum and flow come together or not at all');
  const rate = a.out.filter((b) => b === a.both).length / a.out.length;
  assert.ok(Math.abs(rate - 0.5) < 0.06, `rate ${rate}`);
  assert.deepEqual(draws(7).out, a.out, 'deterministic');
  assert.notDeepEqual(draws(8).out, a.out);
});

// ---- Sweeps ----------------------------------------------------------------------------------------------------------

test('tennis TA sweep: configs in lock-step, per-match P&L over every match, episodes add up, F1 never fills more than F0', async () => {
  const dir = await replayDir();
  const specs: SimSpec[] = [
    { id: 'f0', overrides: { ...LOOSE }, fill: 'F0' },
    { id: 'f1', overrides: { ...LOOSE }, fill: 'F1' },
    { id: 'f2', overrides: { ...LOOSE }, fill: 'F2' },
    { id: 'coin', overrides: { ...LOOSE }, fill: 'F1', placebo: 'coin' },
    { id: 'nopacer', overrides: { ...LOOSE, HARNESS_PACER: 'off' }, fill: 'F1' },
    { id: 'prod', overrides: {}, fill: 'F1' },
  ];
  const grids: MatchGrid[] = [];
  await assert.rejects(runSweep({ dir, fromDay: '2026-03-02', toDay: '2026-03-02', stratum: 'H', specs }), /toDay/);
  const r = await runSweep({ dir, fromDay: '2026-03-02', toDay: '2026-03-03', stratum: 'H', specs, onGrid: (g) => grids.push(g) });
  assert.equal(r.matches, 3);
  assert.equal(r.matchList.length, 3);
  assert.ok(r.matchList.every((m) => m.trades > 100 && m.tickers.length === 2 && !m.unresolved && m.startPublished && m.resultA !== undefined));
  for (const run of r.runs) {
    assert.equal(run.pnl.length, 3, `${run.id}: one value per match`);
    const sumMatch = run.pnl.reduce((a, b) => a + b, 0);
    const sumDays = run.days.reduce((a, d) => a + d.pnl, 0);
    const sumEps = run.episodes.reduce((a, e) => a + e.pnl, 0);
    assert.ok(Math.abs(sumMatch - sumDays) < 1e-3, `${run.id}: matches ${sumMatch} vs days ${sumDays}`);
    assert.ok(Math.abs(sumMatch - sumEps) < 0.02, `${run.id}: matches ${sumMatch} vs episodes ${sumEps}`);
    for (const e of run.episodes) {
      assert.ok(e.m >= 0 && e.m < 3 && (e.k === 0 || e.k === 1), `${run.id}: episode indices`);
      assert.ok(['pre', 'e20', 'p1', 'p2', 'p3'].includes(e.ph));
      assert.ok(e.sig >= 0 && e.sig < 16);
    }
    // The end loser cut is on by default: nothing reaches settlement in breach.
    assert.equal(run.days.reduce((a, d) => a + d.breaches, 0), 0, `${run.id}: no breaches`);
  }
  const by = Object.fromEntries(r.runs.map((x) => [x.id, x]));
  const fills = (id: string) => by[id].days.reduce((a, d) => a + Object.values(d.legs).reduce((s, v) => s + v, 0), 0);
  const entries = (id: string) => by[id].days.reduce((a, d) => a + d.entries, 0);
  assert.ok(entries('f0') > 0, 'the loose config trades');
  assert.ok(entries('f1') <= entries('f0'), `F1 ${entries('f1')} entries vs F0 ${entries('f0')}`);
  assert.ok(fills('f1') > 0, 'F1 fills too');
  assert.notDeepEqual(by.f1.pnl, by.f0.pnl, 'F1 and F0 fill differently');
  // Grids: one per match, one sample a second, quotes where the book stood.
  assert.equal(grids.length, 3);
  for (const g of grids) {
    assert.ok(g.n > 3 * 3600 && g.n < 4 * 3600, `grid ${g.n} samples`);
    let quoted = 0;
    for (let i = 0; i < g.n; i++) if (Number.isFinite(g.bidA[i]) && Number.isFinite(g.askA[i])) { quoted++; assert.ok(g.askA[i] > g.bidA[i]); }
    assert.ok(quoted > 0.8 * g.n, `quoted ${quoted}/${g.n}`);
    assert.ok(g.liveIdx > 0 && g.progress[g.n - 1] > 0.5);
    assert.equal((g as MatchGrid & { startPublished?: boolean }).startPublished, true);
  }
  // The progress clock runs for every owned match without any config (family B alone), and gives the same grids.
  const alone: MatchGrid[] = [];
  const r0 = await runSweep({ dir, fromDay: '2026-03-02', toDay: '2026-03-03', stratum: 'H', specs: [], onGrid: (g) => alone.push(g) });
  assert.equal(r0.decisions, 0);
  assert.equal(alone.length, 3);
  for (const [i, g] of alone.entries()) {
    assert.equal(g.liveIdx, grids[i].liveIdx);
    assert.deepEqual([...g.progress], [...grids[i].progress]);
    assert.deepEqual([...g.bidA], [...grids[i].bidA]);
  }
  // Seeded: the placebo arm repeats exactly.
  const again = await runSweep({ dir, fromDay: '2026-03-02', toDay: '2026-03-03', stratum: 'H', specs: [specs[3]] });
  assert.deepEqual(again.runs[0].pnl, by.coin.pnl);
  assert.deepEqual(again.runs[0].episodes, by.coin.episodes);
});

test('tennis TA sweep: admit() keeps a match out of the pool, and its configs never see it', async () => {
  const dir = await replayDir();
  const r = await runSweep({ dir, fromDay: '2026-03-02', toDay: '2026-03-03', stratum: 'H', specs: [{ id: 'a', overrides: { ...LOOSE }, fill: 'F1' }], admit: (m) => m.event !== 'KXATPMATCH-M2' });
  assert.deepEqual(r.matchList.map((m) => m.event).sort(), ['KXATPMATCH-M1', 'KXATPMATCH-M3']);
  assert.equal(r.runs[0].pnl.length, 2);
  const none = await runSweep({ dir, fromDay: '2026-03-03', toDay: '2026-03-04', stratum: 'H', specs: [{ id: 'a', overrides: { ...LOOSE }, fill: 'F1' }] });
  assert.equal(none.matches, 0, 'owned starts are [fromDay, toDay)');
});

test('settlement audit on a comeback: the settle-hold stick holds the losing favorite into settlement (a breach); production cuts it', async () => {
  const hist = fs.mkdtempSync(path.join(os.tmpdir(), 'ttc-')), dir = path.join(hist, 'replay');
  writeScriptedHistory(hist, '2026-03-05', [
    { id: 'C1', winA: false, startHour: 10, p: comeback },
    // No published start: the price says when it began (a 4c drop 5 minutes in). Market B closes 30 minutes after A.
    { id: 'C2', winA: true, startHour: 15, p: (m) => (m < 5 ? 0.7 : Math.min(0.97, 0.66 + m * 0.002)), noStart: true, closeLaterB: 30 },
  ]);
  await buildHistoryReplay({ historyDir: hist, outDir: dir, assets: [], fromDay: '2026-03-05', toDay: '2026-03-06', tennisSeries: ['KXATPMATCH'], log: () => {} });
  const specs: SimSpec[] = [
    { id: 'cut', overrides: { ...LOOSE }, fill: 'F1' },
    { id: 'hold', overrides: { ...LOOSE, TENNIS_END_LOSER_CUT: false }, fill: 'F1' },
    { id: 'stop', overrides: { ...LOOSE, TENNIS_END_LOSER_CUT: false, HARNESS_LOSER_STOP: 0.3 }, fill: 'F1' },
  ];
  const grids: MatchGrid[] = [];
  const r = await runSweep({ dir, fromDay: '2026-03-05', toDay: '2026-03-06', stratum: 'H', specs, onGrid: (g) => grids.push(g) });
  assert.equal(r.matches, 2);
  const c1 = r.matchList.findIndex((m) => m.event === 'KXATPMATCH-C1'), c2 = r.matchList.findIndex((m) => m.event === 'KXATPMATCH-C2');
  assert.equal(r.matchList[c1].startPublished, true);
  assert.equal(r.matchList[c2].startPublished, false, 'no published start');
  const start2 = Date.parse('2026-03-05T15:00:00Z');
  assert.ok(r.matchList[c2].start < start2 - 60 * MIN, 'its start is the market line\'s time');
  assert.equal(r.matchList[c2].close, start2 + 180 * MIN, 'bookkeeping waits for the later close');
  const g2 = grids.find((g) => g.event === 'KXATPMATCH-C2')!;
  assert.ok(g2.t0 + g2.liveIdx * 1000 >= start2 + 5 * MIN, 'the strategy got no start: the match went live on its first move, not at the market line');
  assert.equal(g2.t0 + g2.closeIdx * 1000, start2 + 150 * MIN, 'the strategy\'s close is the earliest');
  const by = Object.fromEntries(r.runs.map((x) => [x.id, x]));
  const breaches = (id: string) => by[id].days.reduce((a, d) => a + d.breaches, 0);
  const fav = (id: string) => by[id].episodes.find((e) => e.m === c1 && e.leg === 'fav_entry')!;
  assert.ok(fav('hold') && fav('cut'), 'both buy the favorite in the middle of the match');
  assert.equal(fav('hold').x, 'settle');
  assert.equal(fav('hold').br, 1);
  assert.ok(breaches('hold') > 0 && fav('hold').pnl < -5, `the stick rides the loser to settlement (${fav('hold').pnl})`);
  assert.equal(fav('cut').x, 'end_cut');
  assert.equal(breaches('cut'), 0);
  assert.ok(fav('cut').pnl > fav('hold').pnl);
  assert.equal(fav('stop').x, 'loser_stop', 'the research loser stop fires on the lot\'s own cost');
  assert.equal(breaches('stop'), 0);
});

test('R: early-listed matches (lookback), lifecycle-only settlement; feed outages blank every book until its next snapshot', async () => {
  const specs: SimSpec[] = [{ id: 'prod', overrides: {}, fill: 'F1' }, { id: 'loose', overrides: { ...LOOSE }, fill: 'F1' }];
  // Which silences are outages: on a day that shows the feed's liveness (heartbeats, or a raw file's other markets) every
  // silence over 12 s; on a blind day (the tennis cut: tennis lines only) only one that a resubscribe ends.
  const cases: Array<{ feed: RecordedFeed; resync: boolean; gaps: number; blind: number; liveDays: number; blindDays: number }> = [
    { feed: 'hb', resync: false, gaps: 1, blind: 0, liveDays: 3, blindDays: 0 },
    { feed: 'raw', resync: false, gaps: 1, blind: 0, liveDays: 3, blindDays: 0 },
    { feed: 'hb', resync: true, gaps: 1, blind: 0, liveDays: 3, blindDays: 0 },
    { feed: 'none', resync: false, gaps: 0, blind: 0, liveDays: 0, blindDays: 2 },
    { feed: 'none', resync: true, gaps: 1, blind: 1, liveDays: 0, blindDays: 2 },
  ];
  const pnls: string[] = [];
  for (const c of cases) {
    const name = `${c.feed}${c.resync ? '+resync' : ''}`;
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ttr-'));
    const plan = writeTaRecording(dir, '2026-03-04', { feed: c.feed, resync: c.resync });
    const grids: MatchGrid[] = [];
    const r = await runSweep({ dir, fromDay: '2026-03-04', toDay: '2026-03-05', stratum: 'R', specs, onGrid: (g) => grids.push(g) });
    assert.equal(r.matches, 1, `${name}: the market line written two days before the start is read`);
    const m = r.matchList[0];
    assert.equal(m.event, plan.event);
    assert.equal(m.unresolved, false, `${name}: settled from the lifecycle lines alone`);
    assert.equal(m.resultA, 1);
    assert.equal(m.startPublished, true);
    assert.equal(r.unresolved, 0);
    assert.deepEqual([r.gaps, r.blindGaps, r.liveDays, r.blindDays], [c.gaps, c.blind, c.liveDays, c.blindDays], name);
    if (c.gaps) assert.ok(r.gapMs >= 10 * MIN && r.gapMs < 11 * MIN, `${name}: ${r.gapMs}`);
    assert.equal(r.lost, 0);
    for (const run of r.runs) {
      assert.equal(run.days[0].unresolved, 0);
      assert.ok(run.episodes.every((e) => e.x !== 'drop'), `${name} ${run.id}: nothing dropped`);
      assert.equal(run.days[0].breaches, 0);
    }
    assert.ok(r.runs.some((x) => x.episodes.some((e) => e.x === 'settle')), `${name}: a held favorite settles on the lifecycle line`);
    pnls.push(JSON.stringify(r.runs.map((x) => x.pnl)));
    assert.equal(grids.length, 1);
    const g = grids[0];
    const at = (t: number) => { const i = Math.floor((t - g.t0) / 1000); return [g.bidA[i], g.askA[i], g.bidB[i], g.askB[i]]; };
    const quoted = (t: number) => at(t).every(Number.isFinite);
    assert.equal(g.t0, plan.start - 3 * 3_600_000, 'the grid starts 3 h before the published start');
    // 45 h after the only snapshot, with no tennis line since: a quiet book on a live socket is current.
    assert.ok(quoted(g.t0 + 1000), `${name}: quoted at the grid's start`);
    assert.ok(quoted(plan.gapFrom - 10_000), `${name}: quoted before the silence`);
    assert.ok(quoted(plan.gapFrom + 5000), `${name}: production keeps a quiet book alive 12 s after the last message, then 5 s more`);
    assert.ok(quoted(plan.end - 60_000));
    const dead = (t: number, why: string) => assert.ok(!quoted(t), `${name}: stale at ${new Date(t).toISOString()} (${why})`);
    const ok = (t: number, why: string) => assert.ok(quoted(t), `${name}: quoted at ${new Date(t).toISOString()} (${why})`);
    if (!c.gaps) {
      // A blind day's silence that no resubscribe ends is a quiet market: the books stay usable through it.
      for (const t of [plan.gapFrom + 30_000, plan.gapFrom + 5 * MIN, plan.gapTo + 5000, plan.snapAgain - 1000]) ok(t, 'no outage');
      assert.equal(g.n, [...g.bidA].filter(Number.isFinite).length, `${name}: every second quoted`);
    } else {
      for (const t of [plan.gapFrom + 30_000, plan.gapFrom + 5 * MIN, plan.gapTo - 1000]) dead(t, 'in the outage');
      if (c.resync) for (const t of [plan.gapTo + 1000, plan.snapAgain - 1000]) ok(t, 'the resubscribe snapshots');
      else for (const t of [plan.gapTo + 5000, plan.snapAgain - 1000]) dead(t, 'deltas without a snapshot');
      ok(plan.snapAgain + 1000, 'usable again after the next snapshot');
    }
  }
  // The heartbeat and the raw file's other markets read the same feed; the strategy never sees them.
  assert.equal(pnls[0], pnls[1]);
  // Only a day before fromDay: the match's market line is lost, and the loss is counted.
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ttr-'));
  writeTaRecording(dir);
  const short = await runSweep({ dir, fromDay: '2026-03-04', toDay: '2026-03-05', stratum: 'R', specs, lookbackDays: 1 });
  assert.equal(short.matches, 0);
  assert.equal(short.lost, 2);
  // A match that began before fromDay is no loss, though the read meets its lines without their market line.
  const after = await runSweep({ dir, fromDay: '2026-03-05', toDay: '2026-03-06', stratum: 'R', specs, lookbackDays: 1 });
  assert.equal(after.matches, 0);
  assert.equal(after.lost, 0);
});

test('feedTimeline: a lone book re-snapshot (a sequence gap) after a blind silence is no outage; two are', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ttf-'));
  const T = Date.parse('2026-03-04T10:00:00Z');
  const tk = ['KXATPMATCH-F1-A', 'KXATPMATCH-F1-B'];
  const book = (t: number, ticker: string) => ({ t, k: 'book', ticker, bids: [{ price: 0.4, size: 10 }], asks: [{ price: 0.42, size: 10 }], ts: t });
  writeRecordingLines(dir, [
    book(T, tk[0]), book(T, tk[1]),
    // 60 s of silence, then one book re-snapshotted alone.
    { t: T + 60_000, k: 'delta', ticker: tk[0], side: 'bid', price: 0.4, delta: 1, ts: T + 60_000 }, book(T + 61_000, tk[1]),
    // 60 s more, then both re-snapshotted within the window: a resubscribe.
    { t: T + 120_000, k: 'trade', ticker: tk[0], price: 0.41, count: 1, takerSide: 'yes', ts: T + 120_000 }, book(T + 121_000, tk[0]), book(T + 130_000, tk[1]),
    // A silence ended by a delta, the snapshots of both books only after RESYNC_WINDOW_MS (the feed busy in between).
    ...[200_000, 206_000, 212_000].map((dt) => ({ t: T + dt, k: 'delta', ticker: tk[0], side: 'bid', price: 0.4, delta: 1, ts: T + dt })),
    book(T + 200_000 + RESYNC_WINDOW_MS + 1, tk[0]), book(T + 200_000 + RESYNC_WINDOW_MS + 2, tk[1]),
  ]);
  const f = await feedTimeline(dir, '2026-03-04', '2026-03-04');
  assert.deepEqual(f.blindDays, ['2026-03-04']);
  assert.deepEqual(f.gaps, [{ from: T + 61_000, to: T + 120_000, blind: true }]);
});

test('R: the strategy and the orders stop at the EARLIER close; a resting order on A expires at A\'s close - 1 s', async () => {
  // A (the 21c underdog) closes 5 minutes before the start, B a week later; the underdog bid rests on A from the
  // pre-start window. A print through it 1.5 s before A's close fills it; one 0.5 s before (or after) does not.
  const start = Date.parse('2026-03-04T12:00:00Z'), listed = start - 2 * 3_600_000, closeA = start - 5 * MIN, closeB = start + 7 * 86_400_000;
  const tk = ['KXATPMATCH-K1-A', 'KXATPMATCH-K1-B'];
  const specs: SimSpec[] = [{ id: 'loose', overrides: { ...LOOSE }, fill: 'F1' }];
  const runFor = async (printAt: number) => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ttk-'));
    writeRecordingLines(dir, [
      ...tk.map((ticker, i) => ({ t: listed, k: 'market', ticker, series: 'KXATPMATCH', kind: 'match', event: 'KXATPMATCH-K1', openTime: listed - 3_600_000, closeTime: i ? closeB : closeA, tickSize: 0.01, title: `Will K${i} win?`, startTime: start })),
      ...tk.map((ticker, i) => ({ t: listed + 1000, k: 'book', ticker, bids: [{ price: i ? 0.78 : 0.2, size: 500 }], asks: [{ price: i ? 0.8 : 0.22, size: 500 }], ts: listed + 1000 })),
      { t: printAt, k: 'trade', ticker: tk[0], price: 0.19, count: 500, takerSide: 'no', ts: printAt },
      { t: closeA + MIN, k: 'trade', ticker: tk[0], price: 0.18, count: 500, takerSide: 'no', ts: closeA + MIN },
      ...tk.map((ticker, i) => ({ t: start + 2 * 3_600_000, k: 'lifecycle', ticker, event: 'determined', result: i ? 'yes' : 'no', ts: start + 2 * 3_600_000 })),
    ]);
    return runSweep({ dir, fromDay: '2026-03-04', toDay: '2026-03-05', stratum: 'R', specs });
  };
  const filled = await runFor(closeA - 1500);
  assert.equal(filled.matches, 1);
  // One decision every 5 s from the listing up to (not at) A's close, none after (B trades on for a week).
  assert.equal(filled.decisions, (closeA - listed) / 5000);
  const ep = filled.runs[0].episodes;
  assert.equal(ep.length, 1, 'the resting underdog bid fills on the print before the close');
  assert.deepEqual([ep[0].leg, ep[0].k, ep[0].t, ep[0].px], ['underdog_entry', 0, closeA - 1500, 0.21]);
  const late = await runFor(closeA - 500);
  assert.equal(late.decisions, filled.decisions);
  assert.deepEqual(late.runs[0].episodes, [], 'expired at A\'s close - 1 s: no fill at or after it');
  assert.deepEqual(late.runs[0].pnl, [0]);
});

test('R: a published start on a later market line re-keys the match (start, day, ownership) while it has not begun', async () => {
  // Market A's line has no start, B's has one: the match starts 00:30 UTC on Mar 5, listed 22:00 on Mar 4.
  const start = Date.parse('2026-03-05T00:30:00Z'), listed = start - 150 * MIN;
  const write = (bListedAt: number) => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ttp-'));
    const tk = ['KXATPMATCH-P1-A', 'KXATPMATCH-P1-B'];
    const mk = (i: number, t: number) => ({ t, k: 'market', ticker: tk[i], series: 'KXATPMATCH', kind: 'match', event: 'KXATPMATCH-P1', openTime: listed - 3_600_000, closeTime: start + 7 * 86_400_000, tickSize: 0.01, title: `Will P${i} win?`, ...(i ? { startTime: start } : {}) });
    writeRecordingLines(dir, [
      mk(0, listed), mk(1, bListedAt),
      ...tk.map((ticker, i) => ({ t: bListedAt + 1000, k: 'book', ticker, bids: [{ price: i ? 0.38 : 0.6, size: 50 }], asks: [{ price: i ? 0.4 : 0.62, size: 50 }], ts: bListedAt + 1000 })),
      ...tk.map((ticker, i) => ({ t: start + 2 * 3_600_000, k: 'lifecycle', ticker, event: 'determined', result: i ? 'no' : 'yes', ts: start + 2 * 3_600_000 })),
    ]);
    return dir;
  };
  const admitted: number[] = [];
  for (const bAt of [listed, listed + 30 * MIN]) {
    const dir = write(bAt);
    const r = await runSweep({ dir, fromDay: '2026-03-05', toDay: '2026-03-06', stratum: 'R', specs: [], admit: (m) => { admitted.push(m.start); return true; } });
    assert.equal(r.matches, 1, 'owned by the slice of its published start');
    assert.deepEqual([r.matchList[0].start, r.matchList[0].startPublished, r.matchList[0].day], [start, true, '2026-03-05']);
    assert.ok(admitted.includes(start), 'admit() is asked with the published start');
    const prev = await runSweep({ dir, fromDay: '2026-03-04', toDay: '2026-03-05', stratum: 'R', specs: [] });
    assert.equal(prev.matches, 0, 'and not by the slice of its first line\'s time');
  }
  // A start that arrives only after the match began does not move it: the key is fixed by then.
  const lateDir = write(start + 10 * MIN);
  const r = await runSweep({ dir: lateDir, fromDay: '2026-03-04', toDay: '2026-03-05', stratum: 'R', specs: [] });
  assert.equal(r.matches, 1);
  assert.deepEqual([r.matchList[0].start, r.matchList[0].startPublished], [listed, false]);
});

test('R: grids reach onGrid in day order; one that finishes after its day was released is counted, not delivered', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'tto-'));
  const H = 3_600_000, D = Date.parse('2026-03-04T00:00:00Z');
  const lines: Array<{ t: number; k: string; [key: string]: unknown }> = [];
  const match = (id: string, start: number, settleA: boolean, settleB: boolean, until: number) => {
    const tk = [`KXATPMATCH-${id}-A`, `KXATPMATCH-${id}-B`];
    tk.forEach((ticker, i) => lines.push({ t: start - 2 * H, k: 'market', ticker, series: 'KXATPMATCH', kind: 'match', event: `KXATPMATCH-${id}`, openTime: start - 3 * H, closeTime: start + 7 * 24 * H, tickSize: 0.01, title: `Will ${id}${i} win?`, startTime: start }));
    tk.forEach((ticker, i) => lines.push({ t: start - 2 * H + 1000, k: 'book', ticker, bids: [{ price: i ? 0.29 : 0.69, size: 100 }], asks: [{ price: i ? 0.31 : 0.71, size: 100 }], ts: start - 2 * H + 1000 }));
    for (let t = start - 2 * H + 2000; t < until; t += 2000) tk.forEach((ticker, i) => lines.push({ t, k: 'delta', ticker, side: 'bid', price: i ? 0.2 : 0.6, delta: (t / 2000) % 2 ? 1 : -1, ts: t }));
    if (settleA) lines.push({ t: start + 3 * H, k: 'lifecycle', ticker: tk[0], event: 'determined', result: 'yes', ts: start + 3 * H });
    if (settleB) lines.push({ t: start + 3 * H, k: 'lifecycle', ticker: tk[1], event: 'determined', result: 'no', ts: start + 3 * H });
  };
  match('X', D + 10 * H, true, false, D + 14 * H); // B's settlement never recorded: live until the end of the read
  match('Y', D + 34 * H, true, true, D + 38 * H);
  match('Z', D + 106 * H, false, false, D + 116 * H); // traffic only, so the release runs
  writeRecordingLines(dir, lines);
  const seen: string[] = [];
  const r = await runSweep({ dir, fromDay: '2026-03-04', toDay: '2026-03-09', stratum: 'R', specs: [], onGrid: (g) => seen.push(`${g.day} ${g.event}`) });
  assert.equal(r.matches, 3);
  assert.deepEqual(seen, ['2026-03-05 KXATPMATCH-Y']);
  assert.equal(r.lateGrids, 1, 'X finished after its day was released');
  // Without the stuck match, a day is released as soon as it is over and nothing of it is live.
  const dir2 = fs.mkdtempSync(path.join(os.tmpdir(), 'tto-'));
  lines.length = 0;
  match('X', D + 10 * H, true, true, D + 14 * H);
  match('Y', D + 34 * H, true, true, D + 38 * H);
  match('Z', D + 106 * H, false, false, D + 116 * H);
  writeRecordingLines(dir2, lines);
  // The listings (admit) and the deliveries in stream order: X's day is released while Y plays, not 36 h after it.
  const seen2: string[] = [];
  const r2 = await runSweep({ dir: dir2, fromDay: '2026-03-04', toDay: '2026-03-09', stratum: 'R', specs: [],
    admit: (m) => { seen2.push(`listed ${m.event}`); return true; }, onGrid: (g) => seen2.push(`grid ${g.day} ${g.event}`) });
  assert.deepEqual(seen2, ['listed KXATPMATCH-X', 'listed KXATPMATCH-Y', 'grid 2026-03-04 KXATPMATCH-X', 'listed KXATPMATCH-Z', 'grid 2026-03-05 KXATPMATCH-Y']);
  assert.equal(r2.lateGrids, 0);
});
