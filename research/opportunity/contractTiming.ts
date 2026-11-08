/** Offline contract-timing contract for future path learners. Never an order signal. */
import { SETTLEMENT_AVG_SEC, type ContractTerms } from '../../bot/model/fairValue';
import type { AtlasFeatureFrame } from './features';

export const CONTRACT_TIMING_SCHEMA = 'opportunity-contract-timing-v1';
export interface TimedPriceContract {
  ticker: string; asset: string; openTime: number; closeTime: number; termsKnownAt: number;
  terms: ContractTerms;
  /** Exact settlement index identity, not an underlying exchange spot-price proxy. */
  settlementReference: string;
  averagingSec?: number;
}
export interface ContractTimingQuery {
  schema: typeof CONTRACT_TIMING_SCHEMA; researchOnly: true;
  asset: string; asOf: number; featureSnapshotAt: number; featuresKnownAt: number; maximumFrameAgeMs: number;
  contract: Readonly<TimedPriceContract & { averagingSec: number }>;
  side: 'yes' | 'no'; direction: 'up' | 'down'; eventDefinitionId: string;
  effectBy: number; executionBufferMs: number;
  geometry: Readonly<Record<string, number>>;
}
function timestamp(t: number) { return Number.isSafeInteger(t) && t >= 0; }
function canonicalContract(c: TimedPriceContract): TimedPriceContract & { averagingSec: number } {
  const averagingSec = c.averagingSec ?? SETTLEMENT_AVG_SEC;
  if (!c.ticker || !c.asset || !c.settlementReference || ![c.openTime, c.closeTime, c.termsKnownAt].every(timestamp) ||
      c.closeTime <= c.openTime || !Number.isFinite(averagingSec) || averagingSec <= 0 || averagingSec * 1000 > c.closeTime - c.openTime) throw new Error('invalid price contract timing');
  const { kind, strike, cap } = c.terms;
  const positive = (x: number | undefined): x is number => x !== undefined && Number.isFinite(x) && x > 0;
  let terms: ContractTerms;
  if ((kind === 'updown' || kind === 'greater') && positive(strike)) terms = { kind, strike };
  else if (kind === 'between' && positive(strike) && positive(cap) && cap > strike) terms = { kind, strike, cap };
  else if (kind === 'less' && positive(cap)) terms = { kind, cap };
  else throw new Error('unsupported or incomplete price contract terms');
  if (kind === 'updown' && c.termsKnownAt < c.openTime) throw new Error('opening-average strike cannot be known before open');
  return { ticker: c.ticker, asset: c.asset, openTime: c.openTime, closeTime: c.closeTime, termsKnownAt: c.termsKnownAt,
    terms: Object.freeze(terms), settlementReference: c.settlementReference, averagingSec };
}

/** Contract geometry is separate from TA candle timeframes and the SNN's column name. */
export function contractTimingQuery(frame: AtlasFeatureFrame, contract: TimedPriceContract,
  options: { side: 'yes' | 'no'; direction: 'up' | 'down'; eventDefinitionId: string; executionBufferMs: number;
    asOf?: number; maximumFrameAgeMs?: number }): Readonly<ContractTimingQuery> {
  const c = canonicalContract(contract), now = options.asOf ?? frame.decisionAt, buffer = options.executionBufferMs;
  const maximumFrameAgeMs = options.maximumFrameAgeMs ?? 60000;
  if (!timestamp(now) || frame.asset !== c.asset || c.termsKnownAt > now || now < c.openTime || now >= c.closeTime ||
      !timestamp(frame.decisionAt) || !Number.isSafeInteger(maximumFrameAgeMs) || maximumFrameAgeMs < 0 ||
      frame.decisionAt > now || now - frame.decisionAt > maximumFrameAgeMs ||
      !Number.isSafeInteger(buffer) || buffer < 0 || now >= c.closeTime - buffer || !options.eventDefinitionId ||
      !['yes', 'no'].includes(options.side) || !['up', 'down'].includes(options.direction)) throw new Error('invalid, inactive or unavailable contract timing query');
  let featuresKnownAt = 0;
  for (const group of Object.values(frame.groups)) {
    if (group.knownAt !== null) {
      if (!timestamp(group.knownAt) || group.knownAt > frame.decisionAt) throw new Error('future feature in contract query');
      featuresKnownAt = Math.max(featuresKnownAt, group.knownAt);
    }
  }
  const lifeSec = (c.closeTime - c.openTime) / 1000, remainingSec = (c.closeTime - now) / 1000;
  const settlementStartsAt = c.closeTime - c.averagingSec * 1000;
  return Object.freeze({ schema: CONTRACT_TIMING_SCHEMA, researchOnly: true, asset: c.asset, asOf: now,
    featureSnapshotAt: frame.decisionAt, featuresKnownAt, maximumFrameAgeMs, contract: Object.freeze(c),
    side: options.side, direction: options.direction, eventDefinitionId: options.eventDefinitionId, executionBufferMs: buffer,
    effectBy: c.closeTime - buffer,
    geometry: Object.freeze({ remaining_sec: remainingSec, life_sec: lifeSec, remaining_life_fraction: remainingSec / lifeSec,
      effect_window_sec: remainingSec - buffer / 1000, until_settlement_window_sec: Math.max(0, (settlementStartsAt - now) / 1000),
      settlement_window_elapsed_fraction: Math.max(0, (now - settlementStartsAt) / (c.averagingSec * 1000)),
      feature_snapshot_age_sec: (now - frame.decisionAt) / 1000 }) });
}

/** Bounds must come from the eventual validated learner; these types do not calibrate it. */
export interface ProbabilityBounds { probability: number; lower: number; upper: number }
export interface MovementTimingForecast {
  kind: 'movement'; id: string; modelId: string; asset: string; asOf: number; featuresKnownAt: number;
  direction: 'up' | 'down'; eventDefinitionId: string; byAt: number;
  moveBy: ProbabilityBounds;
}
export interface ContractPathForecast extends Omit<MovementTimingForecast, 'kind'> {
  kind: 'contract-path'; contract: TimedPriceContract; side: 'yes' | 'no';
  settlementBasis: 'official-index-average' | 'spot-close-proxy';
  /** Reference to future model validation evidence, not a validation performed here. */
  calibrationRef: string | null;
  sidePays: ProbabilityBounds;
  /** Joint probability, never the product of marginal move/settlement probabilities. */
  timelyMoveAndSidePays: ProbabilityBounds;
}
type Forecast = MovementTimingForecast | ContractPathForecast;
export interface ContractTimingAssessment {
  schema: typeof CONTRACT_TIMING_SCHEMA; researchOnly: true; liveEntryAllowed: false;
  status: 'timing-supported' | 'context-only' | 'insufficient-confidence' | 'unavailable' | 'unvalidated';
  query: Readonly<ContractTimingQuery>;
  /** Continuous timing probabilities for the learner; no vote across indicators or timeframes. */
  context: Array<{ id: string; modelId: string; direction: 'up' | 'down'; eventDefinitionId: string; byAt: number; moveBy: ProbabilityBounds }>;
  forecastId: string | null; modelId: string | null; calibrationRef: string | null;
  moveBy: ProbabilityBounds | null; sidePays: ProbabilityBounds | null; timelyMoveAndSidePays: ProbabilityBounds | null;
  rejected: Array<{ id: string; reason: string }>;
  minimumMoveLowerBound: number; minimumJointLowerBound: number;
}
function validBounds(p: ProbabilityBounds) {
  return [p.probability, p.lower, p.upper].every(Number.isFinite) && p.lower >= 0 && p.upper <= 1 && p.lower <= p.probability && p.probability <= p.upper;
}
function sameContract(a: TimedPriceContract, b: TimedPriceContract) {
  const x = canonicalContract(a), y = canonicalContract(b);
  return x.ticker === y.ticker && x.asset === y.asset && x.openTime === y.openTime && x.closeTime === y.closeTime &&
    x.settlementReference === y.settlementReference && x.averagingSec === y.averagingSec &&
    x.terms.kind === y.terms.kind && x.terms.strike === y.terms.strike && x.terms.cap === y.terms.cap;
}

/** No forecast interpolation, horizon rounding, stale countdown, model selection or trading.
 * A validated joint model may read ANY TA timeframe, but must answer THIS exact contract/window.
 * The confidence threshold is caller-specified research policy, not an indicator threshold. */
export function assessContractTiming(query: Readonly<ContractTimingQuery>, forecasts: Forecast[],
  policy: { minimumMoveLowerBound: number; minimumJointLowerBound: number }): ContractTimingAssessment {
  const minimum = policy.minimumJointLowerBound, minimumMove = policy.minimumMoveLowerBound;
  if (!Number.isFinite(minimum) || minimum < 0 || minimum > 1 || !Number.isFinite(minimumMove) || minimumMove <= 0.5 || minimumMove > 1) throw new Error('explicit high-confidence research policy required');
  const out: ContractTimingAssessment = { schema: CONTRACT_TIMING_SCHEMA, researchOnly: true, liveEntryAllowed: false,
    status: 'unavailable', query, context: [], forecastId: null, modelId: null, calibrationRef: null,
    moveBy: null, sidePays: null, timelyMoveAndSidePays: null, rejected: [], minimumMoveLowerBound: minimumMove, minimumJointLowerBound: minimum };
  const exact: ContractPathForecast[] = [];
  for (const f of forecasts) {
    const reject = (reason: string) => out.rejected.push({ id: f.id, reason });
    if (f.asset !== query.asset || f.asOf !== query.asOf || !timestamp(f.featuresKnownAt) || f.featuresKnownAt > f.asOf ||
        !timestamp(f.byAt) || f.byAt <= f.asOf || !f.id || !f.modelId || !f.eventDefinitionId || !['up', 'down'].includes(f.direction) || !validBounds(f.moveBy)) {
      reject('invalid, stale, future or different-asset forecast'); continue;
    }
    out.context.push({ id: f.id, modelId: f.modelId, direction: f.direction, eventDefinitionId: f.eventDefinitionId, byAt: f.byAt, moveBy: { ...f.moveBy } });
    if (f.kind !== 'contract-path') continue;
    if (f.byAt !== query.effectBy || f.direction !== query.direction || f.eventDefinitionId !== query.eventDefinitionId || f.side !== query.side) {
      reject('different remaining-time window, event, direction or side'); continue;
    }
    let same = false;
    try { same = f.contract.termsKnownAt <= query.asOf && sameContract(f.contract, query.contract); } catch { /* invalid geometry cannot support this query */ }
    if (!same || f.settlementBasis !== 'official-index-average') { reject('different contract geometry, index or settlement basis'); continue; }
    if (!validBounds(f.sidePays) || !validBounds(f.timelyMoveAndSidePays)) { reject('invalid joint/settlement probability bounds'); continue; }
    const a = f.moveBy, b = f.sidePays, joint = f.timelyMoveAndSidePays, eps = 1e-12;
    if (joint.probability > Math.min(a.probability, b.probability) + eps || joint.probability < Math.max(0, a.probability + b.probability - 1) - eps ||
        joint.lower > Math.min(a.upper, b.upper) + eps || joint.upper < Math.max(0, a.lower + b.lower - 1) - eps) {
      reject('incoherent joint probabilities'); continue;
    }
    exact.push(f);
  }
  if (exact.length > 1) {
    // The validated ensemble/selector must produce one forecast, not cherry-pick the largest confidence here.
    out.rejected.push(...exact.map((f) => ({ id: f.id, reason: 'multiple exact forecasts require upstream validated aggregation' })));
    return out;
  }
  const f = exact[0];
  if (!f) { out.status = out.context.length ? 'context-only' : 'unavailable'; return out; }
  out.forecastId = f.id; out.modelId = f.modelId; out.calibrationRef = f.calibrationRef;
  out.moveBy = { ...f.moveBy }; out.sidePays = { ...f.sidePays }; out.timelyMoveAndSidePays = { ...f.timelyMoveAndSidePays };
  out.status = !f.calibrationRef?.trim() ? 'unvalidated'
    : f.moveBy.lower >= minimumMove && f.timelyMoveAndSidePays.lower >= minimum ? 'timing-supported' : 'insufficient-confidence';
  return out;
}
