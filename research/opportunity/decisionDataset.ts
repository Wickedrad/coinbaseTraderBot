/** Joined causal decision/target streams. Does not fit, score, promote or trade. */
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildFeatureReport, hashFile, type FeatureRunOptions } from './featuresCli';
import type { AtlasFeatureFrame, MinuteEntryAnchor } from './features';
import { defaultPathConfig, PathLabeler, type PathEntry, type PathLabel, type PathLabelConfig } from './pathLabels';
import { studyPolicy } from './studyPolicy';

export const DECISION_DATASET_SCHEMA = 'opportunity-decisions-v1';
export const DECISION_PATH_SCHEMA = 'opportunity-decision-paths-v1';
const MIN = 60000;
export interface ReferenceWindow { nominalMinutes: number; openTime: number; closeTime: number; remainingMinutes: number }
/** Study sampling clocks only: no ticker, strike, index or official settlement is invented. */
export function referenceWindows(asOf: number, periods: number[] = [15, 60]): ReferenceWindow[] {
  if (!Number.isSafeInteger(asOf) || asOf < 0 || asOf % MIN !== 0 || new Set(periods).size !== periods.length || periods.some((p) => !Number.isSafeInteger(p) || p < 1 || p > 1440)) throw new Error('invalid reference clock');
  return periods.map((nominalMinutes) => {
    const span = nominalMinutes * MIN, openTime = Math.floor(asOf / span) * span, closeTime = openTime + span;
    return { nominalMinutes, openTime, closeTime, remainingMinutes: (closeTime - asOf) / MIN };
  });
}
export interface DecisionPathEntry extends PathEntry {
  decisionId: string; inputSha256: string; anchorDefinition: MinuteEntryAnchor['definition'];
}
export interface DecisionObservation {
  type: 'decision'; schema: typeof DECISION_DATASET_SCHEMA; decisionId: string;
  frame: AtlasFeatureFrame; anchor: Readonly<MinuteEntryAnchor>; referenceWindows: ReadonlyArray<Readonly<ReferenceWindow>>;
  horizonsMin: readonly number[];
  labelStatus: 'scheduled' | 'unavailable-scale' | 'reserved-final';
}
export interface DecisionDatasetOptions extends Pick<FeatureRunOptions, 'archiveDir' | 'assets' | 'source' | 'maxMinutes' | 'dailyLagMs' | 'dailyMaxAgeMs' | 'onProgress'> {
  studyPolicyId?: string;
  everyMinutes?: number; trainBefore?: number; finalFrom?: number;
  referencePeriodsMin?: number[];
  path?: Partial<Pick<PathLabelConfig, 'horizonsMin' | 'targetsAtr' | 'stopsAtr' | 'reversals' | 'costs'>>;
  onDecision?: (decision: DecisionObservation) => void | Promise<void>;
  onLabels?: (rows: PathLabel<DecisionPathEntry>[]) => void | Promise<void>;
}
export async function buildDecisionDataset(o: DecisionDatasetOptions) {
  const policy = studyPolicy(o.studyPolicyId), trainBefore = o.trainBefore ?? policy.trainBefore, finalFrom = o.finalFrom ?? policy.finalFrom;
  if (trainBefore > policy.trainBefore || finalFrom > policy.finalFrom) throw new Error('decision partitions exceed registered study policy');
  const periods = [...(o.referencePeriodsMin ?? [15, 60])];
  referenceWindows(0, periods); // validate before callbacks or output
  const defaults = defaultPathConfig('validate', trainBefore, finalFrom);
  const override = structuredClone(o.path ?? {}), baseHorizons = override.horizonsMin ?? [5, 15, 60, 240, 1440];
  const maxHorizon = Math.max(...baseHorizons, ...periods);
  const pathConfig: PathLabelConfig = { ...defaults, targetsAtr: [1], stopsAtr: [1], ...override,
    horizonsMin: [...new Set([...baseHorizons, maxHorizon])].sort((a, b) => a - b) };
  if (!baseHorizons.length || baseHorizons.some((h, i) => !Number.isSafeInteger(h) || h < 1 || h > 1440 || (i > 0 && h <= baseHorizons[i - 1]))) throw new Error('base horizons must be increasing integer minutes');
  new PathLabeler<DecisionPathEntry>(pathConfig);
  const root = fileURLToPath(new URL('../../', import.meta.url));
  const codeHashes: Record<string, string> = {};
  for (const name of ['research/opportunity/decisionDataset.ts', 'research/opportunity/decisionDatasetCli.ts', 'research/opportunity/pathLabels.ts', 'research/opportunity/studyPolicy.ts']) codeHashes[name] = await hashFile(path.join(root, name));
  const assets: Array<{ asset: string; decisions: number; scheduled: number; unavailableScale: number; reservedFinal: number;
    labels: number; censored: number; partitions: Record<'train' | 'development' | 'final' | 'purged', number> }> = [];
  let labeler: PathLabeler<DecisionPathEntry> | undefined;
  let stats: typeof assets[number];
  const emit = async (rows: PathLabel<DecisionPathEntry>[]) => {
    for (const row of rows) { stats.labels++; stats.partitions[row.partition]++; if (row.censorReason) stats.censored++; }
    if (rows.length) await o.onLabels?.(rows);
  };
  const source = o.source ?? 'binance-1m';
  const replay = await buildFeatureReport({ archiveDir: o.archiveDir, assets: [...o.assets], source, everyMinutes: o.everyMinutes ?? 1,
    maxMinutes: o.maxMinutes, dailyLagMs: o.dailyLagMs, dailyMaxAgeMs: o.dailyMaxAgeMs, onProgress: o.onProgress,
    onAssetStart(asset) {
      stats = { asset, decisions: 0, scheduled: 0, unavailableScale: 0, reservedFinal: 0, labels: 0, censored: 0,
        partitions: { train: 0, development: 0, final: 0, purged: 0 } };
      assets.push(stats);
      labeler = new PathLabeler<DecisionPathEntry>({ ...pathConfig, source: `${source}/${asset}/1m.csv` });
    },
    async onStep(bar, frame, anchor) {
      // Stop labels BEFORE the first held-out candle is consumed. Features can still be audited.
      if (bar.ts + MIN > finalFrom && labeler) { await emit(labeler.finish('processing-limit', finalFrom)); labeler = undefined; }
      let entry: DecisionPathEntry | undefined, horizons: number[] | undefined;
      if (frame && anchor) {
        const source = frame.groups.spot_1m;
        const decisionId = createHash('sha256').update(JSON.stringify([source.source, source.sha256, frame.asset, frame.decisionAt])).digest('hex');
        const clocks = referenceWindows(frame.decisionAt, periods);
        horizons = [...new Set([...baseHorizons, ...clocks.map((c) => c.remainingMinutes)])].sort((a, b) => a - b);
        const reserved = frame.decisionAt >= finalFrom;
        const scaleAvailable = anchor.atrBps !== null && anchor.atrBps > 0 &&
          Math.max(...pathConfig.targetsAtr, ...pathConfig.stopsAtr) * anchor.atrBps < 10000;
        const labelStatus = reserved ? 'reserved-final' : scaleAvailable ? 'scheduled' : 'unavailable-scale';
        stats.decisions++;
        if (reserved) stats.reservedFinal++; else if (scaleAvailable) stats.scheduled++; else stats.unavailableScale++;
        const observation: DecisionObservation = Object.freeze({ type: 'decision', schema: DECISION_DATASET_SCHEMA, decisionId, frame, anchor,
          referenceWindows: Object.freeze(clocks.map((c) => Object.freeze(c))), horizonsMin: Object.freeze([...horizons]), labelStatus });
        await o.onDecision?.(observation);
        if (labelStatus === 'scheduled') entry = { ts: frame.decisionAt, asset: frame.asset, price: anchor.price,
          f: { atrBps: anchor.atrBps!, knownAt: anchor.knownAt }, decisionId, inputSha256: source.sha256!, anchorDefinition: anchor.definition };
      }
      if (labeler) await emit(labeler.push(bar, entry, entry ? horizons : undefined));
    },
    async onAssetEnd(_asset, limited) { if (labeler) await emit(labeler.finish(limited ? 'processing-limit' : 'end-of-input')); labeler = undefined; },
  });
  for (const [name, digest] of Object.entries(codeHashes)) if (await hashFile(path.join(root, name)) !== digest) throw new Error(`Code changed during dataset run: ${name}`);
  return { schema: DECISION_DATASET_SCHEMA, studyPolicyId: policy.id, createdAt: new Date().toISOString(), researchOnly: true, autoPromote: false, liveEntryAllowed: false,
    purpose: 'minute decision features joined to observed spot-path targets; no fitting, scoring or official contract settlement labels',
    partitions: { trainBefore, finalFrom, finalOutcomesWithheld: true },
    labelPolicy: { ...pathConfig, source: 'per-asset audited input path', baseHorizonsMin: baseHorizons, referencePeriodsMin: periods,
      anchor: 'builtin-ATR14-over-last-1440-contiguous-1m-bars', finalBoundaryCensorReason: 'processing-limit' },
    unavailableInputs: ['SNN temporal state', 'official settlement index/contract terms', 'funding/open interest', 'cross-asset lead-lag'],
    codeHashes, featureInputAudit: replay, assets };
}
