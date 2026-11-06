import assert from 'node:assert/strict';
import { test } from 'node:test';
import { COLS, type Grid } from '../research/perpTaSweep';
import { ho1Of } from '../research/perpTaBlind';
import {
  SLOW, dailyCloses, votes, sigma30, nextSide, simulate, dailyPriced, placebo, blockResult, evaluate, ruleHash, gateOf, sealedVerdict,
  type CoinRun, type Spot, type CoinCosts, type CoinData, type BlockResult,
} from '../research/perpTaSlow';
import type { Ho1 } from '../research/perpTaBlind';

const MPD = 1440, DAY = 86_400_000, NOVOTE = -128;
const T0 = Date.UTC(2021, 0, 1);
const BTC: CoinCosts = { half: 0.19, fundOff: 0 };

/** A perp grid whose spot and perp columns follow px (perp: pp, if given); each bar's high / low sit `wick` beyond its open
 *  and close. Funding instants every fundEvery minutes (the minute before each multiple) at `rate`. */
function grid(n: number, px: (i: number) => number, o: { pp?: (i: number) => number; wick?: number; fundEvery?: number; rate?: number; t0?: number; asset?: string } = {}): Grid {
  const c = Object.fromEntries(COLS.map((k) => [k, new Float32Array(n)])) as Grid['c'];
  const w = o.wick ?? 5e-4, pp = o.pp ?? px;
  for (let i = 0; i < n; i++) {
    const s = px(i), s0 = i ? px(i - 1) : s, p = pp(i), p0 = i ? pp(i - 1) : p;
    c.so[i] = s0; c.sc[i] = s; c.sh[i] = Math.max(s, s0) * (1 + w); c.sl[i] = Math.min(s, s0) * (1 - w); c.sv[i] = 1;
    c.po[i] = p0; c.pc[i] = p; c.ph[i] = Math.max(p, p0) * (1 + w); c.pl[i] = Math.min(p, p0) * (1 - w);
    c.valid[i] = 1;
  }
  if (o.fundEvery) for (let i = o.fundEvery - 1; i < n; i += o.fundEvery) c.fund[i] = o.rate ?? 1e-12;
  return { asset: o.asset ?? 'BTC', t0: o.t0 ?? T0, n, c, fundRaw: new Float32Array(n) };
}
/** Minutes [from, to) without a perp bar, as buildGrid leaves them: not valid, the perp bar a copy of the last close. */
function gap(g: Grid, from: number, to: number): void {
  for (let i = from; i < to; i++) { const c = g.c.pc[i - 1]; g.c.po[i] = g.c.ph[i] = g.c.pl[i] = g.c.pc[i] = c; g.c.valid[i] = 0; }
}
const spotOf = (n: number, px: (i: number) => number): Spot => ({ has: new Uint8Array(n).fill(1), close: Float64Array.from({ length: n }, (_, i) => px(i)) });
/** Piecewise drift per day (log return per day), continuous in minutes. */
function path(drifts: Array<[number, number]>, p0 = 100): (i: number) => number {
  const lv: number[] = [];
  let x = Math.log(p0), d = 0;
  for (const [days, g] of drifts) for (let k = 0; k < days * MPD; k++, d++) { lv.push(x); x += g / MPD; }
  lv.push(x);
  return (i) => Math.exp(lv[Math.min(i, lv.length - 1)]);
}
function lcg(seed: number) { let x = seed >>> 0; return () => ((x = (Math.imul(x, 1664525) + 1013904223) >>> 0) / 4294967296); }
const sum = (a: ArrayLike<number>) => Array.from(a).reduce((x, y) => x + y, 0);

test('perp TA slow: the daily close is the last spot bar of the 60 minutes before 00:00 UTC, else none', () => {
  const n = 3 * MPD, has = new Uint8Array(n), close = new Float64Array(n);
  has[MPD - 1] = 1; close[MPD - 1] = 10;            // day 1: the 23:59 bar
  has[2 * MPD - 30] = 1; close[2 * MPD - 30] = 20;  // day 2: 23:30 (23:59 missing)
  has[3 * MPD - 61] = 1; close[3 * MPD - 61] = 30;  // day 3: 22:59, outside the 60 minutes
  const C = dailyCloses({ has, close }, 3);
  assert.ok(Number.isNaN(C[0]));
  assert.equal(C[1], 10); assert.equal(C[2], 20); assert.ok(Number.isNaN(C[3]));
});

test('perp TA slow: the 7/14/28-day vote, sigma30 and the position rule', () => {
  const C = Float64Array.from({ length: 40 }, (_, k) => (k === 0 ? NaN : 100 * 1.01 ** k));
  const v = votes(C);
  assert.equal(v[27], NOVOTE, 'C[27 - 28] does not exist');
  assert.equal(v[28], NOVOTE, 'C[0] is missing (no close at the grid start)');
  assert.equal(v[29], 3);
  const D = C.slice(); D[20] = NaN;
  assert.equal(votes(D)[34], NOVOTE, 'C[34 - 14] missing: no vote');
  assert.equal(votes(D)[35], 3);
  // Alternating +-1% daily returns: sigma30 is their sample stdev; one missing close inside the window: NaN.
  const A = Float64Array.from({ length: 40 }, (_, k) => 100 * Math.exp(0.01 * (k % 2)));
  const s = sigma30(A), r = Array.from({ length: 30 }, (_, j) => (j % 2 ? -0.01 : 0.01));
  const m = sum(r) / 30, sd = Math.sqrt(r.reduce((a, b) => a + (b - m) ** 2, 0) / 29);
  assert.ok(Math.abs(s[35] - sd) < 1e-12); assert.ok(Number.isNaN(s[29]));
  // Positions (pre-registered item 3).
  const T: Array<[number, number, number]> = [
    [0, 3, 1], [0, 2, 0], [0, 1, 0], [0, 0, 0], [0, -1, 0], [0, -2, 0], [0, -3, -1],
    [1, 3, 1], [1, 1, 1], [1, 0, 1], [1, -1, 0], [1, -2, 0], [1, -3, -1],
    [-1, -3, -1], [-1, -1, -1], [-1, 0, -1], [-1, 1, 0], [-1, 2, 0], [-1, 3, 1],
    [1, NOVOTE, 1], [-1, NOVOTE, -1], [0, NOVOTE, 0],
  ];
  for (const [side, vv, want] of T) assert.equal(nextSide(side, vv), want, `side ${side}, vote ${vv}`);
});

test('perp TA slow: a planted daily trend is held long from the first day with 30 returns; maker entry at the peg', () => {
  const days = 120, n = days * MPD, px = path([[days, 0.005]]);
  const g = grid(n, px), r = simulate(g, spotOf(n, px), n, BTC);
  // Votes are +3 from boundary 29; sigma30 needs closes 1..31 (C[0] never exists): the entry is at boundary 31.
  assert.equal(r.entries.indexOf(1), 31);
  assert.equal(r.makerFills[31], 1); assert.equal(sum(r.takerFills), 0);
  assert.equal(r.trades.length, 1); assert.equal(r.trades[0].open, true, 'still held: reported as an open trade');
  assert.ok(Number.isNaN(r.trades[0].exitMin)); assert.equal(r.trades[0].entryMin, 31 * MPD);
  const q = g.c.pc[31 * MPD - 1] * (1 - 0.19e-4), qty = 250 / q;
  const expect = qty * (g.c.pc[n - 1] - q) - 250 * 5e-4;
  assert.ok(Math.abs(sum(r.mtm) - expect) < 1e-9 * Math.abs(expect), `${sum(r.mtm)} vs ${expect}`);
  assert.ok(sum(r.mtm) > 0);
  assert.ok(Math.abs(sum(r.fee) + 0.125) < 1e-12);
  // The reversed rule is short the same trend and loses.
  assert.ok(sum(simulate(g, spotOf(n, px), n, BTC, { variant: 'reversed' }).mtm) < 0);
});

test('perp TA slow: no trade-through, no maker fill; the taker fallback takes minute 61 (or the next bar after a gap)', () => {
  const days = 100, n = days * MPD, px = path([[60, 0.005], [40, -0.005]]);
  const g = grid(n, px, { pp: () => 100, wick: 0 }); // a flat perp: the peg is never traded through
  const r = simulate(g, spotOf(n, px), n, BTC);
  assert.equal(sum(r.makerFills), 0);
  assert.ok(r.trades.length >= 1);
  const t = r.trades[0];
  assert.equal(t.side, 1); assert.equal(t.entryMin, 31 * MPD + 60); assert.deepEqual(t.taker, [true, true]);
  const tk = (12 + 0.19) / 1e4;
  assert.ok(Math.abs(t.fees - 2 * 250 * tk) < 1e-9);
  assert.ok(Math.abs(r.fallbackExtra[31] - (250 * (tk - 5e-4) + 250 * 0.19e-4)) < 1e-9);
  assert.ok(Math.abs(t.usd + t.fees) < 1e-9, 'a flat perp: the trade loses its fees only');
  // No bar in minutes 61..71: the fallback takes minute 72.
  const g2 = grid(n, px, { pp: () => 100, wick: 0 });
  for (let i = 31 * MPD + 60; i <= 31 * MPD + 70; i++) g2.c.valid[i] = 0;
  assert.equal(simulate(g2, spotOf(n, px), n, BTC).trades[0].entryMin, 31 * MPD + 71);
});

test('perp TA slow: an order unfilled at the next 00:00 is carried to the first perp bar; that day\'s vote is not acted on', () => {
  const days = 60, n = days * MPD, px = path([[days, 0.005]]);
  const g = grid(n, px);
  gap(g, 31 * MPD, 32 * MPD + 30);
  const r = simulate(g, spotOf(n, px), n, BTC);
  assert.equal(r.carried, 1); assert.equal(r.carriedDay[32], 1); assert.equal(r.ordersDay[32], 0);
  assert.equal(r.entries[31], 0); assert.equal(r.entries[32], 1);
  assert.equal(r.trades[0].entryMin, 32 * MPD + 30); assert.deepEqual(r.trades[0].taker, [true]);
  // A minute with a perp bar but no spot bar (not valid in the grid) still fills a resting order.
  const g2 = grid(n, px);
  for (let i = 31 * MPD; i < 31 * MPD + 5; i++) g2.c.valid[i] = 0;
  const r2 = simulate(g2, spotOf(n, px), n, BTC);
  assert.equal(r2.makerFills[31], 1); assert.equal(r2.trades[0].entryMin, 31 * MPD);
});

test('perp TA slow: a crash through all three lookbacks reverses long to short in one order', () => {
  const days = 70, n = days * MPD, base = path([[days, 0.005]]);
  const px = (i: number) => base(i) * (i >= 41 * MPD - 1 ? 0.8 : 1);
  const r = simulate(grid(n, px), spotOf(n, px), n, BTC);
  assert.equal(r.trades[0].side, 1); assert.equal(r.trades[1].side, -1); assert.equal(r.trades[1].entryMin, 41 * MPD);
  assert.equal(r.trades[0].exitMin, 41 * MPD);
  assert.ok(r.notional[41] < 0, 'short after the reversal'); assert.equal(r.makerFills[41], 1);
  const [l, s] = r.trades;
  assert.ok(s.qty * s.entryPx < 250, "the crash lifts sigma30: a smaller short");
  assert.ok(Math.abs(r.fees[41] - (l.qty * l.exitPx + s.qty * s.entryPx) * 5e-4) < 1e-9, "one fill, both legs at maker");
});

test('perp TA slow: longs pay funding at each instant (the offset added), shorts receive it; zero-rate instants move nothing', () => {
  const days = 60, n = days * MPD, px = path([[days, 0.005]]), h = 0.19e-4;
  const f32 = Math.fround(1e-4);
  const g = grid(n, px, { pp: () => 100, fundEvery: 480, rate: 1e-4 });
  const r = simulate(g, spotOf(n, px), n, { half: 0.19, fundOff: 1 });
  // Entry filled at minute 31 x 1440 (= 480 x 93); instants at 480m - 1 for m = 94 .. 180.
  const per = (250 / (100 * (1 - h))) * 100 * (f32 + 1e-4);
  assert.ok(Math.abs(sum(r.fund) + 87 * per) < 1e-9, `${sum(r.fund)} vs ${-87 * per}`);
  const s = simulate(g, spotOf(n, px), n, { half: 0.19, fundOff: 1 }, { variant: 'always-short' });
  assert.ok(sum(s.fund) > 0);
  const st = simulate(g, spotOf(n, px), n, { half: 0.19, fundOff: 1, paidMult: 1.5 });
  assert.ok(Math.abs(sum(st.fund) - 1.5 * sum(r.fund)) < 1e-9);
  const off0 = simulate(g, spotOf(n, px), n, { half: 0.19, fundOff: 1, offMult: 0 });
  assert.ok(Math.abs(sum(off0.fund) + 87 * (250 / (100 * (1 - h))) * 100 * f32) < 1e-9);
  const z = simulate(grid(n, px, { pp: () => 100, fundEvery: 480 }), spotOf(n, px), n, BTC);
  assert.equal(sum(z.fund), 0);
});

test('perp TA slow: every day MTM = price + fees + funding, and the tercile $ add up to it', () => {
  const days = 200, n = days * MPD, rnd = lcg(7), drift = [[50, 0.006], [50, -0.006], [50, 0.004], [50, -0.003]] as Array<[number, number]>;
  const base = path(drift), noise = Float64Array.from({ length: n }, () => 1 + 0.002 * (rnd() - 0.5));
  const px = (i: number) => base(i) * noise[i];
  const g = grid(n, px, { fundEvery: 480, rate: 2e-4 });
  const ter = Int8Array.from({ length: n }, (_, i) => Math.floor(i / 600) % 3);
  for (const variant of ['rule', 'reversed', 'taker', 'always-long'] as const) {
    const r = simulate(g, spotOf(n, px), n, { half: 0.19, fundOff: 1.66 }, { variant, ter });
    for (let k = 0; k < r.nDays; k++) {
      assert.ok(Math.abs(r.mtm[k] - (r.price[k] + r.fee[k] + r.fund[k])) < 1e-9, `${variant} day ${k}`);
      assert.ok(Math.abs(r.mtm[k] - (r.terUsd[3 * k] + r.terUsd[3 * k + 1] + r.terUsd[3 * k + 2])) < 1e-9, `${variant} terciles day ${k}`);
    }
    assert.ok(r.trades.length > 0 || variant === 'always-long', variant);
    // The hourly attribution adds up to the book's MTM (every minute is in a tercile here).
    assert.ok(Math.abs(sum(r.hourTerUsd) - sum(r.mtm)) < 1e-6, `${variant} hourly attribution`);
    assert.equal(sum(r.terMinutes), (days - 1) * MPD + 0, 'every minute from day 1 on is counted once');
  }
});

test('perp TA slow: nothing at or after the last whole day (or nMax) is read', () => {
  const days = 70, n = days * MPD + 700, rnd = lcg(3), base = path([[days + 1, 0.004]]);
  const noise = Float64Array.from({ length: n }, () => 1 + 0.003 * (rnd() - 0.5)), px = (i: number) => base(i) * noise[i];
  const sane = grid(n, px, { fundEvery: 480, rate: 1e-4 }), bad = grid(n, px, { fundEvery: 480, rate: 1e-4 });
  const cut = days * MPD, sp = spotOf(n, px), spBad = spotOf(n, px);
  for (const k of COLS) for (let i = cut; i < n; i++) bad.c[k][i] = k === 'valid' ? (i % 2) : k === 'fund' ? 0.01 : bad.c[k][i] * 3;
  for (let i = cut; i < n; i++) spBad.close[i] *= 3;
  const a = simulate(sane, sp, cut + 500, BTC), b = simulate(bad, spBad, cut + 500, BTC);
  assert.equal(a.nDays, days);
  assert.deepEqual(Array.from(a.mtm), Array.from(b.mtm));
  assert.deepEqual(Array.from(a.notional), Array.from(b.notional));
  assert.deepEqual(a.trades, b.trades);
  // nMax inside a day: that day is not booked, and nothing from nMax on is read either.
  const c = simulate(sane, sp, 40 * MPD + 10, BTC), d = simulate(bad, spBad, 40 * MPD + 10, BTC);
  assert.equal(c.nDays, 40); assert.deepEqual(Array.from(c.mtm), Array.from(d.mtm));
});

test('perp TA slow: gates mode never reads the sealed block (evaluate capped at the seal)', () => {
  const t0 = Date.UTC(2025, 3, 1), days = 120, n = days * MPD, rnd = lcg(11);
  const base = path([[60, 0.006], [60, -0.004]]), noise = Float64Array.from({ length: n }, () => 1 + 0.002 * (rnd() - 0.5));
  const px = (i: number) => base(i) * noise[i];
  const seal = (SLOW.seal - t0) / 60_000;
  const mk = (poison: boolean): CoinData => {
    const g = grid(n, px, { t0, fundEvery: 480, rate: 1e-4 }), spot = spotOf(n, px);
    if (poison) { for (const k of COLS) for (let i = seal; i < n; i++) g.c[k][i] = k === 'valid' ? 0 : g.c[k][i] * 2; for (let i = seal; i < n; i++) spot.close[i] *= 2; }
    return { g, spot, ter: new Int8Array(n) };
  };
  const blocks = [{ name: 'validation' as const, from: SLOW.validFrom, to: SLOW.seal }];
  const a = evaluate([mk(false)], SLOW.seal, blocks, 'abcdef0123456789', { resamples: 20, shifts: 5 });
  const b = evaluate([mk(true)], SLOW.seal, blocks, 'abcdef0123456789', { resamples: 20, shifts: 5 });
  assert.equal(JSON.stringify(a), JSON.stringify(b));
  assert.equal(a.blocks.validation.rule.days, 90, "Apr 2 .. Jun 30: day 0 has no boundary before it");
  assert.equal(a.blocks.validation.diagnostics.macro.notRun, 'the macro_trend states were not computed');
  assert.ok(a.blocks.validation.gate);
  assert.match(ruleHash(), /^[0-9a-f]{16}$/);
});

test('perp TA slow: the daily-priced book charges the cost at each position change, on both legs', () => {
  const nd = 10, z = () => new Float64Array(nd);
  const r = { t0: T0, notional: Float64Array.from([0, 0, 100, 100, 100, 0, 0, -100, -100, 0]), posId: Int32Array.from([0, 0, 1, 1, 1, 0, 0, 2, 2, 0]), ret: z().fill(0.01), fundRate: z() } as unknown as CoinRun;
  // Price: (3 x 100 - 2 x 100) x 1% = 1; costs 0.001 x (100 + 101 + 100 + 101).
  assert.ok(Math.abs(dailyPriced([r], [0], [nd], [0.001], 0) - (1 - 0.402)) < 1e-12);
  // Shifted by 5 with wrap: the long sits on days 7-9 and the short on days 2-3.
  const s5 = dailyPriced([r], [0], [nd], [0], 5);
  assert.ok(Math.abs(s5 - (-2 * 1 + 3 * 1)) < 1e-12);
});

test('perp TA slow: shifts are common calendar shifts; a coin is flat on days it has no data for', () => {
  const z = (n: number) => new Float64Array(n);
  const A = { t0: T0, notional: z(10), posId: new Int32Array(10), ret: z(10), fundRate: z(10) } as unknown as CoinRun;
  const B = { t0: T0 + 3 * DAY, notional: z(7).fill(100), posId: new Int32Array(7).fill(1), ret: z(7).fill(0.01), fundRate: z(7) } as unknown as CoinRun;
  // Calendar days 0..9; B covers 3..9. Shifted by 2, B's days 3 and 4 source calendar days 1 and 2 (no data: flat).
  assert.ok(Math.abs(dailyPriced([A, B], [0, 0], [10, 7], [0, 0], 0) - 7) < 1e-12);
  assert.ok(Math.abs(dailyPriced([A, B], [0, 0], [10, 7], [0, 0], 2) - 5) < 1e-12);
});

test('perp TA slow: the coins\' P&L correlation pairs the same calendar days', () => {
  const rnd = lcg(21), days = 400, lag = 50, n = days * MPD;
  const base = path([[100, 0.006], [100, -0.006], [100, 0.006], [101, -0.004]]);
  const noise = Float64Array.from({ length: n + lag * MPD }, () => 1 + 0.002 * (rnd() - 0.5));
  const pa = (i: number) => base(i) * noise[i], pb = (i: number) => pa(i + lag * MPD);
  const ra = simulate(grid(n, pa), spotOf(n, pa), n, BTC);
  const nb = n - lag * MPD, rb = simulate(grid(nb, pb, { t0: T0 + lag * DAY, asset: 'ETH' }), spotOf(nb, pb), nb, BTC);
  const br = blockResult([ra, rb], { name: 'discovery', from: T0, to: T0 + days * DAY }, 1, { resamples: 10 });
  assert.ok(br.meanPairCorr > 0.8, `rho ${br.meanPairCorr}`);
});

test('perp TA slow: the gates need net and the daily-priced rule above the placebo mean; the sealed statuses', () => {
  const br = { block: 'validation', usd: 10, placebo: { rule: 30, mean: 20, percentile: 0.9, shifts: 1000 } } as unknown as BlockResult;
  assert.equal(gateOf(br).pass, false);
  assert.ok(gateOf({ ...br, usd: 25 } as BlockResult).pass);
  const sb = { usd: 100, priceUsd: 120, entries: 40, lb90: 0.01, bestMonthShare: 0.2, byCoin: { BTC: 1, ETH: 1, SOL: 1, XRP: -1 }, placebo: { rule: 100, mean: 10 } } as unknown as BlockResult;
  const st = { stress3: 1, fundStress: 1, offset0: 1, offset2: 1 };
  const ok = { why: [], beats_placebo: true } as unknown as Ho1;
  assert.equal(sealedVerdict(sb, ok, st).status, 'PASS (provisional)');
  const folds = { why: ['HO-1: 15 of 30 folds won (needs 20)'], beats_placebo: true } as unknown as Ho1;
  assert.equal(sealedVerdict(sb, folds, st).status, 'FAIL: edge not refuted, HO-1 not met');
  assert.equal(sealedVerdict(sb, { ...folds, beats_placebo: false } as Ho1, st).status, 'FAIL');
  const few = sealedVerdict({ ...sb, entries: 12 } as BlockResult, ok, st);
  assert.equal(few.status, 'INCONCLUSIVE'); assert.equal(few.pass, false);
});

test('perp TA slow: the placebo prices the rule as the minute simulation does, and a trend follower beats its shifts', () => {
  const days = 400, n = days * MPD, rnd = lcg(5);
  const base = path([[80, 0.006], [80, -0.006], [80, 0.006], [80, -0.006], [80, 0.006]]);
  const noise = Float64Array.from({ length: n }, () => 1 + 0.002 * (rnd() - 0.5)), px = (i: number) => base(i) * noise[i];
  const g = grid(n, px, { fundEvery: 480, rate: 1e-4 });
  const runs = [simulate(g, spotOf(n, px), n, { half: 0.19, fundOff: 1.66 })];
  const blk = { name: 'discovery' as const, from: T0, to: T0 + days * DAY };
  const br = blockResult(runs, blk, 1, { resamples: 100 });
  const gross = sum(runs[0].traded);
  assert.ok(Math.abs(br.placebo.rule - br.usd) < 0.01 * gross, `daily priced ${br.placebo.rule} vs minute sim ${br.usd} (traded ${gross})`);
  assert.ok(br.usd > 0 && br.placebo.rule > br.placebo.mean, `rule ${br.placebo.rule} vs placebo ${br.placebo.mean}`);
  assert.ok(br.placebo.percentile > 0.9);
  assert.equal(br.placebo.shifts, SLOW.shifts);
  // Too short a block for 90-day shifts each way: no placebo.
  assert.ok(Number.isNaN(placebo(runs, { name: 'discovery', from: T0, to: T0 + 150 * DAY }, 1).mean));
  // Reporting identities.
  assert.ok(Math.abs(br.usd - (br.priceUsd + br.feeUsd + br.fundUsd)) < 0.05);
  assert.ok(br.entries >= 4 && br.fills.maker + br.fills.taker === sum(runs[0].makerFills) + sum(runs[0].takerFills));
});

test('perp TA HO-1: an external placebo replaces the random-entry one', () => {
  const byDay = Object.fromEntries(Array.from({ length: 96 }, (_, k) => [new Date(Date.UTC(2025, 6, 1) + k * DAY).toISOString().slice(0, 10), 1]));
  const taken = [{ x: 400e4, ter: 0 }, { x: 300e4, ter: 1 }, { x: 200e4, ter: 2 }];
  const hours = [700, 700, 700];
  const lose = ho1Of(byDay, taken, hours, 1, { placebo: { usd: 5, placeboUsd: 10 } });
  assert.equal(lose.beats_placebo, false); assert.equal(lose.placebo_usd, 10);
  assert.ok(lose.why.some((w) => /circular shifts/.test(w)));
  const win = ho1Of(byDay, taken, hours, 1, { placebo: { usd: 10, placeboUsd: 5 } });
  assert.equal(win.beats_placebo, true); assert.deepEqual(win.why, []);
  assert.ok(ho1Of(byDay, taken, hours, 1).why.some((w) => /no placebo/.test(w)));
});
