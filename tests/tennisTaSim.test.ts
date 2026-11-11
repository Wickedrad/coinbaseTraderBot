import assert from 'node:assert/strict';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { test } from 'node:test';
import { loadConfig, paperEnv } from '../bot/config';
import { orderFee, takerFee, type FeeSchedule } from '../bot/fees';
import { OrderBook } from '../bot/marketdata/orderBook';
import { openEntryFee, openSidePrice, PositionBook } from '../bot/oms/positions';
import { HourlyQuotaPacer, QuotaFloors } from '../bot/risk/quotaPacer';
import { breakEvenExit, positionNetAtBid } from '../bot/strategy/fairValueStrategy';
import { MatchTracker, PROGRESS_LATCH_MS, type MatchMarket, type TennisPlan } from '../bot/tennis/tennisStrategy';
import { buildHistoryReplay } from '../research/history/historyReplay';
import type { KalshiCandle } from '../research/history/kalshiHistory';
import { ConfigSim, FEES, feedTimeline, hash32, PLACEBO_RESERVOIR, PLACEBO_SEED, PlaceboReservoir, phaseLabel, RESYNC_WINDOW_MS, rng, runSweep, sigBits, SOCKET_BEAT_KIND, type GridWithHigh, type SimSpec } from '../research/tennisTaSim';
import type { MatchGrid } from '../research/tennisTaTypes';
import { contractsFor, drawTwins, levelFor, minuteCandles, SETTLE_FRAC, WINDOW_FEES, windowOutcome, type MinuteCandles } from '../research/tennisTaWindow';
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

test('held markets as bot/engine.ts fills them: PositionBook, the open contracts\' cost (openSidePrice + openEntryFee), the engine\'s formulas; the pacer fed the same', () => {
  const pacerCfg = loadConfig(paperEnv({})).strategy.pacer;
  for (const mult of [1, 1.25]) {
    const s = simOf('F1', mult === 1 ? { HARNESS_LOSER_STOP: 0.3 } : { HARNESS_LOSER_STOP: 0.3, HARNESS_FEE_MULT: mult });
    const fees: FeeSchedule = { ...FEES, takerMultiplier: FEES.takerMultiplier * mult, makerMultiplier: FEES.makerMultiplier * mult };
    s.rulesAt(T0); // the pacer starts with the first decision
    const book = new PositionBook();
    const pacer = new HourlyQuotaPacer(pacerCfg, T0);
    // A profitable partial exit, an add to what is left, flat, a re-entry and its own partial exit.
    const fills: Array<[side: 'bid' | 'ask', n: number, px: number, taker: boolean]> = [['bid', 7, 0.33, false], ['bid', 3.5, 0.35, true], ['ask', 4, 0.41, true], ['bid', 2, 0.38, false],
      ['ask', 8.5, 0.47, true], ['bid', 6, 0.45, false], ['ask', 2.5, 0.52, true], ['bid', 2.25, 0.46, true]];
    const quotes: Array<[number, number]> = [[0.3, 0.32], [0.36, 0.38], [0.5, 0.52], [0.12, 0.14]];
    const roundTripOff: number[] = [];
    for (const [i, [side, n, px, taker]] of fills.entries()) {
      const ts = T0 + 1000 * (i + 1);
      s.fill(order(side, n, px), n, px, taker, 'E', ts);
      // bot/oms/oms.ts onFill: the fee on the side price paid, into the book; then bot/engine.ts's pacer hook on the book after it.
      const fee = orderFee(n, side === 'bid' ? px : 1 - px, taker, fees);
      const pos = book.applyFill({ ticker: TK, side, count: n, price: px, fee });
      pacer.onFill({ ticker: TK, side, count: n, price: px }, fee, pos, ts);
      assert.deepEqual(s.pos.get(TK), pos, `fill ${i}: the position book x${mult}`);
      assert.equal(s.pacer!.status(ts).realized24hUsd, pacer.status(ts).realized24hUsd, `fill ${i}: the pacer's credit x${mult}`);
      for (const [b, a] of quotes) {
        const sim = s.held(TK, { price: b }, { price: a });
        if (!(pos.yes > 0)) { assert.equal(sim, undefined); continue; }
        // bot/engine.ts tennisTick, verbatim (costPer: the research loser stop's cost, the same open contracts' cost).
        const engine = {
          position: pos.yes, avgEntry: openSidePrice(pos),
          netAtBid: positionNetAtBid(pos.yes, openSidePrice(pos)! + openEntryFee(pos)!, { price: b }, { price: a }, fees),
          breakEven: breakEvenExit(pos.yes, openSidePrice(pos)! + openEntryFee(pos)!, fees),
          costPer: openSidePrice(pos)! + openEntryFee(pos)!,
        };
        assert.deepEqual(sim, engine, `fill ${i} quote ${b}/${a} x${mult}`);
        // What the old round-trip basis ((fees - netCash) / yes, every earlier exit's profit in) would have said.
        roundTripOff[i] = Math.max(roundTripOff[i] ?? 0, Math.abs(positionNetAtBid(pos.yes, (pos.fees - pos.netCash) / pos.yes, { price: b }, { price: a }, fees)! - sim!.netAtBid!));
      }
    }
    assert.ok((roundTripOff[0] ?? 0) < 1e-9, 'one entry: both bases agree');
    for (const i of [2, 3, 5, 6, 7]) assert.ok(roundTripOff[i] > 0.1, `fill ${i}: after a profitable exit the round-trip basis is off by ${roundTripOff[i]} x${mult}`);
    // Settlement through the book: realized into the match and the pacer exactly as the engine's settled hook does.
    s.settle(TK, 'yes', 'E', T0 + 20_000);
    const m = book.settle(TK, 'yes', T0 + 20_000)!;
    pacer.onSettled(TK, m.realized!, T0 + 20_000);
    assert.equal(s.pacer!.status(T0 + 20_000).realized24hUsd, pacer.status(T0 + 20_000).realized24hUsd);
    s.finish('E', [TK], '2026-03-02', false, T0 + 30_000);
    assert.ok(Math.abs(s.run('H').pnl[0] - m.realized!) < 1e-4, `realized ${s.run('H').pnl[0]} vs the book's ${m.realized}`);
    assert.equal(s.pos.get(TK), undefined, 'a settled market leaves the book');
  }
  // costPer only for the research loser stop; it stays the open contracts' cost after a profitable partial exit.
  const s = simOf('F1', { HARNESS_LOSER_STOP: 0.3 });
  s.fill(order('bid', 10, 0.2), 10, 0.2, false, 'E', 1000);
  s.fill(order('ask', 5, 0.9), 5, 0.9, true, 'E', 2000);
  assert.ok(Math.abs(s.held(TK, { price: 0.5 }, { price: 0.52 })!.costPer! - (0.2 + orderFee(10, 0.2, false, FEES) / 10)) < 1e-9);
  assert.equal(simOf('F1').held(TK, undefined, undefined), undefined);
  const off = simOf('F1');
  off.fill(order('bid', 10, 0.2), 10, 0.2, false, 'E', 1000);
  assert.equal(off.held(TK, { price: 0.5 }, { price: 0.52 })!.costPer, undefined, 'costPer only for the research loser stop');
  // A sale's fee is booked on the side price paid (bot/oms/oms.ts), not the YES price: they differ on fractional counts.
  const fs1 = simOf('F1');
  fs1.fill(order('bid', 1.55, 0.333), 1.55, 0.333, true, 'E', 1000);
  fs1.fill(order('ask', 1.55, 0.333), 1.55, 0.333, true, 'E', 2000);
  const sideFee = orderFee(1.55, 0.333, true, FEES) + orderFee(1.55, 0.667, true, FEES);
  assert.notEqual(orderFee(1.55, 0.333, true, FEES), orderFee(1.55, 0.667, true, FEES));
  assert.ok(Math.abs(fs1.pos.get(TK)!.fees - sideFee) < 1e-12);
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

test('the quota floor outlives a flat fill as in production (no fill touches QuotaFloors); settlement forgets it', () => {
  // Production (bot/engine.ts): floor() at each decision, forget() on the settled event; a fill never touches the floors.
  const prod = new QuotaFloors();
  prod.floor(TK, 10); prod.arm(TK, 10, 1.5);
  const s = simOf('F1');
  s.fill(order('bid', 10, 0.4), 10, 0.4, false, 'E', 0);
  s.floors.floor(TK, 10); s.floors.arm(TK, 10, 1.5);
  // Flat at 1 s, a re-entry of 8 filled at 3 s, then the next decision reads the floor.
  s.fill(order('ask', 10, 0.6, 'quota_snipe'), 10, 0.6, true, 'E', 1000);
  s.fill(order('bid', 8, 0.55), 8, 0.55, false, 'E', 3000);
  const got = s.floors.floor(TK, yes(s));
  assert.ok(got !== undefined && Math.abs(got - 1.2) < 1e-9, `floor ${got}`);
  assert.equal(got, prod.floor(TK, 8));
  s.settle(TK, 'yes', 'E', 4000);
  assert.equal(s.floors.floor(TK, 8), undefined, 'settled: forgotten (bot/engine.ts on settled)');
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
  assert.equal(late.progressHigh, 0, 'the latch has not reached the last share (no 2 min of readings there): the ride goes by the reading');
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
  // A coin config's reservoir draws from PLACEBO_SEED (the registry rows' seed) combined with its spec id.
  const id = 'A|s1|m0.01|f0.2|o0.01|w60|coin';
  const sim = new ConfigSim({ id, overrides: {}, fill: 'F1', placebo: 'coin' });
  const ref = new PlaceboReservoir(rng((PLACEBO_SEED ^ hash32(id)) >>> 0));
  assert.equal(PLACEBO_SEED, 20261105);
  const seq = (r: PlaceboReservoir) => { const out: number[] = []; for (let t = 0; t < 3000; t++) out.push(r.draw(t % 3 ? 'E1' : 'E2', t, t % 16)); return out; };
  const got = seq(sim.placebo!);
  assert.deepEqual(got, seq(ref));
  assert.notDeepEqual(got, seq(new PlaceboReservoir(rng(hash32(id)))), 'not the spec id alone');
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
  assert.equal(fav('stop').x, 'loser_stop', 'the research loser stop fires on the open contracts\' own cost');
  assert.equal(breaches('stop'), 0);
  // The grids carry production's two progress reads for family B: `progress` the reading of the tick (the ride rule, the
  // phase contexts) and `progressHigh` the latched progress (MatchTracker.latchProgress over the 5 s decisions of a
  // production-default tracker: what the end cut and the entry block read), which follows the reading by PROGRESS_LATCH_MS.
  const tennis = loadConfig(paperEnv({})).tennis;
  const share = 1 - tennis.settleFrac;
  let lagged = 0;
  for (const g of grids as GridWithHigh[]) {
    assert.equal(g.progressHigh.length, g.n);
    const ref = new MatchTracker('ref', tennis);
    const closeT = g.t0 + g.closeIdx * 1000;
    let checked = 0;
    for (let i = 0; i < g.n; i++) {
      // The sample 1 s after a decision holds that decision's readings (a sample at a decision's instant comes before it).
      const d = g.t0 + i * 1000 - 1000;
      if (d % 5000 !== 0 || d >= closeT) continue;
      assert.equal(g.progressHigh[i], ref.latchProgress(d, g.progress[i]), `${g.event}: the latch at sample ${i}`);
      checked++;
    }
    assert.ok(checked > 1000, `${g.event}: ${checked} decisions`);
    const iRead = g.progress.findIndex((p) => p >= share - 1e-9), iHigh = g.progressHigh.findIndex((p) => p >= share - 1e-9);
    if (iRead < 0) continue;
    assert.ok(iHigh >= 0 && iHigh - iRead >= PROGRESS_LATCH_MS / 1000, `${g.event}: the last share by the reading at ${iRead}, by the latch at ${iHigh}`);
    // Not the running maximum of the reading (one tick's high reading never sets it).
    let runMax = 0, above = 0;
    for (let i = 0; i < g.n; i++) { runMax = Math.max(runMax, g.progress[i]); assert.ok(g.progressHigh[i] <= runMax + 1e-12); if (runMax > g.progressHigh[i] + 0.01) above++; }
    assert.ok(above > 0, `${g.event}: the latch lags the running maximum`);
    lagged++;
  }
  assert.ok(lagged > 0, 'a match reached its last share');
});

type RecordedCase = { feed: RecordedFeed; resync: boolean; quiet?: boolean; gaps: number; blind: number; liveDays: number; blindDays: number };
const R_SPECS: SimSpec[] = [{ id: 'prod', overrides: {}, fill: 'F1' }, { id: 'loose', overrides: { ...LOOSE }, fill: 'F1' }];

/** One recording of writeTaRecording through the sweep: the match, its settlement, the feed's outages and the grid's quotes
 *  around the 10-minute tennis silence. Returns the configs' per-match P&L. */
async function recordedCase(c: RecordedCase): Promise<string> {
  const name = `${c.feed}${c.quiet ? '+quiet' : ''}${c.resync ? '+resync' : ''}`;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ttr-'));
  const plan = writeTaRecording(dir, '2026-03-04', { feed: c.feed, resync: c.resync, quiet: c.quiet });
  const grids: MatchGrid[] = [];
  const r = await runSweep({ dir, fromDay: '2026-03-04', toDay: '2026-03-05', stratum: 'R', specs: R_SPECS, onGrid: (g) => grids.push(g) });
  assert.equal(r.matches, 1, `${name}: the market line written two days before the start is read`);
  const m = r.matchList[0];
  assert.equal(m.event, plan.event);
  assert.equal(m.unresolved, false, `${name}: settled from the lifecycle lines alone`);
  assert.equal(m.resultA, 1);
  assert.equal(m.startPublished, true);
  assert.equal(r.unresolved, 0);
  assert.deepEqual([r.gaps, r.blindGaps, r.liveDays, r.blindDays], [c.gaps, c.blind, c.liveDays, c.blindDays], name);
  if (c.gaps) assert.ok(r.gapMs >= 10 * MIN && r.gapMs < 11 * MIN, `${name}: ${r.gapMs}`);
  else assert.equal(r.gapMs, 0, name);
  assert.equal(r.lost, 0);
  for (const run of r.runs) {
    assert.equal(run.days[0].unresolved, 0);
    assert.ok(run.episodes.every((e) => e.x !== 'drop'), `${name} ${run.id}: nothing dropped`);
    assert.equal(run.days[0].breaches, 0);
  }
  assert.ok(r.runs.some((x) => x.episodes.some((e) => e.x === 'settle')), `${name}: a held favorite settles on the lifecycle line`);
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
    // A silence that is no outage (a quiet market on a blind day, or a quiet tennis stretch inside a live feed): the books
    // stay usable through it.
    for (const t of [plan.gapFrom + 30_000, plan.gapFrom + 5 * MIN, plan.gapTo + 5000, plan.snapAgain - 1000]) ok(t, 'no outage');
    assert.equal(g.n, [...g.bidA].filter(Number.isFinite).length, `${name}: every second quoted`);
  } else {
    for (const t of [plan.gapFrom + 30_000, plan.gapFrom + 5 * MIN, plan.gapTo - 1000]) dead(t, 'in the outage');
    if (c.resync) for (const t of [plan.gapTo + 1000, plan.snapAgain - 1000]) ok(t, 'the resubscribe snapshots');
    else for (const t of [plan.gapTo + 5000, plan.snapAgain - 1000]) dead(t, 'deltas without a snapshot');
    ok(plan.snapAgain + 1000, 'usable again after the next snapshot');
  }
  return JSON.stringify(r.runs.map((x) => x.pnl));
}

test('R: early-listed matches (lookback), lifecycle-only settlement; feed outages blank every book until its next snapshot', async () => {
  // Which silences are outages: on a day that shows the feed's liveness (beat lines, or a raw file's other markets) every
  // silence over 12 s; on a blind day (tennis lines only) only one that a resubscribe ends.
  const cases: RecordedCase[] = [
    { feed: 'beat', resync: false, gaps: 1, blind: 0, liveDays: 3, blindDays: 0 },
    { feed: 'raw', resync: false, gaps: 1, blind: 0, liveDays: 3, blindDays: 0 },
    { feed: 'beat', resync: true, gaps: 1, blind: 0, liveDays: 3, blindDays: 0 },
    { feed: 'none', resync: false, gaps: 0, blind: 0, liveDays: 0, blindDays: 2 },
    { feed: 'none', resync: true, gaps: 1, blind: 1, liveDays: 0, blindDays: 2 },
  ];
  const pnls: string[] = [];
  for (const c of cases) pnls.push(await recordedCase(c));
  // The beats and the raw file's other markets read the same feed; the strategy never sees them.
  assert.equal(pnls[0], pnls[1]);
  // Only a day before fromDay: the match's market line is lost, and the loss is counted.
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ttr-'));
  writeTaRecording(dir);
  const short = await runSweep({ dir, fromDay: '2026-03-04', toDay: '2026-03-05', stratum: 'R', specs: R_SPECS, lookbackDays: 1 });
  assert.equal(short.matches, 0);
  assert.equal(short.lost, 2);
  // A match that began before fromDay is no loss, though the read meets its lines without their market line.
  const after = await runSweep({ dir, fromDay: '2026-03-05', toDay: '2026-03-06', stratum: 'R', specs: R_SPECS, lookbackDays: 1 });
  assert.equal(after.matches, 0);
  assert.equal(after.lost, 0);
});

test('R: beat and alive lines keep a live feed\'s books usable through a quiet tennis stretch; a reconnect they mask is still an outage', async () => {
  // The tennis lines stop for 10 minutes while the beats (or alive lines, or a raw file's crypto deltas) go on: no outage.
  const quiet: RecordedCase[] = (['beat', 'alive', 'raw'] as const).map((feed) => ({ feed, resync: false, quiet: true, gaps: 0, blind: 0, liveDays: 3, blindDays: 0 }));
  const pnls: string[] = [];
  for (const c of quiet) pnls.push(await recordedCase(c));
  // Feed activity only: the configs trade exactly as on the blind day's quiet market (no outage there either), an alive
  // line's tickers never touch a recorded book.
  const blind = await recordedCase({ feed: 'none', resync: false, gaps: 0, blind: 0, liveDays: 0, blindDays: 2 });
  assert.deepEqual(pnls, [blind, blind, blind]);
  // The same quiet stretch ended by a resubscribe (fresh snapshots of both books): a reconnect the beats hid (they come from
  // any source line), an outage from the last tennis line to the snapshots, even with alive lines naming the books in it.
  for (const feed of ['beat', 'alive'] as const) await recordedCase({ feed, resync: true, quiet: true, gaps: 1, blind: 1, liveDays: 3, blindDays: 0 });
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

test('feedTimeline: ws_beat lines date a reconnect from the socket\'s last line after a quiet tennis hour; without them the beats mask it (conservative), a restart is dated from the silence', async () => {
  const T = Date.parse('2026-03-04T10:00:00Z');
  const tk = ['KXATPMATCH-W1-A', 'KXATPMATCH-W1-B'];
  const S = 1000;
  const book = (t: number, ticker: string) => ({ t, k: 'book', ticker, bids: [{ price: 0.4, size: 10 }], asks: [{ price: 0.42, size: 10 }], ts: t });
  const delta = (t: number) => ({ t, k: 'delta', ticker: tk[0], side: 'bid', price: 0.4, delta: 1, ts: t });
  // O: a 20 s Kalshi outage after an hour without a tennis line (the Coinbase feed goes on, so the any-source beats do),
  // ended by a resubscribe; W: a 30 s stall of the socket that no resubscribe ends; R: the whole recorder silent 30 s.
  const O = T + 3600 * S, W = T + 5400 * S, R = T + 1800 * S;
  const lines = (o: { ws: boolean; restart?: boolean }) => {
    const out: Array<{ t: number; k: string; [key: string]: unknown }> = [book(T, tk[0]), book(T, tk[1])];
    const kalshiDown = (t: number) => (!o.restart && ((t >= O && t < O + 20 * S) || (t >= W && t < W + 30 * S)));
    const allDown = (t: number) => !!o.restart && t >= R && t < R + 30 * S;
    for (let t = T; t <= T + 7200 * S; t += 5 * S) {
      if (allDown(t)) continue;
      out.push({ t, k: 'beat' });
      if (o.ws && !kalshiDown(t)) out.push({ t, k: SOCKET_BEAT_KIND });
    }
    for (let t = T + 10 * S; t <= T + 60 * S; t += 10 * S) out.push(delta(t));
    if (o.restart) out.push(book(R + 32 * S, tk[0]), book(R + 32 * S, tk[1]));
    else { out.push(book(O + 20 * S, tk[0]), book(O + 20 * S, tk[1])); for (let t = O + 30 * S; t <= O + 80 * S; t += 10 * S) out.push(delta(t)); }
    out.push(delta(T + 7200 * S + 1));
    return out;
  };
  const gapsOf = async (ls: ReturnType<typeof lines>) => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ttw-'));
    writeRecordingLines(dir, ls);
    const f = await feedTimeline(dir, '2026-03-04', '2026-03-04');
    assert.deepEqual([f.liveDays, f.blindDays], [['2026-03-04'], []]);
    return f.gaps.map((g) => [(g.from - T) / S, (g.to - T) / S, g.blind]);
  };
  // The socket's own liveness: the reconnect from the last ws_beat (as the raw file's crypto lines would date it), the
  // stall too (no resubscribe needed), and no outage in the quiet tennis hour.
  assert.deepEqual(await gapsOf(lines({ ws: true })), [[3595, 3620, false], [5395, 5430, false]]);
  // Beats from any source only: the reconnect is found by its resubscribe and dated from the last TENNIS socket line (the
  // cut shows nothing later of the socket), the stall is not seen.
  assert.deepEqual(await gapsOf(lines({ ws: false })), [[60, 3620, true]]);
  // A restart (every line silent, then the resubscribe): dated from the silence, not from the last tennis line.
  assert.deepEqual(await gapsOf(lines({ ws: false, restart: true })), [[1795, 1832, false]]);
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

// ---- Window mode (Amendment 4): signal instances, virtual positions, the one test's inputs ----------------------------

/** The window rule's candles of every market of a fixture history day file (research/tennisTaWindow.ts minuteCandles on the
 *  stored candles: the fixtures store closes only, so bidL is the close). */
function candlesOfHistory(hist: string, day: string): (ticker: string) => MinuteCandles | undefined {
  const by = new Map<string, MinuteCandles>();
  for (const l of fs.readFileSync(path.join(hist, 'kalshi', 'KXATPMATCH', `${day}.jsonl`), 'utf8').split('\n')) {
    if (!l) continue;
    const m = JSON.parse(l) as { ticker: string; closeTime: number; candles: Array<{ ts: number; bidC: number; askC: number; last: number; volume: number }> };
    const kc: KalshiCandle[] = m.candles.map((c) => ({ ts: c.ts, bidO: null, bidH: null, bidL: null, bidC: c.bidC, askO: null, askH: null, askL: null, askC: c.askC, last: c.last, volume: c.volume, oi: null }));
    by.set(m.ticker, minuteCandles(kc, m.closeTime));
  }
  return (t) => by.get(t);
}

/** The entry minute's end as the sim seeds the twins with it. */
const minuteKey = (t: number) => new Date(Math.ceil(t / MIN) * MIN).toISOString().slice(0, 16);

test('window mode: an entry plan is an instance at the decision\'s ask, held virtually as production holds a fill; released at its window minute or by the end rule; exits are ignored', () => {
  const EV = 'KXATPMATCH-W0', A = `${EV}-A`, B = `${EV}-B`;
  const close = T0 + 150 * MIN;
  // B's minutes: bid 0.19 / ask 0.21, its bid at 0.27 from the minute ending T0 + 12 min for eight minutes; A mirrors it.
  const mcB: MinuteCandles = [];
  for (let i = 1; i <= 150; i++) { const up = i >= 12 && i < 20; mcB.push({ ts: T0 + i * MIN, bidL: up ? 0.27 : 0.19, bidC: up ? 0.27 : 0.19, askC: up ? 0.29 : 0.21, twoSided: true }); }
  const mcA: MinuteCandles = mcB.map((c) => ({ ts: c.ts, bidL: +(1 - c.askC).toFixed(2), bidC: +(1 - c.askC).toFixed(2), askC: +(1 - c.bidC).toFixed(2), twoSided: true }));
  const s = new ConfigSim({ id: 'w', overrides: {}, fill: 'F1', window: true });
  assert.equal(s.window, true);
  s.candlesOf = (t) => (t === A ? mcA : t === B ? mcB : undefined);
  const tr = s.tracker(EV);
  const mk = (ticker: string, bid: number, ask: number): MatchMarket => ({ ticker, position: 0, quote: { bid, ask } });
  const markets = [mk(A, 0.79, 0.81), mk(B, 0.19, 0.21)];
  const t1 = T0 + 5 * MIN + 5000;
  const entry = plan({ ticker: B, price: 0.19, count: 40 });
  const exit = plan({ ticker: A, side: 'ask', price: 0.79, count: 10, postOnly: false, reduceOnly: true, timeInForce: 'immediate_or_cancel', leg: 'end_cut' });
  s.windowDecision(EV, [A, B], close, [entry, exit], markets, tr, t1);
  // The instance is a taker buy at the ask the decision saw (0.21), not at the plan's maker bid; held as production's fields
  // would carry such a fill (position C, avgEntry the ask, netAtBid and breakEven on ask + the taker fee a contract).
  const C = contractsFor(0.21), level = levelFor(0.21, C, FEES), cost = 0.21 + takerFee(C, 0.21, FEES) / C;
  const h = s.held(B, { price: 0.19 }, { price: 0.21 })!;
  assert.equal(h.position, C);
  assert.equal(h.avgEntry, 0.21);
  assert.equal(h.breakEven, breakEvenExit(C, cost, FEES));
  assert.equal(h.netAtBid, positionNetAtBid(C, cost, { price: 0.19 }, { price: 0.21 }, FEES));
  assert.equal(h.costPer, undefined);
  assert.equal(s.held(A, { price: 0.79 }, { price: 0.81 }), undefined, 'the exit plan placed nothing');
  assert.equal(s.busy(B), false, 'no order, no position in the book');
  assert.equal(s.pos.get(B), undefined);
  // Another entry plan while held is no instance; the release waits for the window minute (candles read up to now only).
  s.windowRelease(EV, t1 + 5000);
  s.windowDecision(EV, [A, B], close, [entry], markets, tr, t1 + 5000);
  s.windowRelease(EV, T0 + 12 * MIN - 5000);
  assert.ok(s.held(B, { price: 0.19 }, { price: 0.21 }), 'held until the window minute ends');
  s.windowRelease(EV, T0 + 12 * MIN);
  assert.equal(s.held(B, { price: 0.19 }, { price: 0.21 }), undefined, 'released at the first decision at or after the window minute\'s end');
  // The favourite leg after the release, on A, the match still short of the end rule: held (A's bid never reaches its level).
  const t2 = T0 + 12 * MIN;
  const favPlan = plan({ ticker: A, price: 0.79, count: 10, leg: 'fav_entry' });
  s.windowDecision(EV, [A, B], close, [favPlan], markets, tr, t2);
  assert.equal(s.held(A, { price: 0.79 }, { price: 0.81 })!.position, contractsFor(0.81));
  s.windowRelease(EV, t2 + 5000);
  assert.ok(s.held(A, { price: 0.79 }, { price: 0.81 }), 'held: no window, no end rule yet');
  // The end-rule decision: the tracker's latched progress (production's latch, updated inside decideMatch) reached
  // 1 - SETTLE_FRAC at t3. An entry plan for the flat market B at this decision is no instance (its window would have to end
  // after the entry and at or before the end rule), nor is any later one (the settle-hold stick emits them: its cut is off,
  // and the released market is flat again at every later decision); the next decision releases A by the end rule.
  tr.progressHigh = 1 - SETTLE_FRAC;
  const t3 = T0 + 13 * MIN;
  s.windowDecision(EV, [A, B], close, [entry], markets, tr, t3);
  assert.equal(s.held(B, { price: 0.19 }, { price: 0.21 }), undefined, 'an entry plan at the end-rule decision is no instance');
  assert.ok(s.held(A, { price: 0.79 }, { price: 0.81 }), 'A is held through the end-rule decision');
  s.windowRelease(EV, t3 + 5000);
  assert.equal(s.held(A, { price: 0.79 }, { price: 0.81 }), undefined, 'released by the end rule');
  for (const t of [t3 + 5000, t3 + 10_000, close - 5000]) {
    s.windowDecision(EV, [A, B], close, [entry, favPlan], markets, tr, t);
    assert.equal(s.held(A, { price: 0.79 }, { price: 0.81 }), undefined, `no entry plan after the end rule is an instance (${(t - t3) / 1000} s after)`);
    assert.equal(s.held(B, { price: 0.19 }, { price: 0.21 }), undefined);
  }
  s.finish(EV, [A, B], '2026-03-02', false, close + 1000);
  const run = s.run('H');
  assert.equal(run.window, true);
  assert.deepEqual(run.pnl, [0]);
  assert.equal(run.episodes.length, 0);
  assert.equal(run.days[0].entries, 0);
  assert.deepEqual(run.days[0].legs, {});
  assert.equal(run.instances!.length, 2);
  const [u, f] = run.instances!;
  assert.deepEqual({ ...u, outcome: undefined, twins: undefined }, { event: EV, side: 'b', leg: 'underdog', t: t1, ask: 0.21, C, level, phase: 'pre', sig: 0, outcome: undefined, twins: undefined });
  assert.deepEqual(u.outcome, windowOutcome(mcB, t1, 0.21, level, t3));
  assert.equal(u.outcome.resolvedBy, 'window');
  assert.equal(u.outcome.resolvedAt, T0 + 12 * MIN);
  // The horizon runs to the end-rule minute (ts == endRuleTs counts): minutes 12 and 13 at the level, so the run and the
  // minutes held are 2.
  assert.equal(u.outcome.lenWin, 2);
  assert.equal(u.outcome.held, 2);
  assert.equal(u.twins.length, 3);
  assert.deepEqual(u.twins, drawTwins(mcA, mcB, t1, t3, `${EV}|w|underdog|${minuteKey(t1)}`, 3, 10, u.side));
  assert.equal(minuteKey(t1), '2026-03-02T16:06');
  assert.deepEqual({ ...f, outcome: undefined, twins: undefined }, { event: EV, side: 'a', leg: 'fav', t: t2, ask: 0.81, C: contractsFor(0.81), level: levelFor(0.81, contractsFor(0.81), FEES), phase: 'pre', sig: 0, outcome: undefined, twins: undefined });
  // A's bid in minute 13 (the one horizon minute, 0.71) is under the level: resolved by the end rule, the dip 10c, held 0.
  assert.deepEqual(f.outcome, windowOutcome(mcA, t2, 0.81, f.level, t3));
  assert.equal(f.outcome.resolvedBy, 'end');
  assert.equal(f.outcome.resolvedAt, t3);
  assert.equal(f.outcome.held, 0);
  assert.ok(Math.abs(f.outcome.dip - (0.71 - 0.81)) < 1e-9);
  assert.deepEqual(f.twins, drawTwins(mcA, mcB, t2, t3, `${EV}|w|fav|${minuteKey(t2)}`, 3, 10, f.side));
  // Without candles: the instance resolves 'none' and has no twin; only the end rule or the close releases it.
  const s2 = new ConfigSim({ id: 'w2', overrides: {}, fill: 'F1', window: true });
  const tr2 = s2.tracker(EV);
  s2.windowDecision(EV, [A, B], close, [entry], markets, tr2, t1);
  s2.windowRelease(EV, close);
  assert.ok(s2.held(B, { price: 0.19 }, { price: 0.21 }), 'no candle releases it');
  s2.finish(EV, [A, B], '2026-03-02', false, close + 1000);
  const i2 = s2.run('H').instances![0];
  assert.equal(i2.outcome.resolvedBy, 'none');
  assert.deepEqual(i2.twins, []);
  // A match not owned leaves nothing behind.
  const s3 = new ConfigSim({ id: 'w3', overrides: {}, fill: 'F1', window: true });
  s3.windowDecision(EV, [A, B], close, [entry], markets, s3.tracker(EV), t1);
  s3.finish(EV, [A, B], '2026-03-02', false, close + 1000, false);
  assert.equal(s3.run('H').instances!.length, 0);
  assert.equal(s3.held(B, { price: 0.19 }, { price: 0.21 }), undefined);
  // The level is the amendment's (item 3: WINDOW_FEES, the tennis taker multiplier 1, the schedule the twins are judged on),
  // whatever the market's dated schedule (feeFor, the sweep's --fees lookup) says; the held view, production's fee view,
  // does carry that schedule.
  const dear: FeeSchedule = { takerMultiplier: 2, makerMultiplier: 2 };
  assert.notEqual(levelFor(0.21, C, dear), levelFor(0.21, C), 'the dated schedule would set another level');
  const s4 = new ConfigSim({ id: 'w4', overrides: {}, fill: 'F1', window: true });
  s4.feeFor = () => dear;
  s4.candlesOf = s.candlesOf;
  s4.windowDecision(EV, [A, B], close, [entry], markets, s4.tracker(EV), t1);
  const h4 = s4.held(B, { price: 0.19 }, { price: 0.21 })!;
  const cost4 = 0.21 + takerFee(C, 0.21, dear) / C;
  assert.equal(h4.breakEven, breakEvenExit(C, cost4, dear));
  assert.equal(h4.netAtBid, positionNetAtBid(C, cost4, { price: 0.19 }, { price: 0.21 }, dear));
  s4.finish(EV, [A, B], '2026-03-02', false, close + 1000);
  const i4 = s4.run('H').instances![0];
  assert.equal(i4.level, levelFor(0.21, C));
  assert.equal(i4.level, levelFor(0.21, C, WINDOW_FEES));
  assert.deepEqual(i4.outcome, windowOutcome(mcB, t1, 0.21, i4.level, close));
  assert.equal(i4.twins.length, 3);
  for (const x of i4.twins) assert.equal(x.level, levelFor(x.ask, x.C), 'the twins on the same schedule');
  for (const x of i4.twins) if (x.side === 'b' && x.ask === 0.21) assert.equal(x.level, i4.level, 'a twin at the instance\'s ask shares its level');
  // A match whose first entry plan comes once the latch stands leaves no instance at all.
  const s5 = new ConfigSim({ id: 'w5', overrides: {}, fill: 'F1', window: true });
  s5.candlesOf = s.candlesOf;
  const tr5 = s5.tracker(EV);
  tr5.progressHigh = 1 - SETTLE_FRAC;
  s5.windowDecision(EV, [A, B], close, [entry], markets, tr5, t1);
  assert.equal(s5.held(B, { price: 0.19 }, { price: 0.21 }), undefined);
  s5.windowDecision(EV, [A, B], close, [entry, favPlan], markets, tr5, t1 + 5000);
  s5.finish(EV, [A, B], '2026-03-02', false, close + 1000);
  assert.deepEqual(s5.run('H').instances, []);
});

/** The windowed match: B the underdog at 20c before the start (the underdog entry pre-match), B's bid up to 27c for a quarter
 *  hour from the fifth minute (the underdog's window), then A climbs to 85c and holds it through the middle (the favourite
 *  entry, whose level its bid never reaches), and collapses in the last third (B wins; the end rule by the latched progress). */
const windowed = (min: number): number => (min < 5 ? 0.8 : min < 20 ? 0.72 : min < 50 ? 0.72 + ((min - 20) / 30) * 0.13 : min < 100 ? 0.85 : min < 130 ? 0.85 - ((min - 100) / 30) * 0.83 : 0.02);

test('tennis TA sweep, window arm: one underdog instance at the first entry plan, the favourite after the window, no sells, twins, the end rule from the latched progress; the P&L arms are unchanged', async () => {
  const hist = fs.mkdtempSync(path.join(os.tmpdir(), 'ttw-')), dir = path.join(hist, 'replay');
  const day = '2026-03-06', EV = 'KXATPMATCH-W1', A = `${EV}-A`, B = `${EV}-B`;
  writeScriptedHistory(hist, day, [{ id: 'W1', winA: false, startHour: 10, p: windowed }]);
  await buildHistoryReplay({ historyDir: hist, outDir: dir, assets: [], fromDay: day, toDay: '2026-03-07', tennisSeries: ['KXATPMATCH'], log: () => {} });
  const candlesOf = candlesOfHistory(hist, day);
  const mcA = candlesOf(A)!, mcB = candlesOf(B)!;
  assert.equal(mcA.length, 210, 'the first stored candle dropped');
  const pnl: SimSpec[] = [{ id: 'A|s1|t', overrides: { ...LOOSE }, fill: 'F1' }, { id: 'A|s1|t|f0', overrides: { ...LOOSE }, fill: 'F0' }];
  const win: SimSpec = { id: 'A|s1|t|window', overrides: { ...LOOSE }, fill: 'F1', window: true };
  const coin: SimSpec = { id: 'A|s1|t|coinwindow', overrides: { ...LOOSE }, fill: 'F1', placebo: 'coin', window: true };
  const grids: MatchGrid[] = [];
  const r = await runSweep({ dir, fromDay: day, toDay: '2026-03-07', stratum: 'H', specs: [...pnl, win, coin], candlesOf, onGrid: (g) => grids.push(g) });
  assert.equal(r.matches, 1);
  // The P&L arms are what they are without the window arms (lock-step: shared data, their own state).
  const alone = await runSweep({ dir, fromDay: day, toDay: '2026-03-07', stratum: 'H', specs: pnl });
  assert.deepEqual(r.runs.slice(0, 2), alone.runs);
  assert.ok(alone.runs[1].episodes.length > 0, 'the F0 arm trades the match');
  assert.equal(r.runs[0].instances, undefined);
  assert.equal(r.runs[0].window, undefined);
  // The window arm: no order, no fill, nothing sold; every match 0; its instances instead.
  const w = r.runs[2];
  assert.equal(w.window, true);
  assert.deepEqual(w.pnl, [0]);
  assert.equal(w.episodes.length, 0);
  assert.equal(w.days[0].matches, 1);
  assert.equal(w.days[0].entries, 0);
  assert.deepEqual(w.days[0].legs, {});
  const g = grids[0] as GridWithHigh;
  assert.deepEqual(g.candles, { a: mcA, b: mcB }, 'the grid carries the window rule\'s candles for family B');
  const start = Date.parse(`${day}T10:00:00Z`);
  const closeT = g.t0 + g.closeIdx * 1000;
  // The end rule: the first decision at which the latched progress reached 1 - SETTLE_FRAC (the sample 1 s after a decision
  // holds that decision's readings), before the close here (the collapse).
  const iHigh = Array.from(g.progressHigh).findIndex((p) => p >= 1 - SETTLE_FRAC - 1e-9);
  assert.ok(iHigh > 0, 'the match reached its last share by the latch');
  const endRule = g.t0 + iHigh * 1000 - 1000;
  assert.equal(endRule % 5000, 0);
  assert.ok(endRule > start + 120 * MIN && endRule < closeT, `end rule at ${(endRule - start) / MIN} min`);
  const insts = w.instances!;
  assert.equal(insts.length, 2, 'each leg fires once');
  const [u, f] = insts;
  // The underdog, pre-match: at the first decision with a two-sided book in the 30 minutes before the start (the first
  // decision sees no book yet), at B's ask as the decision saw it (the grid's ask at that second), C and the level by the rule.
  assert.equal(u.event, EV);
  assert.equal(u.leg, 'underdog');
  assert.equal(u.side, 'b');
  assert.equal(u.phase, 'pre');
  assert.equal(u.t, start - 30 * MIN + 5000);
  assert.equal(u.ask, g.askB[(u.t - g.t0) / 1000]);
  assert.equal(u.ask, 0.2);
  assert.equal(u.C, contractsFor(0.2));
  assert.equal(u.level, levelFor(0.2, u.C, FEES));
  assert.ok(u.sig !== undefined && u.sig >= 0 && u.sig < 16, 'the confluence reading of the decision');
  // Its window: B's bid is at 27c from the candle ending 5 minutes into the match; the verdict is windowOutcome's under the end rule.
  assert.deepEqual(u.outcome, windowOutcome(mcB, u.t, u.ask, u.level, endRule));
  assert.equal(u.outcome.resolvedBy, 'window');
  assert.equal(u.outcome.resolvedAt, start + 5 * MIN);
  assert.ok(Math.abs(u.outcome.tWin! - (35 - 5 / 60)) < 1e-9);
  // The favourite, after the underdog's release: once the match is 'late' and A holds 85c, on A at the ask the decision saw;
  // its level is above any bid A shows, so no window: resolved by the end rule, held 0 minutes at the level.
  assert.equal(f.leg, 'fav');
  assert.equal(f.side, 'a');
  assert.ok(f.t > u.outcome.resolvedAt! && f.t > start + 50 * MIN && f.t < start + 100 * MIN, `favourite at ${(f.t - start) / MIN} min`);
  assert.equal(f.t % 5000, 0);
  assert.equal(f.ask, g.askA[(f.t - g.t0) / 1000]);
  assert.equal(f.ask, 0.85);
  assert.equal(f.level, levelFor(0.85, contractsFor(0.85), FEES));
  assert.equal(f.phase, 'p2');
  assert.deepEqual(f.outcome, windowOutcome(mcA, f.t, f.ask, f.level, endRule));
  assert.equal(f.outcome.win, false);
  assert.equal(f.outcome.resolvedBy, 'end');
  assert.equal(f.outcome.resolvedAt, endRule);
  assert.equal(f.outcome.held, 0);
  // Twins: three each, drawn by the rule under the same end rule, seeded by event | config | leg | entry minute.
  for (const x of insts) {
    assert.equal(x.twins.length, 3);
    assert.deepEqual(x.twins, drawTwins(mcA, mcB, x.t, endRule, `${EV}|${win.id}|${x.leg}|${minuteKey(x.t)}`, 3, 10, x.side));
  }
  // The coin placebo window arm: the same instances under the loose config (no signal needed), its own twins' seeds.
  const c = r.runs[3];
  assert.equal(c.placebo, 'coin');
  assert.deepEqual(c.instances!.map((x) => [x.leg, x.t, x.ask, x.outcome]), insts.map((x) => [x.leg, x.t, x.ask, x.outcome]));
  assert.deepEqual(c.instances![0].twins, drawTwins(mcA, mcB, u.t, endRule, `${EV}|${coin.id}|underdog|${minuteKey(u.t)}`, 3, 10, u.side));
  assert.notDeepEqual(c.instances![0].twins, u.twins);
  // Without candles: the underdog instance is the same, resolves 'none' without twins, and is never released by a window, so
  // the favourite leg cannot fire while it is held.
  const none = await runSweep({ dir, fromDay: day, toDay: '2026-03-07', stratum: 'H', specs: [win] });
  const n0 = none.runs[0].instances!;
  assert.equal(n0.length, 1);
  assert.deepEqual([n0[0].leg, n0[0].t, n0[0].ask, n0[0].C, n0[0].level], ['underdog', u.t, u.ask, u.C, u.level]);
  assert.equal(n0[0].outcome.resolvedBy, 'none');
  assert.deepEqual(n0[0].twins, []);
  const nog: MatchGrid[] = [];
  await runSweep({ dir, fromDay: day, toDay: '2026-03-07', stratum: 'H', specs: [], onGrid: (g2) => nog.push(g2) });
  assert.equal(nog[0].candles, undefined, 'no candlesOf: the grid carries no candles');
});

/** The settle-hold stick's match: B the underdog at 22c before the start (its window: B at 30c from the fifth minute), A at
 *  70c through the middle (no favourite: under favMin), then a step to 4c at 100 minutes (B at 96c, over favMax: no favourite
 *  either, and the latched progress reaches 1 - SETTLE_FRAC: the end rule) and to 12c at 125 minutes (B at 88c, in the
 *  band, stable from 130): the favourite leg on B is placeable only after the end rule, which production's entry block
 *  stops and the settle-hold stick (TENNIS_END_LOSER_CUT=false) does not. */
const lateFav = (min: number): number => (min < 5 ? 0.78 : min < 100 ? 0.7 : min < 125 ? 0.04 : 0.12);

test('tennis TA sweep, window arm under the settle-hold stick: an entry plan at or after the end rule is no instance (each leg at most once a match) though the stick\'s P&L arm takes it', async () => {
  const hist = fs.mkdtempSync(path.join(os.tmpdir(), 'tth-')), dir = path.join(hist, 'replay');
  const day = '2026-03-06', EV = 'KXATPMATCH-H1', A = `${EV}-A`, B = `${EV}-B`;
  writeScriptedHistory(hist, day, [{ id: 'H1', winA: false, startHour: 10, p: lateFav }]);
  await buildHistoryReplay({ historyDir: hist, outDir: dir, assets: [], fromDay: day, toDay: '2026-03-07', tennisSeries: ['KXATPMATCH'], log: () => {} });
  const candlesOf = candlesOfHistory(hist, day);
  const mcA = candlesOf(A)!, mcB = candlesOf(B)!;
  const HOLD = { ...LOOSE, TENNIS_END_LOSER_CUT: false };
  // The P&L arms under F0 (the scripted prints wobble a cent around the price: a resting F1 bid never sees one through it).
  const specs: SimSpec[] = [
    { id: 'A|s1|prod|settlehold|F0', overrides: HOLD, fill: 'F0' },
    { id: 'A|s1|t|F0', overrides: { ...LOOSE }, fill: 'F0' },
    { id: 'A|s1|prod|settlehold|window', overrides: HOLD, fill: 'F1', window: true },
    { id: 'A|s1|t|window', overrides: { ...LOOSE }, fill: 'F1', window: true },
  ];
  const grids: MatchGrid[] = [];
  const r = await runSweep({ dir, fromDay: day, toDay: '2026-03-07', stratum: 'H', specs, candlesOf, onGrid: (g) => grids.push(g) });
  assert.equal(r.matches, 1);
  const g = grids[0] as GridWithHigh;
  const start = Date.parse(`${day}T10:00:00Z`);
  const iHigh = Array.from(g.progressHigh).findIndex((p) => p >= 1 - SETTLE_FRAC - 1e-9);
  const endRule = g.t0 + iHigh * 1000 - 1000;
  assert.ok(endRule > start + 100 * MIN && endRule < start + 125 * MIN, `end rule at ${(endRule - start) / MIN} min`);
  const [pnl, pnlCut, hold, cut] = r.runs;
  // The stick's P&L arm does take the favourite (B) after the end rule, the cut being off (and holds it to settlement);
  // production's entry block stops that plan.
  const favEp = pnl.episodes.find((e) => e.leg === 'fav_entry');
  assert.ok(favEp !== undefined && favEp.t >= start + 125 * MIN, `the settle-hold P&L arm enters the favourite after the end rule (${favEp ? (favEp.t - start) / MIN : 'never'})`);
  assert.ok(favEp!.t > endRule);
  assert.equal(favEp!.x, 'settle');
  assert.ok(pnlCut.episodes.length > 0 && !pnlCut.episodes.some((e) => e.leg === 'fav_entry'), 'production\'s cut places no entry from the end-entry margin on');
  // Its window arm: the underdog instance only, once (not one per decision after the end rule), as under production's cut.
  assert.equal(hold.window, true);
  assert.deepEqual(hold.pnl, [0]);
  assert.equal(hold.episodes.length, 0);
  assert.equal(hold.instances!.length, 1, 'no entry plan at or after the end rule is an instance');
  const [u] = hold.instances!;
  assert.equal(u.leg, 'underdog');
  assert.equal(u.side, 'b');
  assert.equal(u.phase, 'pre');
  assert.ok(u.t < endRule);
  assert.deepEqual(u.outcome, windowOutcome(mcB, u.t, u.ask, u.level, endRule));
  assert.equal(u.outcome.resolvedBy, 'window');
  assert.equal(u.twins.length, 3);
  assert.deepEqual(u.twins, drawTwins(mcA, mcB, u.t, endRule, `${EV}|${specs[2].id}|underdog|${minuteKey(u.t)}`, 3, 10, u.side));
  assert.deepEqual(cut.instances!.map((x) => [x.leg, x.t, x.ask, x.C, x.level, x.outcome]), hold.instances!.map((x) => [x.leg, x.t, x.ask, x.C, x.level, x.outcome]));
});
