import './tmpScope'; // one temp folder per run, removed at exit
import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { tfState } from '../bot/ta/analyzer';
import { tfFeatures } from '../bot/ta/taNet';
import { marketClockFeatures, sessionAt } from '../bot/model/sessions';
import type { Candle } from '../bot/ta/indicators';
import { AsOfDailyFeatures, CausalAtlasFeatures } from '../research/opportunity/features';
import { buildFeatureReport } from '../research/opportunity/featuresCli';
import { parseMinuteCsv } from '../research/opportunity/minuteCsv';

const MIN = 60000, DAY = 86400000, start = Date.UTC(2026, 3, 1);
const source = { source: 'test/BTC/1m.csv', sha256: 'a'.repeat(64) };
function bar(ts: number, i = 0): Candle {
  const o = 100 + Math.sin(i / 13) * 3 + i / 1000, c = o + Math.cos(i / 7) * 0.1;
  return { ts, o, h: Math.max(o, c) + 0.3, l: Math.min(o, c) - 0.2, c, v: 10 + i % 7, tb: 4 };
}

test('multi-timeframe snapshots withhold forming/partial candles and match the existing TA vocabulary', () => {
  const p = new CausalAtlasFeatures('BTC', source), minutes: Candle[] = [];
  for (let i = 0; i < 31 * 5; i++) { const c = bar(start + i * MIN, i); p.push(c); minutes.push(c); }
  const before = p.snapshot();
  assert.equal(before.groups.spot_5m.bars, 31);
  assert.equal(before.groups.spot_5m.knownAt, start + 155 * MIN);
  const aggregate: Candle[] = [];
  for (let i = 0; i < minutes.length; i += 5) {
    const cs = minutes.slice(i, i + 5);
    aggregate.push({ ts: cs[0].ts, o: cs[0].o, c: cs.at(-1)!.c, h: Math.max(...cs.map((c) => c.h)),
      l: Math.min(...cs.map((c) => c.l)), v: cs.reduce((s, c) => s + c.v, 0) });
  }
  const expected: Record<string, number> = {};
  tfFeatures('x', tfState('5m', aggregate), expected, { sma200: true, vwap: true });
  for (const [key, value] of Object.entries(expected)) assert.equal(before.groups.spot_5m.values[key.slice(2)], Number.isFinite(value) ? value : null, key);
  p.push(bar(start + 155 * MIN, 100000)); // a large move in the newly forming 5m candle
  const after = p.snapshot();
  assert.deepEqual(after.groups.spot_5m, before.groups.spot_5m);
  assert.ok(after.groups.spot_1m.knownAt! <= after.decisionAt);
  assert.equal(before.groups.spot_5m.bars, 31, 'published earlier snapshots are immutable');
  assert.throws(() => { (before.groups.spot_5m.values as Record<string, number>).rsi = 0; }, TypeError);
  const partial = new CausalAtlasFeatures('BTC', source);
  for (let i = 1; i < 5; i++) partial.push(bar(start + i * MIN, i));
  assert.equal(partial.snapshot().groups.spot_5m.bars, 0, 'starting mid-bucket cannot manufacture a full candle');
});

test('gaps clear affected minute-derived context and prevent returns across missing prices', () => {
  const p = new CausalAtlasFeatures('ETH', source);
  for (let i = 0; i < 300; i++) p.push(bar(start + i * MIN, i));
  assert.equal(p.snapshot().groups.spot_5m.status, 'ready');
  p.push(bar(start + 301 * MIN, 301));
  const frame = p.snapshot();
  assert.equal(frame.gapsSeen, 1); assert.equal(frame.groups.spot_5m.status, 'missing');
  assert.equal(frame.groups.micro.values.log_return_1m, null);
  assert.equal(frame.groups.spot_1m.status, 'warming');
  assert.throws(() => p.push(bar(start + 301 * MIN)), /strictly increasing/);
  assert.throws(() => p.push({ ...bar(start + 302 * MIN), c: NaN }), /valid/);
});

test('daily spot TA becomes available at its thirtieth completed day and ignores the next forming day', () => {
  const p = new CausalAtlasFeatures('BTC', source);
  for (let i = 0; i < 30 * 1440 - 1; i++) p.push(bar(start + i * MIN, i));
  assert.equal(p.snapshot().groups.spot_1d.status, 'warming');
  p.push(bar(start + (30 * 1440 - 1) * MIN, 30 * 1440 - 1));
  const completed = p.snapshot();
  assert.equal(completed.groups.spot_1d.bars, 30);
  assert.equal(completed.groups.spot_1d.knownAt, start + 30 * DAY);
  assert.equal(completed.groups.spot_1d.status, 'ready');
  assert.equal(completed.groups.spot_1m.bars, 1440, 'a full UTC day is retained for minute VWAP');
  p.push({ ts: start + 30 * DAY, o: 100, h: 10000, l: 1, c: 9000, v: 1 });
  assert.deepEqual(p.snapshot().groups.spot_1d, completed.groups.spot_1d);
  for (const group of Object.values(p.snapshot().groups)) assert.ok(group.knownAt === null || group.knownAt <= p.snapshot().decisionAt);
});

test('daily joins honor close plus publication lag, work backwards, expose staleness and exclude future suffixes', () => {
  const bars = Array.from({ length: 80 }, (_, i) => bar(start + i * DAY, i));
  const a = new AsOfDailyFeatures(bars, source, DAY, 2 * DAY);
  const decision = start + 41 * DAY;
  const group = a.at(decision);
  assert.equal(group.lastOpen, start + 39 * DAY); assert.equal(group.knownAt, decision);
  const poisoned = bars.map((c, i) => i < 40 ? c : { ...c, o: 5000, h: 6000, l: 4000, c: 5500 });
  const b = new AsOfDailyFeatures(poisoned, source, DAY, 2 * DAY);
  assert.deepEqual(group, b.at(decision));
  a.at(start + 75 * DAY);
  assert.deepEqual(a.at(decision), group, 'cache must not leak later states into backwards queries');
  assert.equal(a.at(start + DAY).status, 'missing');
  const stale = a.at(start + 84 * DAY);
  assert.equal(stale.status, 'stale'); assert.ok(Object.values(stale.values).every((v) => v === null));
  const withGap = bars.filter((_, i) => i !== 37);
  assert.equal(new AsOfDailyFeatures(withGap, source).at(decision).bars, 2, 'no smoothing across a daily gap');
  assert.throws(() => new AsOfDailyFeatures([bars[1], bars[0]], source), /invalid daily/);
});

test('daily dominance drops all placeholder-volume derivatives and distinguishes missing taker flow', () => {
  const bars = Array.from({ length: 60 }, (_, i) => bar(start + i * DAY, i));
  const dominance = new AsOfDailyFeatures(bars, source, 0, DAY, false).at(start + 60 * DAY);
  for (const key of ['obv_slope', 'cmf', 'mfi', 'div', 'hdiv', 'tl_adosc', 'vp_pos', 'vol_ratio', 'breakout']) assert.equal(dominance.values[key], null, key);
  assert.ok(Number.isFinite(dominance.values.rsi));
  const p = new CausalAtlasFeatures('BTC', source);
  p.push({ ...bar(start), tb: undefined });
  assert.equal(p.snapshot().groups.micro.values.taker_imbalance, null);
  p.push({ ...bar(start + MIN), tb: 0 });
  assert.equal(p.snapshot().groups.micro.values.taker_imbalance, -1);
  assert.equal(p.snapshot().groups.micro.firstOpen, start);
  assert.equal(p.snapshot().groups.micro.bars, 2);
});

test('feature clock uses the existing DST-aware session contract at decision time', () => {
  for (const time of ['2026-03-06T14:30:00Z', '2026-03-09T13:30:00Z']) {
    const ts = Date.parse(time), p = new CausalAtlasFeatures('BTC', source);
    p.push(bar(ts - MIN)); const frame = p.snapshot();
    assert.equal(frame.decisionAt, ts); assert.equal(frame.session, sessionAt(ts));
    assert.deepEqual(frame.groups.clock.values, marketClockFeatures(ts));
  }
});

test('canonical minute parser keeps unknown flow distinct and rejects malformed prices/timestamps', () => {
  assert.equal(parseMinuteCsv('0,100,101,99,100,1')?.tb, undefined);
  assert.equal(parseMinuteCsv('0,100,101,99,100,1,0')?.tb, 0);
  for (const row of ['1,100,101,99,100,1', '0,100,99,101,100,1', '0,100,101,99,100,1,NaN', '0,,101,99,100,1', '0,100,101,99,100,1,2']) assert.equal(parseMinuteCsv(row), undefined);
});

test('feature replay verifies input bytes, leaves absent context unknown, and never fits on final-period data', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-features-'));
  try {
    const name = 'binance-1m/BTC/1m.csv', file = path.join(root, 'history', name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    const input = 'ts,o,h,l,c,v\n' + Array.from({ length: 45 }, (_, i) => `${start + i * MIN},100,101,99,100,1\n`).join('');
    fs.writeFileSync(file, input);
    fs.writeFileSync(path.join(root, 'archive-validation.json'), JSON.stringify({ schema: 'atlas-archive-audit-v1', files: [
      { path: name, ready: true, source: 'binance-1m', rows: 45, sha256: createHash('sha256').update(input).digest('hex') },
    ] }));
    let frames = 0;
    const report = await buildFeatureReport({ archiveDir: root, assets: ['BTC'], onFrame(frame) {
      frames++; assert.equal(frame.groups.yahoo_daily.status, 'missing'); assert.equal(frame.groups.dominance_btcd.knownAt, null);
    } });
    assert.equal(frames, 3); assert.equal(report.assets[0].minutes, 45);
    assert.equal(report.autoPromote, false); assert.match(report.purpose, /no outcome scoring, model fitting/);
    assert.equal(fs.readFileSync(file, 'utf8'), input);
    fs.appendFileSync(file, `${start + 45 * MIN},100,101,99,100,1\n`);
    await assert.rejects(buildFeatureReport({ archiveDir: root, assets: ['BTC'] }), /hash mismatch/);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});
