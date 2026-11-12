import assert from 'node:assert/strict';
import { test } from 'node:test';
import { takerFee } from '../bot/fees';
import type { KalshiCandle } from '../research/history/kalshiHistory';
import { FEES, hash32 as simHash32, PLACEBO_SEED as SIM_PLACEBO_SEED, rng as simRng } from '../research/tennisTaSim';
import {
  contractsFor, drawTwins, eligibleMinutes, endRuleTs, entryHour, gapStats, hash32, HIST_EDGES, histBin, levelFor, minuteCandles,
  newMinuteCandleStats, PLACEBO_SEED, poolRows, rng, twinSeed, WINDOW_FEES, WINDOW_VERSION, WindowAgg, windowOutcome, type MinuteCandle,
  type MinuteCandles, type WindowInstance, type WindowOutcome,
} from '../research/tennisTaWindow';

const MIN = 60_000, HOUR = 3_600_000;
const T0 = Date.parse('2026-03-02T14:00:00Z');
const near = (a: number, b: number, eps = 1e-9) => assert.ok(Math.abs(a - b) <= eps, `${a} != ${b}`);

/** A minute ending at T0 + k min. */
const cd = (k: number, bidL: number, bidC: number, askC: number): MinuteCandle => ({ ts: T0 + k * MIN, bidL, bidC, askC, twoSided: bidC > 0 && askC > bidC && askC < 1 });
/** One quote every minute from k0 to k1 (inclusive). */
const flat = (k0: number, k1: number, bidL: number, bidC: number, askC: number): MinuteCandles => { const out: MinuteCandles = []; for (let k = k0; k <= k1; k++) out.push(cd(k, bidL, bidC, askC)); return out; };
const kc = (k: number, p: Partial<KalshiCandle> = {}): KalshiCandle => ({ ts: T0 + k * MIN, bidO: 0.3, bidH: 0.31, bidL: 0.29, bidC: 0.3, askO: 0.32, askH: 0.33, askL: 0.31, askC: 0.32, last: 0.31, volume: 10, oi: 100, ...p });

// ---- Constants and the sim's seed helpers ------------------------------------------------------------------------------

test('tennisTaWindow: version, edges and the sim parity of the seed helpers', () => {
  assert.equal(WINDOW_VERSION, 'tennis-ta-window/1');
  assert.deepEqual(HIST_EDGES, { tWin: [1, 2, 3, 5, 10, 15, 30, 60, 120], lenWin: [1, 2, 3, 5, 10, 20, 40], dip: [0, -0.01, -0.02, -0.03, -0.05, -0.08, -0.12, -0.20], held: [0, 1, 2, 5, 10, 20, 40, 80] });
  assert.equal(PLACEBO_SEED, SIM_PLACEBO_SEED);
  assert.equal(WINDOW_FEES.takerMultiplier, FEES.takerMultiplier);
  assert.equal(WINDOW_FEES.makerMultiplier, FEES.makerMultiplier);
  // The copies of hash32 and rng must stay identical to the sim's (the sim imports this module, so they cannot be shared).
  for (const s of ['', 'a', 'KXATPMATCH-M1|A|s1|m0.01|f0.2|o0.01|w60|underdog|2026-03-02T14:05', 'unicode é中']) assert.equal(hash32(s), simHash32(s));
  for (const seed of [0, 1, 20261105, 0xffffffff, twinSeed('x|y|z|1')]) {
    const a = rng(seed), b = simRng(seed);
    for (let i = 0; i < 8; i++) assert.equal(a(), b());
  }
  assert.equal(twinSeed('k'), (SIM_PLACEBO_SEED ^ simHash32('k')) >>> 0);
});

// ---- Candles ---------------------------------------------------------------------------------------------------------

test('minuteCandles: drops the first stored candle, sorts, keeps the close minute, flags one-sided books', () => {
  const close = T0 + 5 * MIN;
  const stored: KalshiCandle[] = [
    kc(0), // the market's first stored candle: dropped as historyReplay drops it
    kc(1),
    kc(3, { bidL: 0.2, bidC: 0.25, askC: 0.27 }), // out of order: sorted
    kc(2, { bidL: null, bidC: 0.28, askC: 0.3 }), // no low stored: the close stands in
    kc(4, { bidL: null, bidC: null, askC: null }), // no book: NaN, not two-sided
    kc(5, { bidL: 0.33, bidC: 0.34, askC: 1 }), // ask at 1.00: not two-sided; ends at the close: kept
    kc(6), // after the close: dropped
  ];
  const stats = newMinuteCandleStats();
  const mc = minuteCandles(stored, close, stats);
  assert.deepEqual(mc.map((c) => (c.ts - T0) / MIN), [1, 2, 3, 4, 5]);
  // 5 minutes kept; one of them (minute 2) had no low and took its close; minute 4 had no book at all (not a substitution).
  assert.deepEqual(stats, { candles: 5, noLow: 1 });
  assert.deepEqual(minuteCandles(stored, close), mc); // the accumulator is optional and changes nothing else
  assert.deepEqual(mc[0], { ts: T0 + MIN, bidL: 0.29, bidC: 0.3, askC: 0.32, twoSided: true });
  assert.equal(mc[1].bidL, 0.28);
  assert.equal(mc[1].twoSided, true);
  assert.equal(mc[2].bidL, 0.2);
  assert.ok(Number.isNaN(mc[3].bidL) && Number.isNaN(mc[3].bidC) && Number.isNaN(mc[3].askC));
  assert.equal(mc[3].twoSided, false);
  assert.equal(mc[4].twoSided, false);
  assert.deepEqual(minuteCandles([kc(0)], close), []);
  assert.deepEqual(minuteCandles([], close), []);
});

test('minuteCandles: the window rule reads the LOW; a closes-only fixture is judged on closes, and the stats say so for every minute', () => {
  const close = T0 + 10 * MIN;
  // Lows stored (Kalshi's own history): minute 3's close sits at 0.35 but its low at 0.33 -> no window at level 0.35.
  const lows: KalshiCandle[] = [kc(0), kc(1), kc(2), kc(3, { bidL: 0.33, bidC: 0.35, askC: 0.37 }), kc(4, { bidL: 0.35, bidC: 0.36, askC: 0.38 })];
  const st = newMinuteCandleStats();
  const mc = minuteCandles(lows, close, st);
  assert.deepEqual(st, { candles: 4, noLow: 0 });
  // Entered at minute 1's end, so minute 2 (low 0.29) is the first full minute after the buy and in the dip.
  let o = windowOutcome(mc, T0 + 1 * MIN, 0.30, 0.35, close);
  assert.equal(o.resolvedAt, T0 + 4 * MIN);
  near(o.dip, 0.29 - 0.30);
  // The same minutes with the low struck (a closes-only fixture): the close stands in, minute 3 becomes the window (the
  // overstatement the count exists for), and every kept minute is counted as noLow.
  const closes = lows.map((c) => ({ ...c, bidL: null }));
  const st2 = newMinuteCandleStats();
  const mc2 = minuteCandles(closes, close, st2);
  assert.deepEqual(st2, { candles: 4, noLow: 4 });
  o = windowOutcome(mc2, T0 + 1 * MIN, 0.30, 0.35, close);
  assert.equal(o.resolvedAt, T0 + 3 * MIN);
  // One accumulator across markets adds up; a candle without a close bid is no substitution.
  minuteCandles([kc(0), kc(5, { bidL: null, bidC: null, askC: null }), kc(6, { bidL: null })], close, st2);
  assert.deepEqual(st2, { candles: 6, noLow: 5 });
});

// ---- Contracts and the level -------------------------------------------------------------------------------------------

test('contractsFor: max(1, floor($10 / ask))', () => {
  assert.equal(contractsFor(0.30), 33);
  assert.equal(contractsFor(0.20), 50);
  assert.equal(contractsFor(0.5), 20);
  assert.equal(contractsFor(0.95), 10);
  assert.equal(contractsFor(0.99), 10);
  assert.equal(contractsFor(0.01), 1000);
  assert.equal(contractsFor(0.07), 142);
  assert.equal(contractsFor(0.3, 20), 66);
  assert.equal(contractsFor(12), 1);
  assert.equal(contractsFor(0), 1);
});

test('levelFor: ask 0.30 x 33 is 0.35 (hand-computed), ask 0.20 x 50 is 0.24, and a literal dollars search agrees', () => {
  // bot/fees.ts takerFee: 0.07 x C x P x (1 - P), rounded up to the cent.
  //   entry fee:  0.07 x 33 x 0.30 x 0.70 = 0.4851 -> 0.49
  //   cost = 0.30 x 33 + 0.49 + 0.01 x 33 = 9.90 + 0.49 + 0.33 = 10.72
  //   L = 0.33: 0.07 x 33 x 0.33 x 0.67 = 0.510741 -> 0.52; 10.89 - 0.52 = 10.37 < 10.72
  //   L = 0.34: 0.07 x 33 x 0.34 x 0.66 = 0.518364 -> 0.52; 11.22 - 0.52 = 10.70 < 10.72
  //   L = 0.35: 0.07 x 33 x 0.35 x 0.65 = 0.525525 -> 0.53; 11.55 - 0.53 = 11.02 >= 10.72  -> L = 0.35
  assert.equal(takerFee(33, 0.30, WINDOW_FEES), 0.49);
  assert.equal(takerFee(33, 0.34, WINDOW_FEES), 0.52);
  assert.equal(takerFee(33, 0.35, WINDOW_FEES), 0.53);
  assert.equal(levelFor(0.30, 33), 0.35);
  assert.equal(levelFor(0.30, 33, FEES), 0.35); // the sim's schedule (no balance precision) rounds to the cent too
  //   entry fee:  0.07 x 50 x 0.20 x 0.80 = 0.56 -> 0.56; cost = 10.00 + 0.56 + 0.50 = 11.06
  //   L = 0.23: 0.07 x 50 x 0.23 x 0.77 = 0.61985 -> 0.62; 11.50 - 0.62 = 10.88 < 11.06
  //   L = 0.24: 0.07 x 50 x 0.24 x 0.76 = 0.6384  -> 0.64; 12.00 - 0.64 = 11.36 >= 11.06 -> L = 0.24
  assert.equal(levelFor(0.20, 50), 0.24);
  // An ask of 0.99 can never be exited at a profit under a 0.99 cap: the level lies above 0.99 (no window, by the rule).
  assert.ok(levelFor(0.99, 10) > 0.99);
  // The same inequality written in dollars, cent by cent.
  for (let a = 5; a <= 95; a += 5) {
    const ask = a / 100, C = contractsFor(ask);
    const cost = ask * C + takerFee(C, ask, WINDOW_FEES) + 0.01 * C;
    let L = NaN;
    for (let lc = a; lc <= 100; lc++) { const l = lc / 100; if (l * C - takerFee(C, l, WINDOW_FEES) >= cost - 1e-9) { L = l; break; } }
    assert.equal(levelFor(ask, C), L, `ask ${ask}`);
    assert.ok(L > ask);
  }
});

// ---- The window --------------------------------------------------------------------------------------------------------

/** Minutes 5..12 and 14 (13 missing) around an entry at 14:05:30 at ask 0.30, level 0.35. */
const path = (): MinuteCandles => [
  cd(5, 0.29, 0.30, 0.31), // ends before the entry: not in the horizon
  cd(6, 0.28, 0.30, 0.32),
  cd(7, 0.27, 0.31, 0.33), // the lowest bid before the window
  cd(8, 0.33, 0.35, 0.37), // close at the level, low under it: not a window
  cd(9, 0.35, 0.37, 0.39), // the window: 3.5 min after the entry
  cd(10, 0.36, 0.38, 0.40),
  cd(11, 0.35, 0.36, 0.38),
  cd(12, 0.34, 0.36, 0.38), // under the level: the run is 3 minutes
  cd(14, 0.36, 0.38, 0.40), // at the level again after a missing minute: held, not part of the run
];
const ENTRY = T0 + 5.5 * MIN, END = T0 + 60 * MIN;

test('windowOutcome: a window found, with tWin, lenWin, dip and held', () => {
  const o = windowOutcome(path(), ENTRY, 0.30, 0.35, END);
  assert.equal(o.win, true);
  assert.equal(o.resolvedBy, 'window');
  assert.equal(o.resolvedAt, T0 + 9 * MIN);
  assert.equal(o.tWin, 3.5);
  assert.equal(o.lenWin, 3);
  near(o.dip, 0.27 - 0.30);
  assert.equal(o.held, 4);
});

test('windowOutcome: no window runs to the close; the end rule cuts it; a cut before any minute; no minute at all', () => {
  // Level 0.40: no minute reaches it.
  let o = windowOutcome(path(), ENTRY, 0.30, 0.40, END);
  assert.deepEqual(o, { win: false, dip: o.dip, held: 0, resolvedBy: 'close', resolvedAt: T0 + 14 * MIN });
  near(o.dip, 0.27 - 0.30);
  // The end rule at 14:08:30: the horizon is minutes 6, 7 and 8; the window of minute 9 lies beyond it.
  o = windowOutcome(path(), ENTRY, 0.30, 0.35, T0 + 8.5 * MIN);
  assert.deepEqual(o, { win: false, dip: o.dip, held: 0, resolvedBy: 'end', resolvedAt: T0 + 8.5 * MIN });
  near(o.dip, 0.27 - 0.30);
  // The end rule exactly at the window minute's end: at or before -> a window.
  assert.equal(windowOutcome(path(), ENTRY, 0.30, 0.35, T0 + 9 * MIN).win, true);
  // The end rule before the first minute after the entry: cut with nothing seen.
  o = windowOutcome(path(), ENTRY, 0.30, 0.35, T0 + 5.75 * MIN);
  assert.equal(o.resolvedBy, 'end');
  assert.ok(Number.isNaN(o.dip));
  assert.equal(o.held, 0);
  // No minute after the entry, or no minutes: none.
  o = windowOutcome(path(), T0 + 20 * MIN, 0.30, 0.35, END);
  assert.deepEqual(o, { win: false, dip: NaN, held: 0, resolvedBy: 'none' });
  assert.deepEqual(windowOutcome([], ENTRY, 0.30, 0.35, END), { win: false, dip: NaN, held: 0, resolvedBy: 'none' });
});

test('windowOutcome: a one-sided minute is not a window; a window in the first minute has no dip; a window at the entry minute boundary', () => {
  const p = path();
  p[4] = { ...p[4], askC: 1, twoSided: false }; // minute 9 at the level, but no ask
  let o = windowOutcome(p, ENTRY, 0.30, 0.35, END);
  assert.equal(o.resolvedAt, T0 + 10 * MIN);
  assert.equal(o.tWin, 4.5);
  assert.equal(o.lenWin, 2);
  assert.equal(o.held, 3);
  near(o.dip, 0.27 - 0.30); // minute 9's low (0.35) is above 0.27 anyway
  // Entry at 14:08:30: minute 9 (14:08-14:09) began before the buy and is never a window (Amendment 4a item 1); the first
  // full minute after the buy (10, low 0.36) is the window, 1.5 min after the entry; nothing before it -> dip NaN.
  o = windowOutcome(path(), T0 + 8.5 * MIN, 0.30, 0.35, END);
  assert.equal(o.win, true);
  assert.equal(o.resolvedAt, T0 + 10 * MIN);
  assert.equal(o.tWin, 1.5);
  assert.ok(Number.isNaN(o.dip));
  // An entry at a minute's end (a twin): that minute is not after the entry.
  o = windowOutcome(path(), T0 + 9 * MIN, 0.37, 0.41, END);
  assert.equal(o.win, false);
  assert.equal(o.held, 0);
  near(o.dip, 0.34 - 0.37);
});

test('windowOutcome: the entry\'s own minute is never a window (Amendment 4a item 1: a full minute after the buy); a twin never has one either', () => {
  // The instance: entered at 14:08:05 at the synthetic book's ask of the previous close (0.30, level 0.35). Minute 9
  // (14:08-14:09, low 0.35) began before the buy, so its low covers time before the purchase: not a window. Minute 10
  // (14:09-14:10, low 0.36) is the first full minute after the buy -> the window, 1 min 55 s after the entry.
  const o = windowOutcome(path(), T0 + 8 * MIN + 5_000, 0.30, 0.35, END);
  assert.equal(o.win, true);
  assert.equal(o.resolvedAt, T0 + 10 * MIN);
  near(o.tWin!, 115 / 60);
  assert.equal(histBin(HIST_EDGES.tWin, o.tWin!), 1);
  const idx = new Map([['E1', 0]]);
  const agg = new WindowAgg('x|window', 'underdog', idx);
  agg.add({ event: 'E1', side: 'b', leg: 'underdog', t: T0 + 8 * MIN + 5_000, ask: 0.30, C: 33, level: 0.35, phase: 'p1', outcome: o, twins: [] });
  assert.equal(agg.row().hist.tWin[0], 0);
  assert.equal(agg.row().hist.tWin[1], 1);
  // An entry 1 s into a minute whose low alone reaches the level, with nothing after it: no window at all.
  const lone: MinuteCandles = [cd(1, 0.29, 0.30, 0.31), cd(2, 0.40, 0.41, 0.42)];
  assert.equal(windowOutcome(lone, T0 + 1 * MIN + 1_000, 0.31, 0.35, END).win, false);
  // A twin enters at a candle's END at that candle's close ask: the candle is not after its entry, so its first candidate is
  // the next minute and tWin is a whole number of minutes >= 1. On a rising market every twin finds a window; none in its own minute.
  const rise = (k: number) => { const bid = Math.min(0.90, 0.30 + 0.004 * k); return cd(k, bid, bid, +(bid + 0.02).toFixed(2)); };
  const mcA: MinuteCandles = [], mcB: MinuteCandles = [];
  for (let k = -60; k <= 150; k++) { mcA.push(rise(k)); mcB.push(rise(k)); }
  let wins = 0;
  for (let i = 0; i < 30; i++) for (const t of drawTwins(mcA, mcB, T0 + 30.5 * MIN, T0 + 150 * MIN, `own|${i}`)) {
    if (!t.outcome.win) continue;
    wins++;
    assert.ok(t.outcome.tWin! >= 1, `twin tWin ${t.outcome.tWin}`);
    assert.equal(t.outcome.tWin! % 1, 0);
    assert.ok(histBin(HIST_EDGES.tWin, t.outcome.tWin!) >= 1);
  }
  assert.ok(wins > 60, `${wins} twin windows`);
});

// ---- Twins -------------------------------------------------------------------------------------------------------------

test('eligibleMinutes: after the second stored candle, at or before the end rule, two-sided, ask in [0.05, 0.95]', () => {
  const mc: MinuteCandles = [
    cd(1, 0.5, 0.5, 0.52), // the second stored candle: not eligible
    cd(2, 0.5, 0.5, 0.52),
    cd(3, 0.94, 0.94, 0.95), // 0.95: in
    cd(4, 0.95, 0.95, 0.96), // 0.96: out
    cd(5, 0.03, 0.04, 0.05), // 0.05: in
    cd(6, 0.03, 0.03, 0.04), // 0.04: out
    cd(7, 0.5, 0.5, 0.5), // crossed / one level: out
    cd(8, NaN, NaN, NaN),
    cd(9, 0.5, 0.5, 0.52),
    cd(10, 0.5, 0.5, 0.52), // after the end rule: out
  ];
  assert.deepEqual(eligibleMinutes(mc, T0 + 9 * MIN).map((c) => (c.ts - T0) / MIN), [2, 3, 5, 9]);
  assert.deepEqual(eligibleMinutes(mc, T0 + 9 * MIN, 0.1, 0.9).map((c) => (c.ts - T0) / MIN), [2, 9]);
  assert.deepEqual(eligibleMinutes([], END), []);
});

test('entryHour: the UTC hour of the entry minute\'s end', () => {
  assert.equal(entryHour(T0 + 30.5 * MIN), Math.floor(T0 / HOUR));
  assert.equal(entryHour(T0 + 59.5 * MIN), Math.floor(T0 / HOUR) + 1);
  assert.equal(entryHour(T0 + 59 * MIN), Math.floor(T0 / HOUR));
});

test('drawTwins: three twins in the entry hour, deterministic in the seed, a fair coin over the sides', () => {
  const mcA = flat(-60, 150, 0.58, 0.59, 0.61), mcB = flat(-60, 150, 0.37, 0.39, 0.41);
  const end = T0 + 150 * MIN, entry = T0 + 30.5 * MIN;
  const key = 'KXATPMATCH-M1|A|s1|m0.01|f0.2|o0.01|w60|underdog|2026-03-02T14:30';
  const tw = drawTwins(mcA, mcB, entry, end, key);
  assert.equal(tw.length, 3);
  for (const t of tw) {
    assert.ok(t.side === 'a' || t.side === 'b');
    assert.ok(t.ts >= T0 && t.ts < T0 + HOUR, 'in the entry hour');
    assert.equal((t.ts - T0) % MIN, 0);
    assert.equal(t.ask, t.side === 'a' ? 0.61 : 0.41);
    assert.equal(t.C, contractsFor(t.ask));
    assert.equal(t.level, levelFor(t.ask, t.C));
    assert.deepEqual(t.outcome, windowOutcome(t.side === 'a' ? mcA : mcB, t.ts, t.ask, t.level, end));
  }
  assert.deepEqual(drawTwins(mcA, mcB, entry, end, key), tw);
  assert.notDeepEqual(drawTwins(mcA, mcB, entry, end, key + '|other'), tw);
  assert.equal(drawTwins(mcA, mcB, entry, end, key, 5).length, 5);
  assert.deepEqual(drawTwins(mcA, mcB, entry, end, key, 2), tw.slice(0, 2));
  // The coin: both sides over many instances, neither side much more than the other.
  let a = 0, n = 0;
  for (let i = 0; i < 200; i++) for (const t of drawTwins(mcA, mcB, entry, end, `${key}|${i}`)) { n++; if (t.side === 'a') a++; }
  assert.equal(n, 600);
  assert.ok(a > 240 && a < 360, `a side ${a} of 600`);
  // Twins land all over the hour.
  const seen = new Set<number>();
  for (let i = 0; i < 100; i++) for (const t of drawTwins(mcA, mcB, entry, end, `${key}|${i}`)) seen.add((t.ts - T0) / MIN);
  assert.ok(seen.size > 40, `${seen.size} distinct minutes`);
});

test('drawTwins: the whole eligible span when the hour holds fewer than 5 eligible minutes; a side without minutes draws none', () => {
  const mcA = flat(-60, 150, 0.58, 0.59, 0.61), mcB = flat(-60, 150, 0.37, 0.39, 0.41);
  // The end rule at 16:02: hour 16 holds minutes 120, 121 and 122 only -> the span from minute -59 to 122.
  const end = T0 + 122 * MIN, entry = T0 + 121.5 * MIN;
  let outside = 0, all = 0;
  for (let i = 0; i < 20; i++) for (const t of drawTwins(mcA, mcB, entry, end, `k|${i}`)) {
    all++;
    assert.ok(t.ts <= end && t.ts > T0 - 59 * MIN);
    if (Math.floor(t.ts / HOUR) !== entryHour(entry)) outside++;
  }
  assert.equal(all, 60);
  assert.ok(outside > 30, `${outside} of 60 outside the hour`);
  // Exactly 5 in the hour: the hour.
  const end5 = T0 + 124 * MIN, entry5 = T0 + 121.5 * MIN;
  for (let i = 0; i < 20; i++) for (const t of drawTwins(mcA, mcB, entry5, end5, `k|${i}`)) assert.ok(t.ts >= T0 + 120 * MIN && t.ts <= end5);
  // Market B never eligible (ask 0.97): only 'a' twins, at most 3.
  const mcB97 = flat(-60, 150, 0.95, 0.96, 0.97);
  let bs = 0, total = 0;
  for (let i = 0; i < 20; i++) { const tw = drawTwins(mcA, mcB97, entry, end, `k|${i}`); total += tw.length; for (const t of tw) if (t.side === 'b') bs++; assert.ok(tw.length <= 3); }
  assert.equal(bs, 0);
  assert.ok(total > 0 && total < 60);
  assert.deepEqual(drawTwins([], [], entry, end, 'k'), []);
});

// ---- Histogram bins ----------------------------------------------------------------------------------------------------

test('histBin: the edges, both directions, NaN in no bin', () => {
  const e = HIST_EDGES;
  assert.deepEqual([0.5, 1, 1.5, 2, 3.5, 119.9, 120, 200].map((v) => histBin(e.tWin, v)), [0, 1, 1, 2, 3, 8, 9, 9]);
  assert.deepEqual([1, 2, 3, 4, 40, 41].map((v) => histBin(e.lenWin, v)), [1, 2, 3, 3, 7, 7]);
  assert.deepEqual([-1, 0, 1, 4, 5, 79, 80, 1000].map((v) => histBin(e.held, v)), [0, 1, 2, 3, 4, 7, 8, 8]);
  // dip's edges run downward: bin 0 is dip > 0, bin 1 (-0.01, 0], bin 2 (-0.02, -0.01], ..., the last dip <= -0.20.
  assert.deepEqual([0.02, 0, -0.005, -0.01, -0.015, -0.03, -0.05, -0.19, -0.20, -0.5].map((v) => histBin(e.dip, v)), [0, 1, 1, 2, 2, 4, 5, 7, 8, 8]);
  assert.equal(histBin(e.dip, 0.27 - 0.30), 4); // float noise sits on the edge
  assert.equal(histBin(e.tWin, NaN), -1);
  assert.equal(histBin(e.held, Infinity), -1);
});

// ---- The row -----------------------------------------------------------------------------------------------------------

const outcome = (o: Partial<WindowOutcome>): WindowOutcome => ({ win: false, dip: NaN, held: 0, resolvedBy: 'none', ...o });
const twinOf = (win: boolean) => ({ side: 'a' as const, ts: T0, ask: 0.5, C: 20, level: 0.55, outcome: outcome({ win, resolvedBy: win ? 'window' : 'close' }) });
const inst = (p: Partial<WindowInstance>): WindowInstance => ({ event: 'E1', side: 'b', leg: 'underdog', t: ENTRY, ask: 0.30, C: 33, level: 0.35, phase: 'e20', outcome: outcome({}), twins: [], ...p });

test('WindowAgg: a C12 row indexed by the slice\'s events, with the histograms, phases, endNoWin and asks', () => {
  const idx = new Map([['E1', 0], ['E2', 1], ['E3', 2]]);
  const agg = new WindowAgg('A|s1|m0.01|f0.2|o0.01|w60|window', 'underdog', idx);
  agg.add(inst({ outcome: outcome({ win: true, tWin: 3.5, lenWin: 3, dip: -0.03, held: 4, resolvedBy: 'window', resolvedAt: T0 + 9 * MIN }), twins: [twinOf(true), twinOf(false), twinOf(false)] }));
  agg.add(inst({ phase: 'p1', ask: 0.40, outcome: outcome({ dip: -0.05, held: 0, resolvedBy: 'end', resolvedAt: END }), twins: [twinOf(false), twinOf(false), twinOf(false)] }));
  agg.add(inst({ event: 'E3', phase: 'pre', ask: 0.20, outcome: outcome({ resolvedBy: 'none' }) }));
  assert.equal(agg.count, 3);
  const row = agg.row();
  assert.equal(row.id, 'A|s1|m0.01|f0.2|o0.01|w60|window');
  assert.equal(row.leg, 'underdog');
  assert.deepEqual(row.n, [2, 0, 1]);
  assert.deepEqual(row.w, [1, 0, 0]);
  assert.deepEqual(row.tn, [6, 0, 0]);
  assert.deepEqual(row.tw, [1, 0, 0]);
  assert.deepEqual(row.hist.tWin, [0, 0, 0, 1, 0, 0, 0, 0, 0, 0]);
  assert.deepEqual(row.hist.lenWin, [0, 0, 0, 1, 0, 0, 0, 0]);
  assert.deepEqual(row.hist.dip, [0, 0, 0, 0, 1, 1, 0, 0, 0]); // the NaN dip of the third instance is in no bin
  assert.deepEqual(row.hist.held, [0, 2, 0, 1, 0, 0, 0, 0, 0]);
  assert.deepEqual(row.byPhase, { pre: [1, 0], e20: [1, 1], p1: [1, 0], p2: [0, 0], p3: [0, 0] });
  assert.equal(row.endNoWin, 1);
  assert.equal(row.asks[0], 3);
  near(row.asks[1], 0.9);
  // Family B: no leg key at all; an event outside the index is an error; the index may grow before row().
  const b = new WindowAgg('RSI|1m|up', undefined, idx);
  assert.ok(!('leg' in b.row()));
  assert.throws(() => b.add(inst({ event: 'E9' })), /E9/);
  idx.set('E4', 3);
  b.add(inst({ event: 'E4', leg: '' }));
  assert.deepEqual(b.row().n, [0, 0, 0, 1]);
  assert.deepEqual(agg.row().n, [2, 0, 1, 0]);
  // The 'both' row: the legs pooled.
  const fav = new WindowAgg(row.id, 'fav', idx);
  fav.add(inst({ event: 'E2', leg: 'fav', side: 'a', ask: 0.85, phase: 'p2', outcome: outcome({ win: true, tWin: 0.5, lenWin: 1, dip: NaN, held: 1, resolvedBy: 'window' }), twins: [twinOf(true), twinOf(true), twinOf(false)] }));
  const both = poolRows(row.id, [agg.row(), fav.row()], 'both');
  assert.equal(both.leg, 'both');
  assert.deepEqual(both.n, [2, 1, 1, 0]);
  assert.deepEqual(both.w, [1, 1, 0, 0]);
  assert.deepEqual(both.tn, [6, 3, 0, 0]);
  assert.deepEqual(both.tw, [1, 2, 0, 0]);
  assert.deepEqual(both.hist.tWin, [1, 0, 0, 1, 0, 0, 0, 0, 0, 0]);
  assert.deepEqual(both.byPhase, { pre: [1, 0], e20: [1, 1], p1: [1, 0], p2: [1, 1], p3: [0, 0] });
  assert.equal(both.endNoWin, 1);
  near(both.asks[1], 1.75);
  assert.equal(both.asks[0], 4);
});

// ---- The one test ------------------------------------------------------------------------------------------------------

test('gapStats: a 3-match fixture with a hand-computed cluster-robust SE, just under the bar', () => {
  // Match 1: n 2, w 2, tn 6, tw 2 -> d = 1 - 1/3 = 2/3;  match 2: 1, 0, 3, 1 -> d = -1/3;  match 3: 1, 1, 3, 0 -> d = 1.
  // gap = (2 x 2/3 - 1/3 + 1) / 4 = 2 / 4 = 0.5 (= rate 3/4 - random 3/12).
  // SE = sqrt(4 x (2/3 - 1/2)^2 + (-1/3 - 1/2)^2 + (1 - 1/2)^2) / 4 = sqrt(4/36 + 25/36 + 9/36) / 4 = sqrt(38) / 24 = 0.25685
  // z = 0.5 / 0.25685 = 1.9467 < 2: no pass.
  const g = gapStats([2, 1, 1], [2, 0, 1], [6, 3, 3], [2, 1, 0]);
  assert.deepEqual([g.n, g.w, g.tn, g.tw], [4, 3, 12, 3]);
  near(g.rate, 0.75);
  near(g.random, 0.25);
  near(g.gap, 0.5);
  near(g.se, Math.sqrt(38) / 24);
  near(g.z!, 0.5 / (Math.sqrt(38) / 24));
  assert.equal(g.pass, false);
});

test('gapStats: a pass, one match (SE 0: no z, Amendment 4a item 2), a match without twins, nothing', () => {
  // d = [5/6, 1, 1/3], weights 2: gap = 13/18; SE = (2/18) sqrt(4 + 25 + 49) / 6 = sqrt(78) / 54; z = 4.42.
  const g = gapStats([2, 2, 2], [2, 2, 1], [6, 6, 6], [1, 0, 1]);
  near(g.gap, 13 / 18);
  near(g.se, Math.sqrt(78) / 54);
  assert.equal(g.pass, true);
  assert.ok(g.z! > 4.4 && g.z! < 4.43);
  // One match: the cluster-robust SE is 0 by construction, so the gap's chance wobble cannot be measured: no z, no pass
  // (Amendment 4a item 2; the registry refuses se 0 too), whatever the gap's sign.
  let s = gapStats([1, 0], [1, 0], [3, 0], [0, 0]);
  assert.deepEqual([s.n, s.w, s.tn, s.tw, s.rate, s.random, s.gap, s.se, s.z, s.pass], [1, 1, 3, 0, 1, 0, 1, 0, null, false]);
  s = gapStats([1], [0], [3], [1]);
  near(s.gap, -1 / 3);
  assert.deepEqual([s.se, s.z, s.pass], [0, null, false]);
  s = gapStats([1], [1], [3], [3]);
  assert.deepEqual([s.gap, s.se, s.z, s.pass], [0, 0, null, false]);
  s = gapStats([2], [1], [6], [3]);
  assert.deepEqual([s.gap, s.se, s.z, s.pass], [0, 0, null, false]);
  // Identical d_i across matches: SE 0 too, the same verdicts.
  s = gapStats([1, 1, 1], [1, 1, 1], [3, 3, 3], [0, 0, 0]);
  assert.deepEqual([s.gap, s.se, s.z, s.pass], [1, 0, null, false]);
  s = gapStats([1, 1, 1], [0, 0, 0], [3, 3, 3], [1, 1, 1]);
  assert.deepEqual([s.se, s.z, s.pass], [0, null, false]);
  // The written rule holds wherever there is a z: pass <=> gap >= 2 x SE.
  for (const [n, w, tn, tw] of [[[2, 1, 1], [2, 0, 1], [6, 3, 3], [2, 1, 0]], [[2, 2, 2], [2, 2, 1], [6, 6, 6], [1, 0, 1]], [[3, 2], [2, 1], [9, 6], [3, 3]]] as number[][][]) {
    const g = gapStats(n, w, tn, tw);
    assert.ok(g.z !== null);
    assert.equal(g.pass, g.gap >= 2 * g.se);
  }
  // A match with instances but no twin is pooled into the rates, not into the cluster gap (here one match contributes: SE 0,
  // so no z).
  s = gapStats([1, 1], [1, 0], [3, 0], [0, 0]);
  assert.deepEqual([s.n, s.w, s.tn, s.tw, s.rate, s.random, s.gap, s.se, s.z, s.pass], [2, 1, 3, 0, 0.5, 0, 1, 0, null, false]);
  // Nothing at all, and twins without instances.
  s = gapStats([], [], [], []);
  assert.deepEqual([s.n, s.z, s.pass], [0, null, false]);
  assert.ok(Number.isNaN(s.rate) && Number.isNaN(s.gap) && Number.isNaN(s.se));
  s = gapStats([0, 0], [0, 0], [3, 3], [1, 0]);
  assert.deepEqual([s.n, s.tn, s.tw, s.z, s.pass], [0, 6, 1, null, false]);
  // Arrays of unequal length pad with 0 (a row fed before the event index grew).
  s = gapStats([2, 1, 1], [2, 0, 1], [6, 3, 3, 0], [2, 1]);
  near(s.gap, 0.5);
  near(s.se, Math.sqrt(38) / 24);
});

// ---- The end rule ------------------------------------------------------------------------------------------------------

test('endRuleTs: the first sample at 1 - settleFrac, capped at the close; the close when never', () => {
  const ph = new Float64Array([0, 0.5, 0.69, 0.7, 0.9]);
  const close = T0 + HOUR;
  assert.equal(endRuleTs(ph, T0, 1000, close), T0 + 3000);
  assert.equal(endRuleTs(ph, T0, 1000, T0 + 2000), T0 + 2000);
  assert.equal(endRuleTs(ph, T0, 1000, close, 0.5), T0 + 1000);
  assert.equal(endRuleTs(ph, T0, 1000, close, 0.05), close);
  assert.equal(endRuleTs(new Float64Array([0, 0.2, 0.6]), T0, 1000, close), close);
  assert.equal(endRuleTs(new Float64Array(0), T0, 1000, close), close);
  assert.equal(endRuleTs(new Float64Array([1 - 0.3]), T0, 1000, close), T0); // the bar's own float
});

test('drawTwins on the instance\'s own contract (Amendment 4a item 3): every twin on that side, the same minutes as the coin path draws for that side', () => {
  // Two markets of one match: A the favourite, B the underdog. With onSide every twin is on the instance's side; without it,
  // the coin splits them. The coin is drawn either way, so for the twins the coin happened to put on that side the minute
  // and the outcome are identical.
  const mcA: MinuteCandles = [], mcB: MinuteCandles = [];
  for (let k = 0; k <= 180; k++) { mcA.push(cd(k, 0.80, 0.81, 0.83)); mcB.push(cd(k, 0.17, 0.18, 0.19)); }
  const entry = T0 + 90.5 * MIN, end = T0 + 170 * MIN;
  let both = 0;
  for (let i = 0; i < 50; i++) {
    const key = `own-contract|${i}`;
    const onA = drawTwins(mcA, mcB, entry, end, key, 3, 10, 'a');
    const coin = drawTwins(mcA, mcB, entry, end, key, 3, 10);
    assert.equal(onA.length, 3);
    for (const t of onA) { assert.equal(t.side, 'a'); assert.equal(t.ask, 0.83); }
    coin.forEach((t, k) => { if (t.side === 'a') { both++; assert.deepEqual(t, onA[k]); } });
    for (const t of drawTwins(mcA, mcB, entry, end, key, 3, 10, 'b')) { assert.equal(t.side, 'b'); assert.equal(t.ask, 0.19); }
  }
  assert.ok(both > 30, `${both} coin twins on A`);
});
