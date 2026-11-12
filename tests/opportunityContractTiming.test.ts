import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { AtlasFeatureFrame } from '../research/opportunity/features';
import { CausalAtlasFeatures } from '../research/opportunity/features';
import { assessContractTiming, contractTimingQuery, type ContractPathForecast, type ContractTimingQuery,
  type MovementTimingForecast, type ProbabilityBounds, type TimedPriceContract } from '../research/opportunity/contractTiming';

const MIN = 60000, start = Date.UTC(2025, 5, 2, 12), now = start;
const policy = { minimumMoveLowerBound: 0.8, minimumJointLowerBound: 0.8 };
const bounds = (p: number, lower = p - 0.02, upper = Math.min(1, p + 0.02)): ProbabilityBounds => ({ probability: p, lower, upper });
function frame(at = now): AtlasFeatureFrame {
  const f = new CausalAtlasFeatures('BTC', { source: 'synthetic', sha256: null });
  f.push({ ts: Math.floor(at / MIN) * MIN - MIN, o: 100, h: 101, l: 99, c: 100, v: 1 });
  return f.snapshot();
}
function contract(minutes: number, patch: Partial<TimedPriceContract> = {}): TimedPriceContract {
  return { ticker: `TEST-${minutes}`, asset: 'BTC', openTime: start, closeTime: start + minutes * MIN,
    termsKnownAt: start, terms: { kind: minutes === 15 ? 'updown' : 'greater', strike: 100 },
    settlementReference: 'synthetic-index', ...patch };
}
function query(c = contract(15), at = now, executionBufferMs = 0) {
  return contractTimingQuery(frame(at), c, { side: 'yes', direction: 'up', eventDefinitionId: 'turn-up-v1', executionBufferMs, asOf: at });
}
function forecast(q: Readonly<ContractTimingQuery>, patch: Partial<ContractPathForecast> = {}): ContractPathForecast {
  return { kind: 'contract-path', id: 'joint-synthetic', modelId: 'synthetic-test-model', asset: q.asset,
    asOf: q.asOf, featuresKnownAt: q.featuresKnownAt, byAt: q.effectBy, direction: q.direction, eventDefinitionId: q.eventDefinitionId,
    contract: structuredClone(q.contract), side: q.side, settlementBasis: 'official-index-average',
    calibrationRef: 'synthetic-test-reference-only', moveBy: bounds(0.94), sidePays: bounds(0.95),
    timelyMoveAndSidePays: bounds(0.91, 0.85, 0.94), ...patch };
}
const assess = (q: Readonly<ContractTimingQuery>, fs: Array<ContractPathForecast | MovementTimingForecast>) => assessContractTiming(q, fs, policy);

test('one-hour setup stays context for 15m, while an exact hourly joint forecast supports the hourly question', () => {
  const h1 = query(contract(60)), m15 = query();
  const long: MovementTimingForecast = { kind: 'movement', id: 'hour-turn', modelId: 'synthetic-hourly', asset: 'BTC', asOf: now,
    featuresKnownAt: now, direction: 'up', eventDefinitionId: 'turn-up-v1', byAt: now + 60 * MIN, moveBy: bounds(0.99) };
  const hour = forecast(h1);
  assert.equal(assess(h1, [long, hour]).status, 'timing-supported');
  const quarter = assess(m15, [long, hour]);
  assert.equal(quarter.status, 'context-only'); assert.equal(quarter.forecastId, null);
  assert.equal(quarter.context[0].moveBy.probability, 0.99, 'retain continuous long-horizon context');
  assert.equal(quarter.context[0].eventDefinitionId, 'turn-up-v1');
  assert.equal(quarter.liveEntryAllowed, false);
});

test('a later fresh short-window forecast can support the 15m contract once the setup starts unfolding', () => {
  const original = query(contract(60)), initial = forecast(original);
  const later = start + 45 * MIN;
  const short = query(contract(15, { ticker: 'NEXT-15', openTime: later, closeTime: start + 60 * MIN, termsKnownAt: later }), later);
  assert.equal(assess(short, [initial]).status, 'unavailable', 'counting down an old hourly forecast is not fresh short evidence');
  const refreshed = forecast(short, { id: 'fresh-short' });
  assert.equal(assess(short, [refreshed]).status, 'timing-supported');
  assert.equal(short.geometry.remaining_sec, 900); assert.equal(short.geometry.life_sec, 900);
});

test('remaining time controls the question for both 15m and hourly contracts, with no nearest-horizon substitution', () => {
  for (const [life, elapsed] of [[15, 6], [60, 51]]) {
    const q = query(contract(life), start + elapsed * MIN);
    assert.equal(q.geometry.remaining_sec, 9 * 60);
    assert.equal(q.geometry.life_sec, life * 60);
    const wrong = forecast(q, { byAt: q.asOf + life * MIN });
    assert.equal(assess(q, [wrong]).status, 'context-only');
    assert.equal(assess(q, [forecast(q)]).status, 'timing-supported');
  }
});

test('execution buffer is explicit and forecasts must answer its exact deadline, including fractional minutes', () => {
  const q = query(contract(15), start + 6 * MIN, 30000);
  assert.equal(q.effectBy, start + 14.5 * MIN);
  assert.equal(q.geometry.effect_window_sec, 510);
  assert.equal(assess(q, [forecast(q, { byAt: q.contract.closeTime })]).status, 'context-only');
  assert.equal(assess(q, [forecast(q)]).status, 'timing-supported');
  const averaging = query(contract(15), start + 14.5 * MIN);
  assert.equal(averaging.geometry.until_settlement_window_sec, 0);
  assert.equal(averaging.geometry.settlement_window_elapsed_fraction, 0.5);
  assert.equal(averaging.geometry.feature_snapshot_age_sec, 30);
  assert.equal(averaging.featureSnapshotAt, start + 14 * MIN);
});

test('high move confidence cannot substitute for this strike paying, or an uncertain joint outcome', () => {
  const q = query();
  const badStrike = forecast(q, { moveBy: bounds(0.95), sidePays: bounds(0.25), timelyMoveAndSidePays: bounds(0.22) });
  assert.equal(assess(q, [badStrike]).status, 'insufficient-confidence');
  const uncertain = forecast(q, { timelyMoveAndSidePays: bounds(0.91, 0.79, 0.94) });
  assert.equal(assess(q, [uncertain]).status, 'insufficient-confidence', 'joint uncertainty is not replaced by multiplying confident marginals');
  const weakShortTiming = forecast(q, { moveBy: bounds(0.94, 0.79, 0.98) });
  assert.equal(assess(q, [weakShortTiming]).status, 'insufficient-confidence');
  const timingOnly = assessContractTiming(q, [badStrike], { minimumMoveLowerBound: 0.8, minimumJointLowerBound: 0.1 });
  assert.equal(timingOnly.status, 'timing-supported', 'timing relevance does not impose a universal high settlement-win probability');
  assert.equal(timingOnly.liveEntryAllowed, false, 'quotes, costs and economic value are still a separate decision');
  const incoherent = forecast(q, { timelyMoveAndSidePays: bounds(0.99) });
  const r = assess(q, [incoherent]);
  assert.equal(r.forecastId, null); assert.match(r.rejected[0].reason, /incoherent/);
});

test('different strikes, contract sides, ranges, settlement references and spot-close proxies cannot authorize the query', () => {
  const q = query();
  for (const c of [
    { ...q.contract, terms: { kind: 'updown' as const, strike: 101 } },
    { ...q.contract, terms: { kind: 'between' as const, strike: 100, cap: 105 } },
    { ...q.contract, settlementReference: 'other-index' },
    { ...q.contract, averagingSec: 30 },
    { ...q.contract, termsKnownAt: now + MIN },
  ]) assert.equal(assess(q, [forecast(q, { contract: c })]).forecastId, null);
  assert.equal(assess(q, [forecast(q, { side: 'no' })]).forecastId, null);
  assert.equal(assess(q, [forecast(q, { direction: 'down' })]).forecastId, null);
  assert.equal(assess(q, [forecast(q, { eventDefinitionId: 'different-turn' })]).forecastId, null);
  assert.equal(assess(q, [forecast(q, { settlementBasis: 'spot-close-proxy' })]).forecastId, null);
});

test('stale, future and different-asset predictions are unavailable, and calibration is not fabricated', () => {
  const q = query();
  for (const patch of [{ asOf: now - MIN }, { asOf: now + MIN }, { featuresKnownAt: now + 1 }, { asset: 'ETH' }, { moveBy: bounds(NaN) }]) {
    const r = assess(q, [forecast(q, patch)]);
    assert.equal(r.status, 'unavailable'); assert.equal(r.context.length, 0);
  }
  const uncalibrated = assess(q, [forecast(q, { calibrationRef: null })]);
  assert.equal(uncalibrated.status, 'unvalidated'); assert.equal(uncalibrated.liveEntryAllowed, false);
});

test('multiple models need upstream validated aggregation instead of selecting the highest probability', () => {
  const q = query();
  const r = assess(q, [forecast(q), forecast(q, { id: 'another-model', modelId: 'another-synthetic-model' })]);
  assert.equal(r.status, 'unavailable'); assert.equal(r.forecastId, null);
  assert.ok(r.rejected.every((x) => /aggregation/.test(x.reason)));
  assert.throws(() => assessContractTiming(q, [], { ...policy, minimumJointLowerBound: NaN }), /policy/);
});

test('query captures immutable geometry and rejects inactive contracts, future source features and unavailable strikes', () => {
  const c = contract(15), q = query(c);
  c.terms.strike = 999;
  assert.equal(q.contract.terms.strike, 100);
  assert.throws(() => { q.contract.terms.strike = 999; }, TypeError);
  for (const bad of [contract(15, { openTime: start + MIN }), contract(15, { closeTime: start }),
    contract(15, { termsKnownAt: start + MIN }), contract(15, { terms: { kind: 'updown' } }),
    contract(15, { terms: { kind: 'match' } }), contract(15, { averagingSec: 10000 })]) assert.throws(() => query(bad));
  assert.throws(() => query(contract(15), start, 15 * MIN));
  assert.throws(() => contractTimingQuery(frame(), contract(15), { side: 'yes', direction: 'up', eventDefinitionId: 'turn', executionBufferMs: 0, asOf: start + 2 * MIN }), /unavailable/);
  const f = frame();
  const future: AtlasFeatureFrame = { ...f, groups: { ...f.groups, clock: { ...f.groups.clock, knownAt: start + MIN } } };
  assert.throws(() => contractTimingQuery(future, contract(15), { side: 'yes', direction: 'up', eventDefinitionId: 'turn', executionBufferMs: 0 }), /future feature/);
});
