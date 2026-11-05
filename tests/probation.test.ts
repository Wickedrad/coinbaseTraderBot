import assert from 'node:assert/strict';
import fs from 'fs';
import path from 'path';
import { test } from 'node:test';
import { Alerter } from '../bot/alerts/alerter';
import { AutoTrainer } from '../bot/autotrain';
import { loadConfig } from '../bot/config';
import { applyTakeGate } from '../bot/model/takeModel';
import { gatePasses, Probation, setProbation, DEFAULT_PROBATION, PROBATION_ALERT_MS, type ProbationEvent } from '../bot/risk/probation';
import { minScoreFor } from '../bot/setups/lanes';
import { tmpAudit, tmpDir } from './helpers';

test('defaults: unvalidated models trade on probation, and contracts exit on the ratchet', () => {
  const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32) });
  assert.equal(cfg.probation.mode, 'monitor');
  assert.equal(cfg.probation.bench, false, 'score-only by default, paper and live alike');
  assert.equal(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), PROBATION_BENCH: 'true' }).probation.bench, true);
  assert.equal(cfg.strategy.exitPolicy, 'confluence_ratchet');
  assert.equal(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), VALIDATION_GATES: 'enforce', EXIT_POLICY: 'hold' }).probation.mode, 'enforce');
});

test('PROBATION_BENCH=true: a book is benched when it loses beyond luck, or past the loss limit, and starts fresh on reset', () => {
  const benched: string[] = [];
  const file = path.join(tmpDir(), 'probation.json');
  const p = new Probation({ ...DEFAULT_PROBATION, minTrades: 10, maxLossUsd: 50, bench: true }, file, (e) => benched.push(e.book));
  assert.ok(p.open('kalshi') && p.passes('kalshi', false));
  // Noisy but positive: stays on.
  for (let i = 0; i < 30; i++) p.record('kalshi', i % 2 ? 1.2 : -1);
  assert.ok(p.open('kalshi'));
  // Steady losses: t well below -1 after the minimum count.
  for (let i = 0; i < 12; i++) p.record('setups', i % 3 ? -0.8 : 0.3);
  assert.equal(p.open('setups'), false);
  assert.equal(p.passes('setups', true), true, 'a validated part keeps trading');
  assert.deepEqual(benched, ['setups']);
  // One big loss: the loss limit, before the minimum count.
  p.record('perps', -60);
  assert.equal(p.open('perps'), false);
  assert.match(p.status().perps.benched!.reason, /PROBATION_MAX_LOSS_USD/);
  // Persisted across a restart.
  const again = new Probation({ ...DEFAULT_PROBATION, minTrades: 10, maxLossUsd: 50, bench: true }, file);
  assert.equal(again.open('setups'), false);
  again.reset('setups');
  assert.ok(again.open('setups'));
  assert.equal(again.status().setups.trades, 0);
  // Enforce: nothing unvalidated passes, nothing is recorded.
  const off = new Probation({ ...DEFAULT_PROBATION, mode: 'enforce' });
  assert.equal(off.passes('kalshi', false), false);
  off.record('kalshi', -100);
  assert.equal(off.status().kalshi.trades, 0);
  assert.ok(fs.existsSync(file));
});

test('the gates open for unvalidated models only while their book is on probation', () => {
  const take = { validation: { validated: false } } as never;
  const plan = () => ({ place: [{ side: 'bid', price: 0.5, count: 1, postOnly: false, reduceOnly: false, purpose: 'enter', edge: 0, why: '' }] as never[], notes: [] as string[] });
  const ctx = { pYes: 0.5, features: {}, tauSec: 300, bid: 0.49, ask: 0.51, margin: 0 };
  try {
    setProbation(undefined);
    assert.equal(gatePasses('kalshi', false), false, 'no probation (tests, research): the gates as before');
    const p = new Probation({ ...DEFAULT_PROBATION, bench: true });
    setProbation(p);
    assert.equal(gatePasses('kalshi', false), true);
    // The unvalidated take head now judges entries (a malformed head throws: it was consulted).
    assert.throws(() => applyTakeGate(plan(), take, ctx));
    for (let i = 0; i < 25; i++) p.record('kalshi', -1);
    assert.equal(gatePasses('kalshi', false), false);
    assert.equal(applyTakeGate(plan(), take, ctx), 0, 'benched: back behind its gate');
  } finally { setProbation(undefined); }
  // Setup types the model has not proven: traded at the lane's minimum score only while set.
  const L = { maxPositions: 1, riskFrac: 0.01, ttlBars: 1, minScore: 0.8, refScore: 0.5, maxChaseR: 0.3, minScoreByKind: { '1h burst': 0.7 } };
  assert.equal(minScoreFor(L, { tf: '15m', kind: 'burst' }), undefined);
  assert.equal(minScoreFor({ ...L, unlistedMinScore: 0 }, { tf: '15m', kind: 'burst' }), 0);
  assert.equal(minScoreFor({ ...L, unlistedMinScore: 0 }, { tf: '1h', kind: 'burst' }), 0.7);
});

test('the loss limit follows the account: the smaller of $25 and 15% of the book\'s break-even, applied at start too', () => {
  assert.deepEqual([DEFAULT_PROBATION.maxLossUsd, DEFAULT_PROBATION.maxLossPct], [25, 0.15]);
  assert.equal(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32) }).probation.maxLossPct, 0.15);
  const file = path.join(tmpDir(), 'probation.json');
  const p = new Probation(DEFAULT_PROBATION, file);
  // A $41.20 live account: 13 settled markets losing $14.51 (the live book on Oct 22), under the old $25 limit.
  for (let i = 0; i < 13; i++) p.record('kalshi', i === 0 ? -2.51 : -1);
  assert.ok(p.open('kalshi'), 'no break-even known yet: $25');
  assert.equal(p.status().kalshi.maxLossUsd, 25);
  // At the next start the break-even is known: 15% of $41.20 is $6.18, and the book is past it.
  const benched: string[] = [];
  const again = new Probation(DEFAULT_PROBATION, file, (e) => benched.push(e.book));
  again.setBreakEven((book) => (book === 'perps' || book === 'setups' ? 100 : 41.2));
  assert.equal(again.status().kalshi.maxLossUsd, 6.18);
  assert.equal(again.status().perps.maxLossUsd, 15, '15% of a $100 perps account');
  assert.ok(again.open('kalshi'), 'not judged before the review');
  again.review();
  assert.deepEqual(benched, ['kalshi']);
  assert.ok(again.open('kalshi'), 'score-only by default: it would bench, nothing turned off');
  assert.equal(again.status().kalshi.wouldBench, true);
  assert.match(again.status().kalshi.benched!.reason, /^net loss \$14\.51 over 13 results reached PROBATION_MAX_LOSS_PCT \(15% of the \$41\.20 break-even: \$6\.18\)/);
  assert.ok(again.open('tennis') && again.open('perps'), 'books within their limit stay on');
  // A big account keeps the dollar limit: 15% of $400 is $60, so $25 applies.
  const big = new Probation(DEFAULT_PROBATION);
  big.setBreakEven(() => 400);
  assert.equal(big.status().kalshi.maxLossUsd, 25);
  // PROBATION_MAX_LOSS_PCT=0: the dollar limit alone.
  const usdOnly = new Probation({ ...DEFAULT_PROBATION, maxLossPct: 0 });
  usdOnly.setBreakEven(() => 41.2);
  assert.equal(usdOnly.status().kalshi.maxLossUsd, 25);
});

const at = (h: number) => Date.UTC(2026, 10, 5) + h * 3600_000;

test('defaults: a book past its loss limit stays open, gates still pass, and exactly one "iterate it" alert fires', () => {
  const events: ProbationEvent[] = [];
  const p = new Probation(DEFAULT_PROBATION, path.join(tmpDir(), 'probation.json'), (e) => events.push(e), at(0));
  try {
    setProbation(p);
    for (let i = 0; i < 40; i++) p.record('kalshi', i === 0 ? -30 : i % 2 ? 0.4 : -0.6, at(i / 10));
    assert.ok(p.open('kalshi'));
    assert.equal(gatePasses('kalshi', false), true, 'the unvalidated helpers keep running');
    const s = p.status().kalshi;
    assert.deepEqual([s.wouldBench, s.benchActive, s.open], [true, false, true]);
    assert.match(s.benched!.reason, /PROBATION_MAX_LOSS_USD/);
    assert.deepEqual(events.map((e) => [e.book, e.event, e.active, e.alert]), [['kalshi', 'bench', false, true]]);
    p.review(at(5));
    assert.equal(events.length, 1, 'no change at the review: no alert');
  } finally { setProbation(undefined); }
});

test('a book oscillating at its loss limit gives one alert: the verdict clears only well clear of the limit', () => {
  const events: ProbationEvent[] = [];
  const p = new Probation(DEFAULT_PROBATION, undefined, (e) => events.push(e));
  p.record('perps', -25, at(0));
  for (let i = 0; i < 30; i++) p.record('perps', i % 2 ? -1.5 : 1.5, at(1 + i));
  assert.deepEqual(events.map((e) => e.event), ['bench']);
  assert.equal(events.filter((e) => e.alert).length, 1);
  assert.ok(p.status().perps.wouldBench, 'net -$25 to -$23.50: not back above half the limit');
  // A change within 6 hours of the last alert is audited, not alerted.
  const q = new Probation(DEFAULT_PROBATION, undefined, (e) => events.push(e));
  events.length = 0;
  q.record('tennis', -30, at(0));
  q.record('tennis', 25, at(1));
  q.record('tennis', -30, at(2));
  assert.deepEqual(events.map((e) => [e.event, e.alert]), [['bench', true], ['clear', false], ['bench', false]]);
  q.record('tennis', 40, at(2) + PROBATION_ALERT_MS);
  assert.deepEqual(events.at(-1), { book: 'tennis', event: 'clear', reason: events.at(-1)!.reason, active: false, alert: true });
});

test('PROBATION_BENCH=true: a benched book comes back on once its window recovers, with an unbench alert', () => {
  const events: ProbationEvent[] = [];
  const p = new Probation({ ...DEFAULT_PROBATION, bench: true }, undefined, (e) => events.push(e));
  p.record('setups', -30, at(0));
  assert.equal(p.open('setups'), false);
  assert.deepEqual([p.status().setups.wouldBench, p.status().setups.benchActive], [true, true]);
  p.record('setups', 10, at(7));
  assert.equal(p.open('setups'), false, 'net -$20: still past half the $25 limit');
  p.record('setups', 10, at(8));
  assert.ok(p.open('setups'), 'net -$10 and t above -0.5: recovered');
  assert.deepEqual([p.status().setups.wouldBench, p.status().setups.benchActive], [false, false]);
  assert.deepEqual(events.map((e) => [e.event, e.active, e.alert]), [['bench', true, true], ['clear', true, true]]);
  assert.match(events[1].reason, /^recovered: net \$-10\.00 over 3 results/);
  // The t half: losing beyond luck clears only once t is above -PROBATION_T/2.
  const q = new Probation({ ...DEFAULT_PROBATION, bench: true, minTrades: 10 });
  for (let i = 0; i < 12; i++) q.record('kalshi', i % 3 ? -0.8 : 0.3, at(i));
  assert.equal(q.open('kalshi'), false);
  for (let i = 0; i < 7; i++) q.record('kalshi', 0.5, at(20 + i));
  assert.equal(q.status().kalshi.t, -0.62);
  assert.equal(q.open('kalshi'), false, 'net -$1.70 is well within the limit, but t is not yet above -0.5');
  q.record('kalshi', 0.5, at(30));
  assert.equal(q.status().kalshi.t, -0.43);
  assert.ok(q.open('kalshi'));
});

test('an old probation.json with a benched book loads as open, and the verdict is still shown', () => {
  const file = path.join(tmpDir(), 'probation.json');
  fs.writeFileSync(file, JSON.stringify({ kalshi: { results: [-5, -30], since: 0, benched: { at: 1, reason: 'lost' } } }));
  const p = new Probation(DEFAULT_PROBATION, file);
  assert.ok(p.open('kalshi') && p.open('perps'));
  const s = p.status().kalshi;
  assert.deepEqual([s.wouldBench, s.benchActive, s.benched?.reason, s.trades], [true, false, 'lost', 2]);
  assert.equal(new Probation({ ...DEFAULT_PROBATION, bench: true }, file).open('kalshi'), false, 'the owner\'s gate still reads it');
});

test('a promotion still starts a fresh probation for a book that would bench', () => {
  const p = new Probation(DEFAULT_PROBATION);
  try {
    setProbation(p);
    p.record('kalshi', -30, at(0));
    assert.ok(p.status().kalshi.wouldBench && p.open('kalshi'));
    const audit = tmpAudit();
    const t = new AutoTrainer({ cfg: loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), DATA_DIR: tmpDir() }), engine: {} as never, audit, alerter: new Alerter([], audit) });
    (t as unknown as { record(kind: string, detail: string): void }).record('fill', 'fill-new');
    const s = p.status().kalshi;
    assert.deepEqual([s.trades, s.wouldBench, s.benched], [0, false, null]);
  } finally { setProbation(undefined); }
});
