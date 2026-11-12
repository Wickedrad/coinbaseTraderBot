import test from 'node:test';
import assert from 'node:assert/strict';
import { MinuteStream, compactBook, pickHourly, segmentEnd, MIN } from '../research/heatmap_live/captureCli';
import type { MarketInfo } from '../bot/kalshi/types';

const bar = (ts: number, c: number) => ({ ts, o: c, h: c, l: c, c, v: 1 });
const mk = (ticker: string, floorStrike: number, yesBid?: number, yesAsk?: number): MarketInfo =>
  ({ ticker, seriesTicker: 'KXBTCD', status: 'active', openTime: 0, closeTime: 1, floorStrike, strikeType: 'greater', yesBid, yesAsk, tickSize: 0.01 } as MarketInfo);

test('segments end on the 3-hour grid through 14:25 UTC, at least 20 minutes away', () => {
  const day = Date.UTC(2026, 10, 11);
  assert.equal(segmentEnd(day + 16 * 3600_000), day + (17 * 60 + 25) * MIN);
  assert.equal(segmentEnd(day + (14 * 60 + 10) * MIN), day + (17 * 60 + 25) * MIN, 'under 20 minutes left rolls to the next boundary');
  assert.equal(segmentEnd(day + (11 * 60 + 30) * MIN), day + (14 * 60 + 25) * MIN);
  assert.equal(segmentEnd(day + (23 * 60 + 40) * MIN), day + (26 * 60 + 25) * MIN, 'crosses midnight');
});

test('a short hole is filled flat, a long one passes through, old bars are dropped', () => {
  const s = new MinuteStream(3);
  assert.deepEqual(s.next(bar(0, 10)).map((b) => b.ts), [0]);
  const filled = s.next(bar(3 * MIN, 12));
  assert.deepEqual(filled.map((b) => [b.ts, b.c, b.v]), [[MIN, 10, 0], [2 * MIN, 10, 0], [3 * MIN, 12, 1]]);
  assert.equal(s.filled, 2);
  assert.deepEqual(s.next(bar(2 * MIN, 99)), [], 'not newer');
  assert.deepEqual(s.next(bar(10 * MIN, 13)).map((b) => b.ts), [10 * MIN], 'six missing minutes exceed the fill limit');
  assert.equal(s.breaks, 1);
});

test('hourly strikes: two-sided listings nearest 50c first, then nearest the coin price', () => {
  const ms = [mk('KXBTCD-X-T100', 100, 0.9, 0.93), mk('KXBTCD-X-T110', 110, 0.52, 0.56), mk('KXBTCD-X-T120', 120, 0.2, 0.24),
    mk('KXBTCD-X-T130', 130, 0, 0.01), mk('KXBTCD-X-T90', 90, 0.99, 1), mk('KXBTCD-X-B115', 115, 0.4, 0.5)];
  assert.deepEqual(pickHourly(ms, 112, 4).map((m) => m.floorStrike), [110, 120, 100, 130]);
  assert.deepEqual(pickHourly(ms, 95, 5).map((m) => m.floorStrike), [110, 120, 100, 90, 130], 'one-sided strikes rank by distance to the coin price');
  assert.deepEqual(pickHourly([], 100), []);
});

test('books keep the top levels of the YES side', () => {
  const b = compactBook({ bids: [{ price: 0.52, size: 10.004 }, { price: 0.51, size: 5 }, { price: 0.5, size: 1 }, { price: 0.49, size: 1 }], asks: [{ price: 0.5512345, size: 7 }] });
  assert.deepEqual(b, { yb: [[0.52, 10], [0.51, 5], [0.5, 1]], ya: [[0.5512, 7]] });
});
