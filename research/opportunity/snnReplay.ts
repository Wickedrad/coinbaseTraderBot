/** Optional offline adapter for the repository's existing observed-input SNN tapes. */
import { SnnNetwork, type ColumnInput } from '../../bot/snn/network';
import { DEFAULT_SNN, stageFlags, type SnnParams } from '../../bot/snn/params';
import { readTape, TAPE_OP } from '../snnTape';
import { FROZEN_TRAIN_BEFORE } from './jointPathData';
import { captureSnnState, type AtlasSnnState } from './snnState';
import { digest, stamp } from './contractDataset';
import { studyPolicy } from './studyPolicy';

/** S5 and S6 consume identical inputs. New observations are applied at their timestamp,
 * never smeared into earlier seconds by SnnNetwork.step's normal catch-up behavior.
 * This adapter owns a separate research network, not the running bot's network. */
export function replayAtlasSnnTape(file: string, options: { variant: 'S5' | 'S6'; sourceSha256: string;
  studyPolicyId?: string;
  domain?: 'crypto' | 'perps'; inputLagMs?: number;
  maximumInputGapMs?: number;
  /** Requires a source tape built with this observed-price age limit. */
  maximumInputPriceAgeMs?: number;
  learningBefore?: number; everyMs?: number; params?: SnnParams; onState: (state: AtlasSnnState) => void }) {
  const policy = studyPolicy(options.studyPolicyId), learningBefore = options.learningBefore ?? policy.trainBefore, every = options.everyMs ?? 60000, inputLagMs = options.inputLagMs ?? 1000;
  const maximumInputGapMs = options.maximumInputGapMs ?? 3000;
  const maximumInputPriceAgeMs = options.maximumInputPriceAgeMs;
  if (!stamp(learningBefore) || learningBefore > policy.trainBefore || !Number.isSafeInteger(every) || every < 1000 || every % 1000 ||
      !/^[a-f0-9]{64}$/.test(options.sourceSha256) || !['S5', 'S6'].includes(options.variant) ||
      !Number.isSafeInteger(inputLagMs) || inputLagMs < 0 || inputLagMs > 60000 || inputLagMs % 1000 ||
      !Number.isSafeInteger(maximumInputGapMs) || maximumInputGapMs < 1000 || maximumInputGapMs > 60000 ||
      (maximumInputPriceAgeMs !== undefined && (!Number.isSafeInteger(maximumInputPriceAgeMs) || maximumInputPriceAgeMs < 1 || maximumInputPriceAgeMs > 60000))) throw new Error('invalid SNN tape replay policy');
  const params = { ...(options.params ?? DEFAULT_SNN), flags: { ...(options.params ?? DEFAULT_SNN).flags, ...stageFlags(options.variant) } };
  const net = new SnnNetwork(params), initialSha = digest(net.serialize());
  let firstAt = 0, lastAt = 0, learnedThrough = 0, previousStep = 0, snapshots = 0, gaps = 0, nextSnapshot = 0, gapResets = 0, awaitingInput = false, unavailableSnapshots = 0;
  let availableKeys = new Set<string>(), unavailableKeys = new Set<string>(), unavailableColumnResets = 0;
  const sourceMissing = () => maximumInputPriceAgeMs !== undefined && (!availableKeys.size || unavailableKeys.size > 0);
  function advance(at: number, inputs: ColumnInput[]) {
    if (!stamp(at) || at < lastAt) throw new Error('unordered tape arrival time');
    if (!firstAt) firstAt = at;
    if (sourceMissing()) net.pauseLearning = true;
    // First freeze at the boundary using only inputs already observed. No future settlements are fed back.
    if (net.lastTs && net.lastTs < learningBefore && at >= learningBefore) {
      if (learningBefore - 1000 > net.lastTs) net.step(learningBefore - 1000, []);
      if (!net.pauseLearning) learnedThrough = Math.max(learnedThrough, Math.min(net.lastTs, learningBefore - 1));
    }
    net.pauseLearning = at >= learningBefore || sourceMissing();
    const second = Math.floor(at / 1000) * 1000;
    if (net.lastTs && second - net.lastTs > 1000) { net.step(second - 1000, []); gaps++; }
    net.step(at, inputs);
    if (!net.pauseLearning) learnedThrough = Math.max(learnedThrough, at);
    lastAt = at;
  }
  for (const op of readTape(file)) {
    // Legacy step/score T is floor(recorded arrival / 1s), whereas settlement now
    // retains milliseconds. Put settlements in the same conservative arrival bucket,
    // so a settlement within a rounded step's second cannot rewind the network.
    const at = op.op === TAPE_OP.SETTLE
      ? Math.max(op.now, Math.floor(op.now / 1000) * 1000 + inputLagMs) : op.T + inputLagMs;
    if (at < lastAt) throw new Error('late tape operation requires an arrival-time replay, not a market-time rewind');
    if (previousStep && at - previousStep > maximumInputGapMs && !awaitingInput) {
      // Keep learned weights, but clear transient state, held inputs and pending
      // direction/contract tags. A missing interval cannot supply a horizon label.
      net.rewind(); awaitingInput = true; gapResets++;
    }
    if (op.op === TAPE_OP.STEP) {
      if (at <= previousStep) throw new Error('duplicate or reversed SNN step');
      let inputs = op.inputs;
      if (maximumInputPriceAgeMs !== undefined) {
        availableKeys = new Set(inputs.filter((i) => Number.isFinite(i.price) && i.price! > 0).map((i) => i.key));
        const missing = new Set([...net.columns.keys()].filter((key) => !availableKeys.has(key)));
        for (const c of net.sortedColumns()) if (missing.has(c.key) || unavailableKeys.has(c.key)) {
          if (missing.has(c.key) && !unavailableKeys.has(c.key)) unavailableColumnResets++;
          c.resetTransient(); net.dirTags.set(c.key, []);
          net.readouts.get(c.key)?.tags.clear(); net.dirReadouts.get(c.key)?.tags.clear();
        }
        unavailableKeys = missing;
        inputs = [...inputs.filter((i) => availableKeys.has(i.key)), ...[...missing].map((key) => ({ key,
          asset: net.columns.get(key)!.asset, price: undefined, mid: undefined, values: {} }))];
      }
      awaitingInput = false; advance(at, inputs); previousStep = at;
      if (at >= nextSnapshot) {
        // Native tapes can begin with a book event before any index/asset input.
        // Advance that observed clock, but do not invent an initialized SNN state.
        if (!net.columns.size || (maximumInputPriceAgeMs !== undefined && !availableKeys.size)) { unavailableSnapshots++; continue; }
        const state = captureSnnState(net, at, { checkpointSha256: initialSha, checkpointKnownAt: firstAt,
          inputSourceSha256: options.sourceSha256, domain: options.domain ?? 'crypto', inputLagMs, maximumInputGapMs,
          ...(maximumInputPriceAgeMs !== undefined ? { maximumInputPriceAgeMs } : {}),
          trainedThrough: learnedThrough, inputKnownAt: at, variant: options.variant, basis: 'observed-tape' },
          maximumInputPriceAgeMs !== undefined ? availableKeys : undefined);
        options.onState(state); snapshots++; nextSnapshot = at + every;
      }
    } else {
      if (awaitingInput) { lastAt = at; continue; }
      if (maximumInputPriceAgeMs === undefined) advance(at, []);
      else { net.pauseLearning = at >= learningBefore || sourceMissing(); lastAt = at; }
      if (op.op === TAPE_OP.SCORE) net.score(op.queries, at);
      else if (op.label !== undefined) { net.settle(op.ticker, op.label ? 'yes' : 'no', at); if (!net.pauseLearning) learnedThrough = Math.max(learnedThrough, at); }
    }
  }
  return { variant: options.variant, studyPolicyId: policy.id, domain: options.domain ?? 'crypto', inputLagMs, maximumInputGapMs, maximumInputPriceAgeMs,
    sourceSha256: options.sourceSha256, firstAt, lastAt, learnedThrough, snapshots, unavailableSnapshots, unavailableColumnResets, gaps, gapResets,
    version: net.version, checkpointSha256: digest(net.serialize()),
    semantics: 'Observed input calls with bounded holds; longer gaps clear transients, inputs and pending labels while preserving weights; no invented ticks; learning frozen at declared cutoff' };
}
