import assert from 'node:assert/strict';
import { test } from 'node:test';
import { catalogTracking } from '../research/history/historyReplay';

const MIN = 60_000, T0 = Date.parse('2026-03-02T10:00:00Z');
const c = (ts: number, bidC: number | null, askC: number | null) => ({ ts, bidC, askC, last: null, volume: 0 });

test('history replay catalog: the 4 strikes nearest 50c by Kalshi quote are tracked, a 1c/99c far strike is not, tracked stays tracked', () => {
  // An hourly ladder of 8 strikes; quotes fall with the strike; the farthest shows a 1c/99c book (mid 50c is not a quote
  // the listing gives: Kalshi's listing mid needs bid > 0 and ask < 1, so 1c/99c counts; the live rule is mirrored as is).
  const mids = [0.97, 0.9, 0.75, 0.55, 0.45, 0.25, 0.1, 0.03];
  const kms = mids.map((m, i) => ({
    ticker: `KXBTCD-26MAR0211-T${100 + i}`, series: 'KXBTCD', event: 'KXBTCD-26MAR0211', openTime: T0, closeTime: T0 + 60 * MIN, strike: 100 + i, cap: null, strikeType: 'greater',
    candles: [c(T0 + MIN, +(m - 0.01).toFixed(2), +(m + 0.01).toFixed(2)), c(T0 + 30 * MIN, i === 7 ? 0.48 : +(m - 0.01).toFixed(2), i === 7 ? 0.52 : +(m + 0.01).toFixed(2))],
  }));
  const tr = catalogTracking(kms, { n: 4, horizonMs: 90 * MIN });
  assert.deepEqual([...tr.keys()].sort(), ['T102', 'T103', 'T104', 'T105', 'T107'].map((s) => `KXBTCD-26MAR0211-${s}`).sort());
  assert.equal(tr.get('KXBTCD-26MAR0211-T103'), T0, 'before any quote, the strikes nearest the middle of the ladder (the live fallback)');
  assert.equal(tr.get('KXBTCD-26MAR0211-T107'), T0 + 30 * MIN, 'picked when its quote came to the money');
  assert.equal(tr.has('KXBTCD-26MAR0211-T100'), false, 'deep in the money: never followed');
  // n = 0: every strike from its open.
  assert.equal(catalogTracking(kms, { n: 0, horizonMs: 90 * MIN }).size, 8);
  // Outside the horizon nothing is tracked yet.
  assert.equal(catalogTracking(kms.map((m) => ({ ...m, closeTime: T0 + 600 * MIN })), { n: 4, horizonMs: 90 * MIN }).get('KXBTCD-26MAR0211-T103'), T0 + 510 * MIN);
});
