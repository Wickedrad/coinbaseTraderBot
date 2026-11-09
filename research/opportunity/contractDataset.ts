/** Observed index paths and venue terms, kept separate from exchange OHLC labels. */
import { createHash } from 'node:crypto';
import { IndexTracker } from '../../bot/marketdata/indexTracker';
import { contractTimingQuery, type ContractTimingQuery, type TimedPriceContract } from './contractTiming';
import type { AtlasFeatureFrame, MinuteEntryAnchor } from './features';
import { encodePathFrame } from './jointPathData';
import { encodeSnnState, type AtlasSnnState } from './snnState';

export const CONTRACT_DATASET_SCHEMA = 'opportunity-contract-observations-v1';
export const CONTRACT_LABEL_SCHEMA = 'opportunity-contract-outcomes-v1';
export const digest = (v: unknown) => createHash('sha256').update(JSON.stringify(v)).digest('hex');
export const stamp = (n: number) => Number.isSafeInteger(n) && n >= 0;
export interface OfficialPrint { ts: number; knownAt: number; value: number }
export interface IndexEvidence {
  asset: string; reference: string; sourceSha256: string;
  basis: 'observed-index' | 'synthetic-fixture'; prints: OfficialPrint[];
}
export interface TimelyMoveDefinition {
  id: string; kind: 'move' | 'reversal' | 'continuation'; direction: 'up' | 'down';
  /** Fixed at decision time, possibly derived from the then-known ATR. Units are price bps. */
  thresholdBps?: number; thresholdAtr?: number; sustainSec: number; sustainFraction: number;
  priorWindowSec: number; priorDriftBps?: number; priorDriftAtr?: number;
}
export interface ContractObservation {
  schema: typeof CONTRACT_DATASET_SCHEMA; id: string; frame: AtlasFeatureFrame;
  query: Readonly<ContractTimingQuery>; event: TimelyMoveDefinition; snn: AtlasSnnState | null;
  anchor: MinuteEntryAnchor | null;
  index: { reference: string; sourceSha256: string; basis: IndexEvidence['basis']; knownAt: number; at: number;
    value: number; partialAverage: number | null; partialCount: number; priorReturnBps: number | null };
  termsSourceSha256: string;
  termsBasis: 'declared-contract' | 'recorded-contract' | 'computed-opening-index';
}
export interface ContractOutcome {
  schema: typeof CONTRACT_LABEL_SCHEMA; observationId: string; plannedThrough: number; knownAt: number;
  status: 'complete' | 'missing-index' | 'pending' | 'settlement-disagreement';
  /** Neither, move only, side pays only, both. This is a joint outcome, not independent labels. */
  category: 0 | 1 | 2 | 3 | null; timelyMove: boolean | null; sidePays: boolean | null;
  settlementAverage: number | null; officialResultConfirmed: boolean;
  firstMoveAt: number | null; mfeBps: number | null; maeBps: number | null; terminalMoveBps: number | null;
  basis: 'reconstructed-official-index-rule'; reason: string | null;
}
const validatedIndices = new WeakSet<IndexEvidence>();
export function freezeIndexEvidence(e: IndexEvidence): IndexEvidence {
  validateIndex(e);
  const copy = { ...e, prints: e.prints.map((p) => Object.freeze({ ...p })) };
  Object.freeze(copy.prints); Object.freeze(copy); validatedIndices.add(copy); return copy;
}
export function validateEvent(e: TimelyMoveDefinition) {
  const positive = (n: number | undefined): n is number => n !== undefined && Number.isFinite(n) && n > 0;
  const threshold = positive(e.thresholdBps) !== positive(e.thresholdAtr);
  const drift = positive(e.priorDriftBps) !== positive(e.priorDriftAtr);
  if (!e.id || !['move', 'reversal', 'continuation'].includes(e.kind) || !['up', 'down'].includes(e.direction) ||
      !threshold || (e.thresholdBps !== undefined && (!positive(e.thresholdBps) || e.thresholdBps >= 10000)) ||
      (e.thresholdAtr !== undefined && !positive(e.thresholdAtr)) ||
      !Number.isInteger(e.sustainSec) || e.sustainSec < 0 || e.sustainSec > 3600 ||
      !Number.isFinite(e.sustainFraction) || e.sustainFraction <= 0 || e.sustainFraction > 1 ||
      !Number.isInteger(e.priorWindowSec) || e.priorWindowSec < 0 || e.priorWindowSec > 86400 ||
      (e.priorDriftBps !== undefined && (!Number.isFinite(e.priorDriftBps) || e.priorDriftBps < 0)) ||
      (e.priorDriftAtr !== undefined && !positive(e.priorDriftAtr)) ||
      (e.kind !== 'move' && (e.priorWindowSec < 1 || !drift))) throw new Error('invalid timely move definition');
}
export const moveThresholdBps = (o: ContractObservation) => o.event.thresholdBps ?? o.event.thresholdAtr! * o.anchor!.atrBps!;
export const priorThresholdBps = (o: ContractObservation) => o.event.priorDriftBps ?? (o.event.priorDriftAtr ?? 0) * (o.anchor?.atrBps ?? 0);
/** No correction policy is assumed: conflicting same-time values require a separate audited feed. */
export function validateIndex(e: IndexEvidence) {
  if (validatedIndices.has(e)) return;
  if (!e.asset || !e.reference || !/^[a-f0-9]{64}$/.test(e.sourceSha256) ||
      !['observed-index', 'synthetic-fixture'].includes(e.basis) || e.prints.length > 2000000) throw new Error('invalid index evidence');
  for (let i = 0; i < e.prints.length; i++) {
    const p = e.prints[i];
    if (![p.ts, p.knownAt].every(stamp) || p.knownAt < p.ts || !Number.isFinite(p.value) || p.value <= 0 ||
        (i > 0 && p.ts <= e.prints[i - 1].ts)) throw new Error('invalid, duplicate or unordered index print');
  }
}
function point(e: IndexEvidence, at: number, knownBy: number, gap = 3000): OfficialPrint | null {
  let lo = 0, hi = e.prints.length;
  while (lo < hi) { const mid = (lo + hi) >>> 1; if (e.prints[mid].ts <= at) lo = mid + 1; else hi = mid; }
  // A later arrival cannot displace a print in an earlier query.
  for (let i = lo - 1; i >= 0 && at - e.prints[i].ts <= gap; i--) if (e.prints[i].knownAt <= knownBy) return e.prints[i];
  return null;
}
function tracker(e: IndexEvidence, through: number, knownBy: number, from: number) {
  const t = new IndexTracker(e.asset, through - from + 10000);
  let lo = 0, hi = e.prints.length;
  while (lo < hi) { const mid = (lo + hi) >>> 1; if (e.prints[mid].ts < from - 3000) lo = mid + 1; else hi = mid; }
  for (let i = lo; i < e.prints.length && e.prints[i].ts <= through; i++) {
    const p = e.prints[i]; if (p.knownAt <= knownBy) t.add(p.value, p.ts);
  }
  return t;
}
export function buildContractObservation(frame: AtlasFeatureFrame, contract: TimedPriceContract, event: TimelyMoveDefinition,
  evidence: IndexEvidence, options: { side: 'yes' | 'no'; executionBufferMs: number; termsSourceSha256: string;
    asOf?: number; snn?: AtlasSnnState | null; anchor?: MinuteEntryAnchor | null; termsBasis?: ContractObservation['termsBasis'] }): ContractObservation {
  validateEvent(event); validateIndex(evidence);
  const q = contractTimingQuery(frame, contract, { ...options, direction: event.direction, eventDefinitionId: event.id });
  if (q.contract.closeTime - q.asOf > 86400000 || evidence.asset !== q.asset || evidence.reference !== q.contract.settlementReference ||
      !Number.isInteger(q.contract.averagingSec) || q.contract.averagingSec > 3600 || q.contract.closeTime % 1000 ||
      !/^[a-f0-9]{64}$/.test(options.termsSourceSha256)) throw new Error('incompatible index, terms source or averaging rule');
  const p = point(evidence, q.asOf, q.asOf);
  if (!p) throw new Error('current official index unavailable');
  const partial = tracker(evidence, q.asOf, q.asOf, q.contract.closeTime - q.contract.averagingSec * 1000)
    .settlement(q.contract.closeTime, q.asOf, q.contract.averagingSec);
  const prior = event.priorWindowSec ? point(evidence, q.asOf - event.priorWindowSec * 1000, q.asOf) : null;
  const core: Omit<ContractObservation, 'id'> = { schema: CONTRACT_DATASET_SCHEMA, frame, query: q,
    event: { ...event }, snn: options.snn ?? null, anchor: options.anchor ?? null, termsSourceSha256: options.termsSourceSha256,
    termsBasis: options.termsBasis ?? 'declared-contract',
    index: { reference: evidence.reference, sourceSha256: evidence.sourceSha256, basis: evidence.basis, knownAt: p.knownAt,
      at: p.ts, value: p.value, partialAverage: partial?.avg ?? null, partialCount: partial?.n ?? 0,
      priorReturnBps: prior ? Math.log(p.value / prior.value) * 10000 : null } };
  const obs = { ...core, id: digest(core) };
  encodeContractObservation(obs);
  return obs;
}

/** A single encoder for fitting and queries. Labels, provenance hashes and raw times stay out. */
export function encodeContractObservation(o: ContractObservation): Record<string, number> {
  validateEvent(o.event);
  const q = contractTimingQuery(o.frame, o.query.contract, { side: o.query.side, direction: o.event.direction,
    eventDefinitionId: o.event.id, executionBufferMs: o.query.executionBufferMs, asOf: o.query.asOf,
    maximumFrameAgeMs: o.query.maximumFrameAgeMs });
  const { id, ...core } = o;
  if ((o.event.thresholdAtr !== undefined || o.event.priorDriftAtr !== undefined) && (!o.anchor ||
      !stamp(o.anchor.knownAt) || o.anchor.knownAt > o.query.asOf || !Number.isFinite(o.anchor.atrBps) || !(o.anchor.atrBps! > 0) ||
      !Number.isFinite(o.anchor.price) || !(o.anchor.price > 0) || !o.anchor.definition)) throw new Error('causal entry ATR required for volatility-relative event');
  if (!(moveThresholdBps(o) > 0) || moveThresholdBps(o) >= 10000) throw new Error('invalid scaled movement');
  if (o.schema !== CONTRACT_DATASET_SCHEMA || digest(core) !== id || digest(q) !== digest(o.query) ||
      !['declared-contract', 'recorded-contract', 'computed-opening-index'].includes(o.termsBasis) ||
      o.index.reference !== q.contract.settlementReference || !/^[a-f0-9]{64}$/.test(o.index.sourceSha256) ||
      !/^[a-f0-9]{64}$/.test(o.termsSourceSha256) || !['observed-index', 'synthetic-fixture'].includes(o.index.basis) ||
      ![o.index.at, o.index.knownAt].every(stamp) || o.index.at > o.index.knownAt || o.index.knownAt > q.asOf ||
      q.asOf - o.index.at > 3000 || !Number.isFinite(o.index.value) || o.index.value <= 0 ||
      !Number.isInteger(o.index.partialCount) || o.index.partialCount < 0 || o.index.partialCount > q.contract.averagingSec! ||
      (o.index.partialAverage !== null && (!Number.isFinite(o.index.partialAverage) || o.index.partialAverage <= 0)) ||
      (o.index.partialCount === 0) !== (o.index.partialAverage === null) ||
      (q.asOf >= q.contract.closeTime - q.contract.averagingSec! * 1000 + 1000 && o.index.partialCount === 0) ||
      (o.index.priorReturnBps !== null && !Number.isFinite(o.index.priorReturnBps))) throw new Error('invalid or unavailable contract observation');
  const x = { ...encodePathFrame(o.frame, true), ...encodeSnnState(o.snn, q.asOf) };
  for (const [k, v] of Object.entries(q.geometry)) x[`contract:${k}`] = v;
  for (const kind of ['updown', 'greater', 'between', 'less']) x[`contract:kind_${kind}`] = Number(q.contract.terms.kind === kind);
  const k = q.contract.terms.strike, cap = q.contract.terms.cap;
  Object.assign(x, { 'contract:side_yes': Number(q.side === 'yes'), 'contract:direction_up': Number(q.direction === 'up'),
    'contract:log_moneyness': k ? Math.log(o.index.value / k) : NaN,
    'contract:log_cap_moneyness': cap ? Math.log(o.index.value / cap) : NaN,
    'contract:partial_average_relative': o.index.partialAverage === null ? NaN : Math.log(o.index.partialAverage / o.index.value),
    'contract:partial_count': o.index.partialCount, 'contract:averaging_sec': q.contract.averagingSec!,
    'contract:index_age_sec': (q.asOf - o.index.at) / 1000, 'contract:prior_return_bps': o.index.priorReturnBps ?? NaN,
    'contract:move_bps': moveThresholdBps(o), 'contract:atr_bps': o.anchor?.atrBps ?? NaN, 'contract:sustain_sec': o.event.sustainSec,
    'contract:sustain_fraction': o.event.sustainFraction, 'contract:prior_sec': o.event.priorWindowSec,
    'contract:prior_drift_bps': priorThresholdBps(o) });
  for (const kind of ['move', 'reversal', 'continuation']) x[`contract:event_${kind}`] = Number(o.event.kind === kind);
  for (const key of Object.keys(x).filter((n) => n.startsWith('contract:'))) x[`missing:${key}`] = Number(!Number.isFinite(x[key]));
  return x;
}

/** Labels use a decision-anchored one-second movement grid and the existing official
 * sixty-mark settlement rule. No minute closes, interpolation or missing-index NO labels. */
export function labelContract(o: ContractObservation, evidence: IndexEvidence, knownBy: number,
  actualResult?: { yes: boolean; knownAt: number }): ContractOutcome {
  encodeContractObservation(o); validateIndex(evidence);
  const q = o.query, c = q.contract, e = o.event;
  if (!stamp(knownBy) || evidence.asset !== q.asset || evidence.reference !== o.index.reference || evidence.sourceSha256 !== o.index.sourceSha256 ||
      (actualResult && (typeof actualResult.yes !== 'boolean' || !stamp(actualResult.knownAt) || actualResult.knownAt < c.closeTime))) throw new Error('invalid label provenance/cutoff');
  const out: ContractOutcome = { schema: CONTRACT_LABEL_SCHEMA, observationId: o.id, plannedThrough: c.closeTime,
    knownAt: knownBy, status: 'pending', category: null, timelyMove: null, sidePays: null,
    settlementAverage: null, officialResultConfirmed: false, firstMoveAt: null, mfeBps: null, maeBps: null,
    terminalMoveBps: null, basis: 'reconstructed-official-index-rule', reason: null };
  if (knownBy < c.closeTime) return out;
  const unavailable = (reason: string) => ({ ...out, status: 'missing-index' as const, reason });
  const t = tracker(evidence, c.closeTime, knownBy, c.closeTime - c.averagingSec! * 1000);
  const settlement = t.settlement(c.closeTime, c.closeTime, c.averagingSec!);
  if (!settlement || settlement.n !== c.averagingSec) return unavailable('incomplete official settlement marks');
  let labelKnownAt = c.closeTime;
  for (let mark = c.closeTime - (c.averagingSec! - 1) * 1000; mark <= c.closeTime; mark += 1000)
    labelKnownAt = Math.max(labelKnownAt, point(evidence, mark, knownBy)!.knownAt);
  const sign = e.direction === 'up' ? 1 : -1, start = o.index.value;
  const prior = e.priorWindowSec ? point(evidence, q.asOf - e.priorWindowSec * 1000, q.asOf) : null;
  if (e.kind !== 'move' && !prior) return unavailable('preceding drift unavailable');
  const priorDrift = prior ? sign * Math.log(start / prior.value) * 10000 : 0;
  const eligible = e.kind === 'move' || (e.kind === 'reversal' ? priorDrift <= -priorThresholdBps(o) : priorDrift >= priorThresholdBps(o));
  const moves: number[] = [], times: number[] = [];
  for (let mark = q.asOf + 1000; mark <= q.effectBy; mark += 1000) {
    const p = point(evidence, mark, knownBy);
    if (!p) return unavailable('movement grid has an index gap');
    labelKnownAt = Math.max(labelKnownAt, p.knownAt);
    moves.push(sign * (p.value / start - 1) * 10000); times.push(mark);
  }
  // Fractional last seconds are explicitly outside this one-second event definition.
  for (let i = 0; eligible && i < moves.length; i++) {
    if (moves[i] < moveThresholdBps(o) || i + e.sustainSec >= moves.length) continue;
    if (moves.slice(i, i + e.sustainSec + 1).every((m) => m >= moveThresholdBps(o) * e.sustainFraction)) { out.firstMoveAt = times[i]; break; }
  }
  const a = settlement.avg, terms = c.terms;
  const yes = terms.kind === 'less' ? a < terms.cap! : a >= terms.strike! && (terms.kind !== 'between' || a < terms.cap!);
  out.settlementAverage = a; out.timelyMove = out.firstMoveAt !== null; out.sidePays = q.side === 'yes' ? yes : !yes;
  out.mfeBps = Math.max(0, ...moves); out.maeBps = Math.min(0, ...moves); out.terminalMoveBps = (a / start - 1) * 10000;
  out.officialResultConfirmed = !!actualResult && actualResult.knownAt <= knownBy;
  if (out.officialResultConfirmed) labelKnownAt = Math.max(labelKnownAt, actualResult!.knownAt);
  out.knownAt = labelKnownAt;
  if (out.officialResultConfirmed && actualResult!.yes !== yes) return { ...out, status: 'settlement-disagreement', reason: 'reported result differs from index reconstruction' };
  out.category = (Number(out.timelyMove) + 2 * Number(out.sidePays)) as 0 | 1 | 2 | 3;
  out.status = 'complete';
  return out;
}
