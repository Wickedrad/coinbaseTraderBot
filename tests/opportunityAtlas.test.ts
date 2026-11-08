import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { bollinger, macd, rsi } from '../bot/ta/indicators';
import { buildAtlas, CompletedDailyIndex } from '../research/opportunity/train';
import { ConditionalOpportunityAtlas, HORIZONS_MIN, FifteenMinuteIndicators, OpportunityLabeler,
  predictStoredAtlas, type AtlasFeatures, type MinuteCandle, type OpportunityEntry } from '../research/opportunity/atlas';

const MIN = 60_000;
const f = (knownAt: number): AtlasFeatures => ({ knownAt, rsi: 20, bbPctB: 0.05, macdBps: -2, atrBps: 100,
  session: 'new_york', etHour: 15.25, btcdDailyChange: -0.01, usdtdDailyChange: -0.01 });
const candle = (i: number, c: number, hi = c, lo = c): MinuteCandle => ({ ts: i * MIN,
  o: c, h: Math.max(hi, c), l: Math.min(lo, c), c, v: 100 });

test('future extrema exclude the entry candle and include the exact H following candles', () => {
  const L = new OpportunityLabeler();
  let got = [] as ReturnType<OpportunityLabeler['push']>;
  for (let i = 0; i <= 15; i++) {
    const price = i === 0 ? 100 : i === 2 ? 105 : i === 4 ? 93 : 100 + i / 100;
    const b = candle(i, price, i === 0 ? 130 : price + 0.1, i === 0 ? 80 : price - 0.1);
    const entry: OpportunityEntry | undefined = i === 0 ? { ts: MIN, asset: 'BTC', price: 100, f: f(MIN) } : undefined;
    got.push(...L.push(b, entry));
  }
  const h5 = got.find((x) => x.horizonMin === 5)!;
  const h15 = got.find((x) => x.horizonMin === 15)!;
  assert.ok(h5 && h15);
  assert.equal(h5.entry.price, 100);
  assert.ok(Math.abs(h5.maxUpBps - 10_000 * Math.log(105.1 / 100)) < 1e-8);
  assert.ok(Math.abs(h5.maxDownBps - 10_000 * Math.log(100 / 92.9)) < 1e-8);
  assert.equal(h5.resolvedAt, 6 * MIN);
  assert.equal(h15.resolvedAt, 16 * MIN);
});

test('gap invalidates pending labels; nonmonotonic time fails closed', () => {
  const L = new OpportunityLabeler();
  L.push(candle(0, 100), { asset: 'BTC', ts: MIN, price: 100, f: f(MIN) });
  for (let i = 1; i < 5; i++) assert.equal(L.push(candle(i, 101)).length, 0);
  assert.equal(L.push(candle(6, 102)).length, 0);
  assert.equal(L.gaps, 1);
  assert.throws(() => L.push(candle(6, 100)), /non-increasing/);
});

test('entry and indicator timestamps must not peek beyond completed data', () => {
  const L = new OpportunityLabeler();
  assert.throws(() => L.push(candle(0, 100), { asset: 'BTC', ts: MIN, price: 100, f: f(2 * MIN) }), /lookahead/);
});

test('incremental 15m RSI, MACD and Bollinger agree with existing built-in indicator formulas', () => {
  const T = new FifteenMinuteIndicators();
  const closes: number[] = [];
  let last: ReturnType<FifteenMinuteIndicators['push']>;
  for (let i = 0; i < 65; i++) {
    const c = 100 * Math.exp(0.001 * i + 0.03 * Math.sin(i * 0.3));
    closes.push(c);
    for (let m = 0; m < 15; m++) {
      last = T.push({ ts: (i * 15 + m) * MIN, o: c, h: c, l: c, c, v: 1 });
    }
    const rs = rsi(closes), hist = macd(closes).hist, bb = bollinger(closes).pctB;
    if (i >= 35) {
      assert.ok(last);
      assert.ok(Math.abs(last!.rsi - rs[i]) < 1e-8, `RSI ${i}`);
      assert.ok(Math.abs(last!.macdBps - hist[i] * 10_000 / c) < 1e-8, `MACD ${i}`);
      assert.ok(Math.abs(last!.bbPctB - bb[i]) < 1e-8, `Bollinger ${i}`);
    }
  }
});

test('daily dominance is not made available at its opening timestamp', () => {
  const D = 1440 * MIN;
  const s = new CompletedDailyIndex([candle(0, 50), candle(1440, 52), candle(2880, 51)]);
  assert.ok(Number.isNaN(s.changeAt(D - 1)));
  assert.ok(Number.isNaN(s.changeAt(D)));
  assert.ok(s.changeAt(2 * D - 1) !== s.changeAt(2 * D));
  assert.ok(s.changeAt(2 * D) > 0);
  assert.ok(s.changeAt(3 * D) < 0);
});

test('train/dev/final splits purge overlapping labels and preserve final from selection', () => {
  const D = 24 * 60 * MIN;
  const M = new ConditionalOpportunityAtlas('BTC', { trainBefore: 10 * D, finalFrom: 20 * D, minDevRows: 1, minDevWeeks: 1 });
  const mk = (t: number, resolved: number) => ({ entry: { asset: 'BTC', ts: t, price: 100, f: f(t) }, horizonMin: 15 as const,
    resolvedAt: resolved, up: true, returnBps: 50, maxUpBps: 100, maxDownBps: 10, upOneAtr: true, downOneAtr: false });
  M.accept(mk(9 * D, 9 * D + MIN));
  M.accept(mk(10 * D - MIN, 10 * D + MIN)); // leaked across train split: must be dropped
  M.accept(mk(12 * D, 12 * D + MIN));
  M.accept(mk(20 * D - MIN, 20 * D + MIN)); // crosses final boundary: drop
  M.accept(mk(21 * D, 21 * D + MIN));
  const row = M.report().horizons.find((x) => x.horizonMin === 15)!;
  assert.equal(row.train, 1);
  assert.equal((row.dev.baseline as { n: number }).n, 1);
  assert.equal((row.final.baseline as { n: number }).n, 1);
});

test('RSI and time-of-day spectra interpolate continuously across storage-bin boundaries', () => {
  const D = 24 * 60 * MIN;
  const M = new ConditionalOpportunityAtlas('BTC', { trainBefore: 1000 * D, finalFrom: 1200 * D });
  const mk = (i: number, r: number, hour: number, up: boolean) => ({
    entry: { asset: 'BTC', ts: i * D, price: 100,
      f: { ...f(i * D), rsi: r, etHour: hour } },
    horizonMin: 15 as const, resolvedAt: i * D + 16 * MIN, up,
    returnBps: up ? 30 : -30, maxUpBps: up ? 100 : 20,
    maxDownBps: up ? 20 : 100, upOneAtr: up, downOneAtr: !up,
  });
  for (let i = 1; i < 850; i++) M.accept(mk(i, i % 2 ? 18.5 : 22.5, i % 2 ? 23.8 : 0.2, i % 2 === 0));
  const x = f(50 * D);
  const p1 = M.predict(15, { ...x, rsi: 19.99, etHour: 23.99 }, 'time').pUp;
  const p2 = M.predict(15, { ...x, rsi: 20.01, etHour: 0.01 }, 'time').pUp;
  assert.ok(Math.abs(p1 - p2) < 0.02, `discontinuity at RSI/time boundary: ${p1} vs ${p2}`);
});

test('retention uses development-only evidence; final labels cannot select an interaction', () => {
  const D = 24 * 60 * MIN;
  const M = new ConditionalOpportunityAtlas('BTC', { trainBefore: 2000 * D, finalFrom: 2200 * D, minDevRows: 30, minDevWeeks: 10 });
  const mk = (i: number, up: boolean, macdBps: number) => ({
    entry: { asset: 'BTC', ts: i * D, price: 100, f: { ...f(i * D), macdBps } },
    horizonMin: 30 as const, resolvedAt: i * D + 31 * MIN, up,
    returnBps: up ? 20 : -20, maxUpBps: 50, maxDownBps: 50,
    upOneAtr: up, downOneAtr: !up,
  });
  for (let i = 1; i < 1500; i++) M.accept(mk(i, i % 2 === 0, i % 2 ? -50 : 50));
  // Development has a perfectly predictive MACD interaction.
  for (let i = 2001; i < 2180; i++) M.accept(mk(i, i % 2 === 0, i % 2 ? -50 : 50));
  // Final reverses the relationship: evidence must NOT be used to choose a group.
  for (let i = 2201; i < 2350; i++) M.accept(mk(i, i % 2 !== 0, i % 2 ? -50 : 50));
  const row = M.report().horizons.find((x) => x.horizonMin === 30)!;
  assert.equal(row.train, 1499);
  assert.ok(row.chosenGroup === 'macd' || row.chosenGroup === 'macd_bands' || row.chosenGroup === 'macd_session', String(row.chosenGroup));
  const final = row.final as { chosen: { improvement: number } };
  assert.ok(final.chosen.improvement < 0, 'final cannot be cherry-picked to fix a failing selected relationship');
  const query = f(2400 * D);
  assert.deepEqual(predictStoredAtlas(JSON.parse(JSON.stringify(M.report())), 30, query),
    M.predict(30, query, row.chosenGroup!));
});


test('trained relationship curves persist in the report and reconstruct identically', () => {
  const D = 1440 * MIN;
  const M = new ConditionalOpportunityAtlas('ETH', { trainBefore: 20 * D, finalFrom: 30 * D, minDevRows: 1, minDevWeeks: 1 });
  for (let i = 1; i <= 14; i++) {
    const t = i * D;
    M.accept({ entry: { asset: 'ETH', ts: t, price: 100, f: { ...f(t), rsi: 10 + i } },
      horizonMin: 60, resolvedAt: t + 61 * MIN, up: i % 2 === 0,
      returnBps: i % 2 ? -20 : 30, maxUpBps: 30, maxDownBps: 30, upOneAtr: false, downOneAtr: false });
  }
  const report = M.report();
  const fromJson = JSON.parse(JSON.stringify(report)) as typeof report;
  const row = fromJson.horizons.find((x) => x.horizonMin === 60)!;
  assert.ok(row.fit.rsi.length > 0);
  // Research curves are persisted even if there is insufficient OOS evidence for activation.
  assert.equal(predictStoredAtlas(fromJson, 60, f(50 * D)), null);
  assert.equal(row.retained, false);
  assert.equal(row.fit.overall.n, 14);
});


test('every horizon matches direct future-window calculations on overlapping entries', () => {
  const bars: MinuteCandle[] = [];
  const L = new OpportunityLabeler();
  let state = 12345;
  const random = () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return state / 2 ** 32; };
  const outcomes: ReturnType<OpportunityLabeler['push']> = [];
  for (let i = 0; i < 1500; i++) {
    const c = 100 + 10 * random();
    const b = candle(i, c, c + random(), c - random());
    bars.push(b);
    outcomes.push(...L.push(b, i % 15 === 0 ? { ts: b.ts + MIN, asset: 'BTC', price: c, f: f(b.ts + MIN) } : undefined));
  }
  for (const h of HORIZONS_MIN) assert.ok(outcomes.some((o) => o.horizonMin === h));
  for (const o of outcomes) {
    const i = o.entry.ts / MIN - 1;
    const future = bars.slice(i + 1, i + 1 + o.horizonMin);
    assert.equal(o.returnBps, 10000 * Math.log(future.at(-1)!.c / o.entry.price));
    assert.equal(o.maxUpBps, 10000 * Math.log(Math.max(...future.map((b) => b.h)) / o.entry.price));
    assert.equal(o.maxDownBps, 10000 * Math.log(o.entry.price / Math.min(...future.map((b) => b.l))));
  }
});

test('numeric context interpolation has no jump when the nearest storage cell changes', () => {
  const M = new ConditionalOpportunityAtlas('BTC', { trainBefore: 10000 * MIN, finalFrom: 20000 * MIN });
  for (let i = 1; i < 2000; i++) {
    const up = i % 2 === 0;
    M.accept({ entry: { asset: 'BTC', ts: i * MIN, price: 100, f: { ...f(i * MIN), macdBps: up ? 20 : -10 } },
      horizonMin: 5, resolvedAt: (i + 5) * MIN, up, returnBps: up ? 20 : -20,
      maxUpBps: 30, maxDownBps: 30, upOneAtr: false, downOneAtr: false });
  }
  const left = M.predict(5, { ...f(3000 * MIN), macdBps: 5 - 1e-7 }, 'macd');
  const right = M.predict(5, { ...f(3000 * MIN), macdBps: 5 + 1e-7 }, 'macd');
  assert.ok(Math.abs(left.pUp - right.pUp) < 1e-6, `${left.pUp} vs ${right.pUp}`);
});

test('daily index as-of lookup remains causal when queried backwards and rejects unordered source bars', () => {
  const D = 1440 * MIN;
  const s = new CompletedDailyIndex([candle(0, 50), candle(1440, 52), candle(2880, 51)]);
  assert.ok(s.changeAt(3 * D) < 0);
  assert.ok(Number.isNaN(s.changeAt(D)));
  assert.throws(() => new CompletedDailyIndex([candle(1440, 52), candle(0, 50)]), /increasing/);
});

test('stored consumer refuses missing selected context and invalid RSI', () => {
  const M = new ConditionalOpportunityAtlas('BTC', { trainBefore: 10000 * MIN, finalFrom: 20000 * MIN });
  const report = M.report();
  // A stored selected model may be queried when a required input is unavailable.
  const row = report.horizons.find((r) => r.horizonMin === 5)!;
  row.retained = true; row.chosenGroup = 'dominance';
  assert.equal(predictStoredAtlas(report, 5, { ...f(1), btcdDailyChange: NaN }), null);
  assert.equal(predictStoredAtlas(report, 5, { ...f(1), rsi: NaN }), null);
});


test('history-store integration respects the cap and rejects malformed minute rows without filling gaps', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-store-'));
  try {
    const dir = path.join(root, 'binance-1m', 'BTC');
    fs.mkdirSync(dir, { recursive: true });
    const rows = ['ts,o,h,l,c,v'];
    for (let i = 0; i < 2400; i++) {
      const c = 100 + Math.sin(i / 50);
      rows.push(i === 600 ? `${i * MIN},100,101,99,100,` :
        `${i * MIN + (i === 601 ? 1 : 0)},${c},${c + 1},${c - 1},${c},1`);
    }
    fs.writeFileSync(path.join(dir, '1m.csv'), rows.join('\n') + '\n');
    const [r] = await buildAtlas({ historyDir: root, assets: ['BTC'], trainBefore: 1200 * MIN,
      finalFrom: 1800 * MIN, maxMinutes: 2000 });
    assert.equal(r.data!.oneMinuteBars, 2000);
    assert.equal(r.data!.malformedRows, 2);
    assert.equal(r.gaps, 1);
    assert.equal(r.data!.lastMinute, new Date(2001 * MIN).toISOString());
    const h = r.horizons.find((row) => row.horizonMin === 5)!;
    assert.ok(h.train > 0);
    assert.ok((h.dev.baseline as { n: number }).n > 0);
    assert.ok((h.final.baseline as { n: number }).n > 0);
    assert.equal(h.fit.groups.find(([g]) => g === 'dominance')![1].length, 0);
    await assert.rejects(buildAtlas({ historyDir: root, assets: ['ETH'], trainBefore: 1200 * MIN,
      finalFrom: 1800 * MIN }), /Missing/);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});
