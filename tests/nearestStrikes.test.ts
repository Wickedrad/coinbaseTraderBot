// Catalog trimming: only the strikes nearest the price in each ladder / bracket event are tracked.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { nearestStrikes } from '../bot/marketdata/marketData';

const kindOf = (series: string, st?: string) => (series.endsWith('15M') ? 'updown' : st === 'between' ? 'between' : 'greater');
const ladder = (event: string, from: number, step: number, count: number) =>
  Array.from({ length: count }, (_, i) => ({ ticker: `${event}-T${from + i * step}`, eventTicker: event, strikeType: 'greater', floorStrike: from + i * step }));

test('nearestStrikes: N nearest per event, 15-minute contracts untouched, tracked markets kept', () => {
  const ms = [...ladder('E1', 60000, 250, 80), ...ladder('E2', 60000, 250, 80)];
  const out = nearestStrikes(ms, kindOf, 'KXBTCD', 70000, 8, new Set());
  assert.equal(out.length, 16, '8 per event');
  assert.ok(out.every((m) => Math.abs(m.floorStrike - 70000) <= 1000));
  const held = nearestStrikes(ms, kindOf, 'KXBTCD', 70000, 8, new Set(['E1-T60000']));
  assert.ok(held.some((m) => m.ticker === 'E1-T60000'), 'a tracked (possibly held) market stays');
  const noPrice = nearestStrikes(ladder('E3', 60000, 250, 81), kindOf, 'KXBTCD', undefined, 4, new Set());
  assert.deepEqual(noPrice.map((m) => m.floorStrike).sort(), [69750, 70000, 70250, 70500].sort((a, b) => a - b).slice(0, 4).length ? noPrice.map((m) => m.floorStrike).sort() : [], 'no price: centred on the median strike');
  assert.ok(noPrice.every((m) => Math.abs(m.floorStrike - 70000) <= 500));
  const updown = [{ ticker: 'U1', eventTicker: 'X', strikeType: 'greater', floorStrike: 1 }];
  assert.equal(nearestStrikes(updown, kindOf, 'KXBTC15M', 70000, 1, new Set()).length, 1);
  assert.equal(nearestStrikes(ms, kindOf, 'KXBTCD', 70000, 0, new Set()).length, 160, '0 = track all');
});

// Decision 1 (Nov 5): the spread cap on the listing mid, two tiers, no last-price fallback.
const q = (ticker: string, strike: number, bid?: number, ask?: number, extra: Record<string, unknown> = {}) =>
  ({ ticker, eventTicker: 'E', strikeType: 'greater', floorStrike: strike, yesBid: bid, yesAsk: ask, yesMid: bid !== undefined && ask !== undefined && bid > 0 && ask > bid && ask < 1 ? (bid + ask) / 2 : undefined, ...extra });
const pick = (ms: any[], n: number, cap: number, price?: number, tracked: string[] = []) =>
  nearestStrikes(ms, kindOf, 'KXBTCD', price, n, new Set(tracked), { maxSpread: cap }).map((m) => m.ticker).sort();

test('strike cap: tight tails never push out a near-money strike that is briefly wide (ladder)', () => {
  // T3 is the money (44c/56c, 12c wide); the rest are tight tails.
  const ms = [q('T0', 100, 0.96, 0.97), q('T1', 101, 0.93, 0.95), q('T2', 102, 0.89, 0.9), q('T3', 103, 0.44, 0.56), q('T4', 104, 0.09, 0.11), q('T5', 105, 0.04, 0.05), q('T6', 106, 0.02, 0.03), q('T7', 107, 0.01, 0.02)];
  // Legacy picks by mid alone: T3 (50c) is kept there too, but with the cap and only tails tight, the index finds it.
  assert.ok(pick(ms, 2, 0.1, 103).includes('T3'), 'reached through the index');
  assert.ok(!pick(ms, 2, 0.1, 103).includes('T0'));
});

test('strike cap: a 24c/36c bucket on a range still makes it past tight 1c buckets', () => {
  const r = (t: string, i: number, bid: number, ask: number) => ({ ...q(t, i, bid, ask), strikeType: 'between', capStrike: i + 1 });
  const ms = [r('B0', 0, 0.01, 0.02), r('B1', 1, 0.02, 0.03), r('B2', 2, 0.24, 0.36), r('B3', 3, 0.15, 0.17), r('B4', 4, 0.01, 0.02), r('B5', 5, 0.01, 0.02)];
  const out = pick(ms, 2, 0.1, 2.5);
  assert.ok(out.includes('B2') && out.includes('B3'), out.join(','));
});

test('strike cap: 1c/99c and one-sided listings lose to a 48c/52c strike; fewer than half tight falls back to the index', () => {
  const ms = [q('D0', 100, 0.01, 0.99), q('D1', 101, undefined, 0.5, { yesMid: 0.5 }), q('D2', 102, 0.48, 0.52), q('D3', 103, 0.2, 0.22), q('D4', 104, 0.05, 0.06)];
  assert.deepEqual(pick(ms, 1, 0.1, 110), ['D2']);
  assert.ok(pick(ms, 1, 0, 110).length === 1, 'legacy still picks one');
  // Only 1 of 4 tight: the index decides.
  const few = [q('F0', 100, 0.01, 0.99), q('F1', 101, 0.01, 0.99), q('F2', 102, 0.48, 0.52), q('F3', 103, 0.01, 0.99)];
  const paths = { mid: 0, index: 0, median: 0 };
  assert.deepEqual(nearestStrikes(few, kindOf, 'KXBTCD', 100.2, 1, new Set(), { maxSpread: 0.1, paths }).map((m) => m.ticker), ['F0']);
  assert.deepEqual(paths, { mid: 0, index: 1, median: 0 });
});

test('strike cap: a tracked wide market is kept; maxSpread 0 reproduces the legacy picks', () => {
  const ms = [q('K0', 90, 0.01, 0.99), q('K1', 101, 0.48, 0.52), q('K2', 102, 0.3, 0.32), q('K3', 103, 0.1, 0.12)];
  assert.ok(pick(ms, 1, 0.1, undefined, ['K0']).includes('K0'));
  const legacy = nearestStrikes(ms, kindOf, 'KXBTCD', undefined, 2, new Set()).map((m) => m.ticker).sort();
  assert.deepEqual(pick(ms, 2, 0), legacy);
  assert.deepEqual(legacy, ['K0', 'K1'], 'legacy takes the dead 1c/99c listing as 50c');
  assert.deepEqual(pick(ms, 2, 0.1), ['K1', 'K2']);
});
