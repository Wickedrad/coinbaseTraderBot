import test from 'node:test';
import assert from 'node:assert/strict';
import { exitLevel, scoreEntry, heatEntries, botEntries, summarize, compareGaps, callOf, report, RULES, type Capture, type Market, type Sample, type Forecast } from '../research/heatmap_live/score';

const S = 1000, MIN = 60 * S;
const m15 = (ticker = 'KXBTC15M-A', open = 0): Market => ({ ticker, asset: 'BTC', kind: '15m', openTime: open, closeTime: open + 15 * MIN, tickSize: 0.01 });
/** Book samples every 10 s; mid(t) gives the YES mid, quoted one cent either side. */
const path10 = (from: number, to: number, mid: (t: number) => number, size = 500): Sample[] => {
  const out: Sample[] = [];
  for (let t = from; t <= to; t += 10 * S) { const x = mid(t); out.push({ t, yb: Math.round((x - 0.01) * 100) / 100, ybs: size, ya: Math.round((x + 0.01) * 100) / 100, yas: size }); }
  return out;
};

test('exit level: entry + both fees + 1c a contract, on the price grid', () => {
  const m = { tickSize: 0.01 };
  assert.equal(exitLevel(0.30, 33, m), 0.35);
  assert.equal(exitLevel(0.50, 20, m), 0.55);
  assert.equal(exitLevel(0.70, 14, m), 0.74);
  assert.equal(exitLevel(0.99, 10, m), undefined, 'no price below $1 can pay for it');
  // A tapered grid: 0.1c ticks under 10c and over 90c, 1c between.
  const taper = { tickSize: 0.01, priceRanges: [{ start: 0, end: 0.1, step: 0.001 }, { start: 0.1, end: 0.9, step: 0.01 }, { start: 0.9, end: 1, step: 0.001 }] };
  assert.equal(exitLevel(0.50, 20, taper), 0.55);
  const hi = exitLevel(0.89, 11, taper)!;
  assert.ok(hi > 0.9 && hi < 0.93 && Math.abs(hi * 1000 - Math.round(hi * 1000)) < 1e-6, `fine ticks above 90c: ${hi}`);
});

test('a window needs the bid at the level for a full minute before the deadline', () => {
  const m = m15();
  // Entry at minute 2 at ask 0.51 (C=19): level 0.56. Mid jumps to 0.60 (bid 0.59) from minute 4 on.
  const up = path10(0, 15 * MIN, (t) => t >= 4 * MIN ? 0.60 : 0.50);
  const s = scoreEntry(m, up, 'yes', 2 * MIN);
  assert.equal(s.status, 'scored'); assert.equal(s.ask, 0.51); assert.equal(s.contracts, 19); assert.equal(s.level, 0.56);
  assert.equal(s.window, true); assert.equal(s.toWindowMs, 2 * MIN); assert.equal(s.windowDepth, true);
  assert.equal(scoreEntry(m, up, 'no', 2 * MIN).window, false, 'the other side never gets there');
  // 50 seconds at the level is not a window.
  const blip = path10(0, 15 * MIN, (t) => t >= 4 * MIN && t <= 4 * MIN + 50 * S ? 0.60 : 0.50);
  assert.equal(scoreEntry(m, blip, 'yes', 2 * MIN).window, false);
  // The move comes only in the last 90 seconds: too late.
  const late = path10(0, 15 * MIN, (t) => t >= 13.6 * MIN ? 0.60 : 0.50);
  assert.equal(scoreEntry(m, late, 'yes', 2 * MIN).window, false);
  // Thin bid: a window, but not with the size needed.
  const thin = path10(0, 15 * MIN, (t) => t >= 4 * MIN ? 0.60 : 0.50, 5);
  const t = scoreEntry(m, thin, 'yes', 2 * MIN);
  assert.equal(t.window, true); assert.equal(t.windowDepth, false);
});

test('entries without a usable book are named, never scored', () => {
  const m = m15(), flat = path10(0, 15 * MIN, () => 0.5);
  assert.equal(scoreEntry(m, flat, 'yes', 16 * MIN).status, 'no-book');
  assert.equal(scoreEntry(m, path10(0, 15 * MIN, () => 0.95), 'yes', 2 * MIN).status, 'out-of-band');
  assert.equal(scoreEntry(m, [{ t: 2 * MIN, yb: NaN, ybs: 0, ya: 0.5, yas: 10 }], 'yes', 2 * MIN).status, 'one-sided');
  const hole = flat.filter((s) => s.t < 5 * MIN || s.t > 7 * MIN);
  assert.equal(scoreEntry(m, hole, 'yes', 2 * MIN).status, 'incomplete');
  const cut = flat.filter((s) => s.t < 10 * MIN);
  assert.equal(scoreEntry(m, cut, 'yes', 2 * MIN).status, 'incomplete', 'the record stops before the deadline');
});

test('a real fill is scored at its own price, size and fee', () => {
  const m = m15(), up = path10(0, 15 * MIN, (t) => t >= 4 * MIN ? 0.53 : 0.50);
  // Bought 20 YES as a maker at 0.49 with no fee: needs 20b - fee >= 9.8 + 0.2 -> 0.52 (bid 0.52 from minute 4).
  const own = scoreEntry(m, up, 'yes', 2 * MIN, { band: false, own: { price: 0.49, contracts: 20, fee: 0 } });
  assert.equal(own.level, 0.52); assert.equal(own.window, true);
  assert.equal(scoreEntry(m, up, 'yes', 2 * MIN).window, false, 'the same entry at the ask (0.51) does not get a window');
});

function capture(n: number, upProb: (i: number) => boolean, call: (i: number) => 'up' | 'down'): Capture {
  const markets = new Map<string, Market>(), books = new Map<string, Sample[]>(), forecasts: Forecast[] = [];
  for (let i = 0; i < n; i++) {
    const open = i * 15 * MIN, m = m15(`KXBTC15M-${i}`, open), goesUp = upProb(i);
    markets.set(m.ticker, m);
    books.set(m.ticker, path10(open, open + 15 * MIN, (t) => t >= open + 5 * MIN ? (goesUp ? 0.62 : 0.38) : 0.50));
    for (let k = 1; k <= 10; k++) for (const horizon of [15, 60] as const) {
      const c = call(i), p = c === 'up' ? [0.37, 0.3, 0.33] : [0.33, 0.3, 0.37];
      forecasts.push({ asset: 'BTC', horizon, featureAt: open + k * MIN, publishedAt: open + k * MIN + 3 * S, p, uniform: p, prior: [0.36, 0.3, 0.34] });
    }
  }
  return { markets, books, forecasts };
}

test('a caller that is always right scores a full gap; a coin flip scores none', () => {
  const up = (i: number) => i % 2 === 0;
  const right = heatEntries(capture(40, up, (i) => up(i) ? 'up' : 'down'), 0, Infinity);
  const first = right.entries.filter((e) => e.contender === 'map15' && e.first);
  assert.equal(first.length, 40);
  const r = summarize(first);
  assert.equal(r.rate, 1); assert.equal(r.randomSide, 0.5); assert.equal(r.gap, 0.5); assert.equal(r.usualRate, 0.5); assert.equal(r.gapVsUsual, 0.5);
  assert.ok(first.every((e) => e.agree === true));
  // Calls unrelated to the outcome: the gap is about zero and well inside two standard errors.
  const noise = summarize(heatEntries(capture(200, up, (i) => (i * 7 + 3) % 5 < 2 ? 'up' : 'down'), 0, Infinity).entries.filter((e) => e.contender === 'map15' && e.first));
  assert.ok(Math.abs(noise.gap) < 2 * noise.gapSe + 0.05, `noise gap ${noise.gap} se ${noise.gapSe}`);
  // Every minute is an entry in the secondary count; minutes after the move are still scored.
  assert.ok(right.entries.filter((e) => e.contender === 'map15').length > 40);
  assert.equal(right.noEntry['map60:outside-entry-window'] > 0, true, 'no hourly contract was watched here');
});

test('the bot side: opening fills scored at the ask and at their own price, and compared', () => {
  const up = (i: number) => i % 2 === 0, c = capture(60, up, (i) => up(i) ? 'up' : 'down');
  // A bot that is always on the wrong side.
  const fills = Array.from({ length: 60 }, (_, i) => ({ ticker: `KXBTC15M-${i}`, side: (up(i) ? 'no' : 'yes') as 'yes' | 'no', ts: i * 15 * MIN + 2 * MIN, price: 0.49, count: 20, fee: 0 }));
  const b = botEntries(c, [...fills, { ticker: 'KXBTC15M-NOPE', side: 'yes', ts: 0, price: 0.5, count: 10, fee: 0 }], 0, Infinity);
  assert.equal(b.entries.length, 60); assert.equal(b.noEntry['bot:contract-not-watched'], 1);
  const r = summarize(b.entries);
  assert.equal(r.rate, 0); assert.equal(r.gap, -0.5); assert.equal(r.ownRate, 0);
  const h = heatEntries(c, 0, Infinity).entries.filter((e) => e.contender === 'map15' && e.first);
  const cmp = compareGaps(h, b.entries);
  assert.equal(cmp.diff, 1); assert.ok(cmp.se < 0.01);
  const rep = report(c, fills, 0, Infinity);
  assert.match(rep.markdown, /Heat map minus bot, 15-minute contracts/);
  assert.match(rep.markdown, /Contracts both entered: 60; same side on 0/);
});

test('ties make no call; the rules are the registered ones', () => {
  assert.equal(callOf([0.35, 0.3, 0.35]), null); assert.equal(callOf([0.36, 0.3, 0.34]), 'up'); assert.equal(callOf([0.3, 0.3, 0.4]), 'down');
  assert.deepEqual([RULES.stakeUsd, RULES.windowMs, RULES.m15.deadline, RULES.hourly.deadline, RULES.minSide, RULES.maxSide], [10, 60000, 90000, 360000, 0.1, 0.9]);
});
