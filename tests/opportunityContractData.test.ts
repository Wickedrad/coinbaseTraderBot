import assert from 'node:assert/strict';
import { test } from 'node:test';
import { SnnNetwork } from '../bot/snn/network';
import { DEFAULT_SNN, stageFlags } from '../bot/snn/params';
import { CausalAtlasFeatures } from '../research/opportunity/features';
import { buildContractObservation, digest, encodeContractObservation, labelContract, type IndexEvidence, type TimelyMoveDefinition } from '../research/opportunity/contractDataset';
import { captureSnnState, combineSnnStates, encodeSnnState } from '../research/opportunity/snnState';

const start = Date.UTC(2023, 0, 2), sha = 'a'.repeat(64);
export function indexFixture(value: (sec: number) => number = (s) => s >= 30 ? 102 : 100): IndexEvidence {
  return { asset: 'BTC', reference: 'fixture-RTI', sourceSha256: sha, basis: 'synthetic-fixture',
    prints: Array.from({ length: 241 }, (_, i) => ({ ts: start + (i - 120) * 1000, knownAt: start + (i - 120) * 1000, value: value(i - 120) })) };
}
const event: TimelyMoveDefinition = { id: 'fixture-move', kind: 'move', direction: 'up', thresholdBps: 100, sustainSec: 5, sustainFraction: 0.8, priorWindowSec: 0, priorDriftBps: 0 };
function observation(e = indexFixture(), change: Partial<TimelyMoveDefinition> = {}) {
  const f = new CausalAtlasFeatures('BTC', { source: 'synthetic', sha256: sha });
  f.push({ ts: start - 60000, o: 100, h: 101, l: 99, c: 100, v: 1 });
  return buildContractObservation(f.snapshot(), { ticker: 'FIXTURE', asset: 'BTC', openTime: start - 780000, closeTime: start + 120000,
    termsKnownAt: start - 780000, terms: { kind: 'updown', strike: 101 }, settlementReference: e.reference }, { ...event, ...change }, e,
  { side: 'yes', executionBufferMs: 10000, termsSourceSha256: sha });
}

test('official-index labels separate timely direction from paying settlement and use sixty marks', () => {
  const e = indexFixture(), o = observation(e), y = labelContract(o, e, start + 120000, { yes: true, knownAt: start + 120000 });
  assert.equal(y.status, 'complete'); assert.equal(y.category, 3); assert.equal(y.firstMoveAt, start + 30000);
  assert.equal(y.settlementAverage, 102); assert.equal(y.officialResultConfirmed, true);
  const finalMinuteOnly = indexFixture((s) => s >= 61 ? 102 : 100);
  const last = finalMinuteOnly.prints.at(-1)!; last.value = 500;
  const p = labelContract(observation(finalMinuteOnly), finalMinuteOnly, start + 120000);
  assert.ok(Math.abs(p.settlementAverage! - (59 * 102 + 500) / 60) < 1e-10, 'not the last close');
  const downAtClose = indexFixture((s) => s >= 81 ? 98 : s >= 30 ? 102 : 100);
  assert.equal(labelContract(observation(downAtClose), downAtClose, start + 120000).category, 1, 'a timely move can still lose the contract');
});

test('missing, late and contradictory index outcomes remain unavailable rather than invented losses', () => {
  const e = indexFixture(), o = observation(e);
  assert.equal(labelContract(o, e, start + 119999).status, 'pending');
  const gap = structuredClone(e); gap.prints = gap.prints.filter((p) => p.ts < start + 70000 || p.ts > start + 80000);
  assert.equal(labelContract(o, gap, start + 120000).status, 'missing-index');
  const late = structuredClone(e); late.prints.at(-1)!.knownAt += 10000;
  // A bounded last-known print is allowed by the existing official sampling rule.
  assert.equal(labelContract(o, late, start + 120000).settlementAverage, 102);
  const disagree = labelContract(o, e, start + 121000, { yes: false, knownAt: start + 121000 });
  assert.equal(disagree.status, 'settlement-disagreement'); assert.equal(disagree.category, null);
  const future = indexFixture(); future.prints.find((p) => p.ts === start)!.knownAt = start + 10000;
  future.prints.find((p) => p.ts === start)!.value = 999;
  assert.equal(observation(future).index.value, 100, 'future arrival cannot enter current features');
});

test('reversal and continuation require preceding drift and sustained movement before the exact deadline', () => {
  const falling = indexFixture((s) => s < 0 ? 102 : s >= 30 ? 102 : 100);
  const r = observation(falling, { kind: 'reversal', priorWindowSec: 60, priorDriftBps: 50 });
  assert.equal(labelContract(r, falling, start + 120000).timelyMove, true);
  assert.equal(labelContract(observation(falling, { kind: 'continuation', priorWindowSec: 60, priorDriftBps: 50 }), falling, start + 120000).timelyMove, false);
  const brief = indexFixture((s) => s === 30 ? 102 : 100);
  assert.equal(labelContract(observation(brief), brief, start + 120000).timelyMove, false);
  const tooLate = indexFixture((s) => s >= 108 ? 102 : 100);
  assert.equal(labelContract(observation(tooLate), tooLate, start + 120000).timelyMove, false, 'sustain must finish before close minus buffer');
});

test('SNN capture preserves the existing network byte for byte and refuses future checkpoints', () => {
  const net = new SnnNetwork({ ...DEFAULT_SNN, nE: 16, nI: 4, nL1: 8, flags: stageFlags('S6') });
  for (let s = 0; s <= 10; s++) net.step(start - 10000 + s * 1000, [{ key: 'BTC-15m', asset: 'BTC', price: 100 + s / 10 }]);
  const before = JSON.stringify(net.serialize());
  const p = { checkpointSha256: sha, inputSourceSha256: sha, checkpointKnownAt: start - 11000, trainedThrough: start - 11000, inputKnownAt: start,
    domain: 'crypto' as const,
    variant: 'S6' as const, basis: 'observed-tape' as const };
  const state = captureSnnState(net, start, p);
  assert.equal(JSON.stringify(net.serialize()), before);
  assert.ok(Object.keys(state.columns[0].values).some((k) => k.startsWith('latent_l2')));
  assert.ok(Object.keys(encodeSnnState(state, start)).every((k) => !k.includes(sha)));
  assert.throws(() => captureSnnState(net, start, { ...p, trainedThrough: start + 1 }), /noncausal/);
  assert.throws(() => captureSnnState(net, start, { ...p, domain: 'perps' }), /horizon/);
  assert.throws(() => encodeSnnState({ ...state, stateAt: start - 3000 }, start), /stale/);
  assert.deepEqual(encodeSnnState(null, start), { 'snn:available': 0 });
  const perpsNet = new SnnNetwork({ ...DEFAULT_SNN, nE: 16, nI: 4, nL1: 8, flags: stageFlags('S6') });
  perpsNet.step(start, [{ key: 'BTC-60m', asset: 'BTC', price: 100 }]);
  const perps = captureSnnState(perpsNet, start, { ...p, domain: 'perps' });
  const combined = combineSnnStates([state, perps]);
  assert.equal(combined.provenance.domain, 'combined'); assert.equal(combined.columns.length, 2);
  assert.ok(combined.columns.some((c) => c.key.startsWith('crypto_'))); assert.ok(combined.columns.some((c) => c.key.startsWith('perps_')));
  assert.throws(() => combineSnnStates([state, state]), /one crypto/);
});

test('numeric contract encoding excludes labels and provenance and rejects content changes', () => {
  const o = observation(), x = encodeContractObservation(o);
  assert.equal(x['contract:remaining_sec'], 120); assert.equal(x['contract:effect_window_sec'], 110);
  assert.ok(Object.keys(x).every((k) => !/label|sha256|knownAt|outcome|ticker/.test(k)));
  assert.throws(() => encodeContractObservation({ ...o, index: { ...o.index, value: 120 } }), /observation/);
  const forged = { ...o, index: { ...o.index, knownAt: start + 1 } }; const { id, ...core } = forged;
  assert.throws(() => encodeContractObservation({ ...forged, id: digest(core) }), /observation/);
});

test('volatility-relative event thresholds require a causal entry scale', () => {
  const e = indexFixture(), o = observation(e), relative = { ...event, thresholdBps: undefined, thresholdAtr: 2 };
  assert.throws(() => buildContractObservation(o.frame, o.query.contract, relative, e,
    { side: 'yes', executionBufferMs: 0, termsSourceSha256: sha }), /entry ATR/);
  const scaled = buildContractObservation(o.frame, o.query.contract, relative, e, { side: 'yes', executionBufferMs: 0, termsSourceSha256: sha,
    anchor: { price: 100, atrBps: 50, knownAt: start, firstOpen: start - 14 * 60000, definition: 'builtin-ATR14-over-last-1440-contiguous-1m-bars' } });
  assert.equal(encodeContractObservation(scaled)['contract:move_bps'], 100);
  assert.equal(labelContract(scaled, e, start + 120000).timelyMove, true);
});
