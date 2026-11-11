// The exit-only lane (E06, bot/strategy/exitOnlyLane.ts): what the hunt lets the lane sell while the market cannot be priced,
// and the replay running the same lane as the engine (research/backtest.ts).
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { loadConfig } from '../bot/config';
import { DEFAULT_FEES } from '../bot/fees';
import { OrderBook } from '../bot/marketdata/orderBook';
import { MetaModel } from '../bot/model/metaModel';
import { ConfluenceRatchetExit, type HuntParams } from '../bot/strategy/exitPolicies';
import { runBacktest } from '../research/backtest';
import { writeSyntheticRecordings } from '../research/synthetic';
import { tmpDir } from './helpers';

/** A hunt on 10 YES whose entry value was 0.45: activated at a 0.50 bid, its stop locked at 0.47 (no wall below the bid). */
function hunted(h: Partial<HuntParams>): ConfluenceRatchetExit {
  const hunt = new ConfluenceRatchetExit({ targetMargin: 0.02, minConfluence: 2, ...h }, { minFillRatio: 1, minWallAgeMs: 3000, slippageTicks: 1 });
  const book = new OrderBook('T');
  book.applySnapshot({ bids: [{ price: 0.5, size: 50 }], asks: [{ price: 0.52, size: 50 }] }, 0);
  const on = hunt.update({ position: 10, qSide: 0.45, sideBid: 0.5, confluence: 3, book, now: 0, tick: 0.01, fees: DEFAULT_FEES });
  assert.deepEqual([on.mode, on.event, on.stop], ['hunt', 'activated', 0.47]);
  return hunt;
}
const at = (hunt: ConfluenceRatchetExit, sideBid: number) => hunt.armed({ position: 10, sideBid, tick: 0.01 });

test('hunt in the exit-only lane: the armed stop sells, a gap sells or lets go, and a judgement waits only when its outcome could hold', () => {
  // The plain trailing stop: under the stop within the slippage it sells at the stop less a tick; a gap above the entry value
  // sells at the bid; a gap below it ends the hunt in a full evaluation, so the lane lets the normal exit's take-profit act.
  const plain = hunted({ lockSale: 'off' });
  assert.deepEqual(at(plain, 0.48), { hunting: true, hold: false, stop: 0.47 });
  assert.deepEqual([at(plain, 0.46).hunting, at(plain, 0.46).event, at(plain, 0.46).plan?.price], [true, 'triggered', 0.46]);
  assert.deepEqual([at(plain, 0.45).hunting, at(plain, 0.45).event, at(plain, 0.45).plan?.price], [true, 'profit_take_gap', 0.45]);
  const gone = at(plain, 0.44);
  assert.deepEqual([gone.hunting, gone.plan], [false, undefined]);
  assert.match(gone.note!, /gapped under its stop 0\.47 and the entry value/);
  assert.equal(at(hunted({ lockSale: 'off', sellIntoGap: false }), 0.44).hunting, true, 'HUNT_SELL_INTO_GAP=false: a gap never sells, the stop waits');
  // The hybrid rule needs the model's value to sell at the stop: that waits; a gap sale needs none.
  const hybrid = hunted({ lockSale: 'off', hybrid: true });
  assert.deepEqual([at(hybrid, 0.46).hunting, at(hybrid, 0.46).plan], [true, undefined]);
  assert.equal(at(hybrid, 0.45).event, 'profit_take_gap');

  // The lock sale (the defaults: fair_value, judged at the first dip, else the normal exit). Above the stop it hunts; under it a
  // hit would sell at the bid and a miss hands the position to the normal exit, so the lane lets the take-profit act meanwhile.
  const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32) });
  const S = cfg.strategy;
  assert.deepEqual([S.huntLockSale, S.huntLockSaleElse, S.huntLockSaleAt], ['fair_value', 'exit', 'trigger'], 'the defaults this case covers');
  const lock = hunted({ lockSale: S.huntLockSale, lockSaleElse: S.huntLockSaleElse, lockSaleAt: S.huntLockSaleAt });
  assert.deepEqual(at(lock, 0.48), { hunting: true, hold: false, stop: 0.47 });
  for (const bid of [0.46, 0.44]) {
    const r = at(lock, bid);
    assert.deepEqual([r.hunting, r.plan], [false, undefined], `bid ${bid}`);
    assert.match(r.note!, /the lock sale's judgement waits for the fair value/);
  }
  // Under HUNT_LOCK_SALE_ELSE=hold a miss holds to settlement: nothing may sell until the judgement can be made.
  const hold = hunted({ lockSale: 'fair_value', lockSaleElse: 'hold' });
  assert.deepEqual([at(hold, 0.46).hunting, at(hold, 0.46).plan], [true, undefined]);
  // Read only: the hunt is as it was for the next full evaluation, which judges the dip itself.
  assert.equal(lock.active, true);
  const book = new OrderBook('T');
  book.applySnapshot({ bids: [{ price: 0.46, size: 50 }], asks: [{ price: 0.48, size: 50 }] }, 5000);
  const judged = lock.update({ position: 10, qSide: 0.6, sideBid: 0.46, fvSide: 0.6, confluence: 3, book, now: 5000, tick: 0.01, fees: DEFAULT_FEES });
  assert.deepEqual([judged.mode, judged.event], ['fair_value', 'lock_pass'], 'the bid under the fair value: handed to the normal exit');
});

test('replay: the exit-only lane sells armed take-profits while the index is stale, as the engine does; no entry goes out', async () => {
  const dir = path.join(tmpDir(), 'rec');
  writeSyntheticRecordings(dir, { windows: 6, seed: 12, marketNoise: 0.06 });
  // The settlement index goes quiet from minute 5 to minute 10 of every window (stale after RISK_MAX_INDEX_AGE_MS).
  const start = Date.parse('2026-01-01T00:00:00Z');
  const gaps = Array.from({ length: 6 }, (_, w) => { const open = start + (600 + w * 900) * 1000; return [open + 300_000, open + 600_000]; });
  const inGap = (t: number, margin = 0) => gaps.some(([a, b]) => t >= a + margin && t < b);
  const file = path.join(dir, fs.readdirSync(dir).find((f) => f.endsWith('.jsonl'))!);
  const kept = fs.readFileSync(file, 'utf8').trim().split('\n').filter((l) => { const e = JSON.parse(l) as { k: string; t: number }; return !(e.k === 'index' && inGap(e.t)); });
  fs.writeFileSync(file, kept.join('\n') + '\n');
  // The quota snipe and the profit mandate off: the take-profit is what sells.
  const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), STRATEGY_STYLE: 'both', PROFIT_MANDATE: 'false', PACER: 'false' });
  const r = await runBacktest(dir, MetaModel.identity(), cfg.strategy, cfg.risk, 200, { exitPolicy: 'take_profit', paper: { orderFrac: 0.1, orderUsd: 0 }, fillLog: true });
  // Fills well inside a gap (5 s past its start: nothing sent before it is still landing).
  const blind = (r.fillLog ?? []).filter((f) => inGap(f.t, 5_000));
  assert.ok(blind.some((f) => f.coid?.endsWith('-exit-tp')), `take-profit sales while the index is stale: ${JSON.stringify(blind)}`);
  assert.ok(blind.every((f) => f.coid?.includes('-exit-')), `only exits: ${JSON.stringify(blind.map((f) => f.coid))}`);
});
