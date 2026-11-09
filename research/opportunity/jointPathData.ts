/** Audited dataset reader and purged risk-set construction. No model or trading imports. */
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { createHash } from 'node:crypto';
import { ATLAS_FEATURE_SCHEMA, type AtlasFeatureFrame } from './features';
import { DECISION_DATASET_SCHEMA, DECISION_PATH_SCHEMA, type DecisionObservation } from './decisionDataset';
import { PATH_LABEL_SCHEMA, pathPartition } from './pathLabels';
import { TANET_SCHEMA } from '../../bot/ta/taNet';
import { studyPolicy } from './studyPolicy';

export const FROZEN_TRAIN_BEFORE = Date.parse('2025-01-01'), FROZEN_FINAL_FROM = Date.parse('2026-01-01');
const MIN = 60000;
export const PATH_ASSETS = ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE'];
export type FirstCause = 'none' | 'target' | 'stop' | 'ambiguous';
export interface PathDecision {
  id: string; at: number; asset: string; values: Record<string, number>; engine: string;
  inputSha256: string; price: number; atrBps: number | null; anchorDefinition: string;
}
export interface PathObservation {
  decisionId: string; at: number; asset: string; side: 'long' | 'short'; targetAtr: number; stopAtr: number;
  horizonMin: number; observedMinutes: number; cause: FirstCause; hitMinute: number | null;
  plannedThrough: number; knownAt: number; censored: boolean;
}
export interface JointPathDataset {
  studyPolicyId?: string;
  decisions: Map<string, PathDecision>; paths: PathObservation[];
  manifestSha256: string; runId: string; trainBefore: number; finalFrom: number; maxHorizonMin: number;
  inputHashes: Record<string, string>;
  counts: { decisions: number; reserved: number; paths: number; eligiblePaths: number };
}
export async function sha256File(file: string) {
  const h = createHash('sha256'); for await (const c of fs.createReadStream(file)) h.update(c); return h.digest('hex');
}
const stamp = (x: number) => Number.isSafeInteger(x) && x >= 0;

/** Numeric inputs only: IDs, source hashes, raw timestamps and label fields are never encoded. */
export function encodePathFrame(frame: AtlasFeatureFrame, allowArrivalTimeSnapshot = false): Record<string, number> {
  if (frame.schema !== ATLAS_FEATURE_SCHEMA || frame.taSchema !== TANET_SCHEMA || !stamp(frame.decisionAt) || (!allowArrivalTimeSnapshot && frame.decisionAt % MIN) || !PATH_ASSETS.includes(frame.asset) || !['talib', 'builtin'].includes(frame.engine)) throw new Error('incompatible path feature frame');
  const out: Record<string, number> = {};
  for (const asset of PATH_ASSETS) out[`asset:${asset}`] = frame.asset === asset ? 1 : 0;
  let n = 0;
  for (const [name, group] of Object.entries(frame.groups)) {
    if (!/^[a-z0-9_]+$/.test(name) || typeof group.source !== 'string' || !group.source || !['ready', 'warming', 'missing', 'stale'].includes(group.status) ||
        (group.knownAt !== null && (!stamp(group.knownAt) || group.knownAt > frame.decisionAt))) throw new Error('noncausal path feature group');
    for (const status of ['ready', 'warming', 'missing', 'stale']) out[`status:${name}:${status}`] = group.status === status ? 1 : 0;
    out[`age:${name}`] = group.knownAt === null ? NaN : Math.log1p((frame.decisionAt - group.knownAt) / 1000);
    for (const [key, value] of Object.entries(group.values)) {
      if (!/^[a-zA-Z0-9_]+$/.test(key) || (value !== null && (typeof value !== 'number' || !Number.isFinite(value))) ||
          (['missing', 'stale'].includes(group.status) && value !== null) || ++n > 4096) throw new Error('invalid path feature value');
      out[`value:${name}:${key}`] = value ?? NaN;
      out[`missing:${name}:${key}`] = value === null ? 1 : 0;
    }
  }
  return out;
}
async function* jsonLines(file: string) {
  const input = fs.createReadStream(file), reader = readline.createInterface({ input, crlfDelay: Infinity });
  try { for await (const line of reader) { if (line.length > 2 * 1024 * 1024) throw new Error('dataset JSONL line exceeds limit'); if (line.trim()) yield JSON.parse(line); } }
  finally { reader.close(); input.destroy(); }
}
export async function loadJointPathDataset(dir: string, limits: { studyPolicyId?: string; maxHorizonMin?: number; maxDecisions?: number; maxPaths?: number } = {}): Promise<JointPathDataset> {
  const root = fs.realpathSync(dir), mf = path.join(root, 'manifest.json'), manifestSha256 = await sha256File(mf);
  const m = JSON.parse(fs.readFileSync(mf, 'utf8'));
  const maxHorizonMin = limits.maxHorizonMin ?? 60, maxDecisions = limits.maxDecisions ?? 20000, maxPaths = limits.maxPaths ?? 500000;
  if (![maxHorizonMin, maxDecisions, maxPaths].every((n) => Number.isSafeInteger(n) && n > 0) || maxHorizonMin > 1440 ||
      m.schema !== DECISION_DATASET_SCHEMA || m.researchOnly !== true || m.partitions?.finalOutcomesWithheld !== true ||
      !stamp(m.partitions.trainBefore) || !stamp(m.partitions.finalFrom) || m.partitions.trainBefore >= m.partitions.finalFrom || !m.runId) throw new Error('invalid joint dataset/limits');
  const policy = studyPolicy(limits.studyPolicyId);
  if (studyPolicy(m.studyPolicyId).id !== policy.id) throw new Error('dataset/study registration mismatch');
  const trainBefore = Math.min(m.partitions.trainBefore, policy.trainBefore), finalFrom = Math.min(m.partitions.finalFrom, policy.finalFrom);
  const hashes = new Map<string, string>();
  for (const [stream, name] of [['decisions', 'decisions.jsonl'], ['paths', 'paths.jsonl']]) {
    const record = m.outputs?.[stream], file = path.join(root, name);
    if (record?.file !== name || !/^[a-f0-9]{64}$/.test(record.sha256) || !fs.realpathSync(file).startsWith(root + path.sep) || await sha256File(file) !== record.sha256) throw new Error(`dataset hash/path mismatch: ${name}`);
    hashes.set(file, record.sha256);
  }
  const decisions = new Map<string, PathDecision>(), headers = new Map<string, { at: number; expected: number; found: number; reserved: boolean; horizons: readonly number[] }>();
  const counts = { decisions: 0, reserved: 0, paths: 0, eligiblePaths: 0 };
  const decisionTimes = new Set<string>();
  let valueDefaults: Readonly<Record<string, number>> | undefined;
  let engine: string | undefined, anchorDefinition: string | undefined;
  let first = true;
  for await (const row of jsonLines(path.join(root, 'decisions.jsonl'))) {
    if (first) { first = false; if (row.type !== 'metadata' || row.schema !== DECISION_DATASET_SCHEMA || row.stream !== 'decisions' || row.runId !== m.runId) throw new Error('decision stream metadata mismatch'); continue; }
    if (++counts.decisions > maxDecisions) throw new Error('joint dataset decision limit exceeded');
    const d = row as DecisionObservation, at = d.frame?.decisionAt, src = d.frame?.groups?.spot_1m;
    if (d.type !== 'decision' || d.schema !== DECISION_DATASET_SCHEMA || !stamp(at) || at % MIN || !src || !/^[a-f0-9]{64}$/.test(src.sha256 ?? '') || !PATH_ASSETS.includes(d.frame.asset) ||
        d.decisionId !== createHash('sha256').update(JSON.stringify([src.source, src.sha256, d.frame.asset, at])).digest('hex') || headers.has(d.decisionId) || !d.horizonsMin?.length ||
        d.horizonsMin.some((h, i) => !Number.isSafeInteger(h) || h < 1 || h > 1440 || (i > 0 && h <= d.horizonsMin[i - 1])) || decisionTimes.has(`${d.frame.asset}:${at}`)) throw new Error('invalid/duplicate decision row');
    decisionTimes.add(`${d.frame.asset}:${at}`);
    const reserved = at >= finalFrom;
    if (!['scheduled', 'unavailable-scale', 'reserved-final'].includes(d.labelStatus) || (reserved && d.labelStatus !== 'reserved-final')) throw new Error('final decision was not reserved');
    const expected = d.labelStatus === 'scheduled' ? d.horizonsMin.length * 2 * m.labelPolicy.targetsAtr.length * m.labelPolicy.stopsAtr.length : 0;
    headers.set(d.decisionId, { at, expected, found: 0, reserved, horizons: d.horizonsMin });
    if (reserved || at >= trainBefore) { counts.reserved++; continue; } // never encode final/development values
    const a = d.anchor;
    if (!a || a.knownAt !== at || !(a.price > 0) || !Number.isFinite(a.price) || a.definition !== m.labelPolicy.anchor ||
        (a.atrBps !== null && (!Number.isFinite(a.atrBps) || a.atrBps <= 0))) throw new Error('invalid decision anchor');
    engine ??= d.frame.engine; anchorDefinition ??= a.definition;
    if (engine !== d.frame.engine || anchorDefinition !== a.definition) throw new Error('mixed feature engines or anchor definitions');
    const encoded = encodePathFrame(d.frame);
    if (valueDefaults && (Object.keys(encoded).length !== Object.keys(valueDefaults).length || Object.keys(encoded).some((key) => !Object.hasOwn(valueDefaults!, key)))) throw new Error('inconsistent feature vocabulary within one schema');
    valueDefaults ??= Object.freeze({ ...encoded });
    const values: Record<string, number> = Object.create(valueDefaults);
    // Intern common missing/constant inputs; at-risk rows share each decision's values.
    for (const [key, value] of Object.entries(encoded)) if (!Object.is(value, valueDefaults[key])) Object.defineProperty(values, key, { value, enumerable: true });
    decisions.set(d.decisionId, { id: d.decisionId, at, asset: d.frame.asset, values, engine,
      price: a.price, atrBps: a.atrBps, anchorDefinition, inputSha256: src.sha256! });
  }
  if (first) throw new Error('missing decision stream metadata');
  const paths: PathObservation[] = [], unique = new Set<string>(); first = true;
  for await (const r of jsonLines(path.join(root, 'paths.jsonl'))) {
    if (first) { first = false; if (r.type !== 'metadata' || r.stream !== 'paths' || r.runId !== m.runId || r.labelsSchema !== DECISION_PATH_SCHEMA) throw new Error('path stream metadata mismatch'); continue; }
    if (++counts.paths > maxPaths) throw new Error('joint dataset path limit exceeded');
    const e = r.entry, p = r.provenance, head = headers.get(e?.decisionId), d = decisions.get(e?.decisionId);
    if (!head || head.reserved || r.type !== 'path-label' || r.schema !== DECISION_PATH_SCHEMA || r.labelDefinitionSchema !== PATH_LABEL_SCHEMA || !p ||
        p.priceBasis !== 'observed-one-minute-ohlc' || e.ts !== head.at || !head.horizons.includes(r.horizonMin) || !['long', 'short'].includes(r.side) ||
        !m.labelPolicy.targetsAtr.includes(r.targetAtr) || !m.labelPolicy.stopsAtr.includes(r.stopAtr) ||
        !Number.isInteger(r.observedMinutes) || r.observedMinutes < 0 || r.observedMinutes > r.horizonMin ||
        ![null, 'gap', 'end-of-input', 'processing-limit'].includes(r.censorReason) || (r.censorReason === null && r.observedMinutes !== r.horizonMin) || !['none', 'target', 'stop', 'ambiguous'].includes(r.firstHit) ||
        (r.firstHit === 'none' ? r.firstHitMinute !== null : !Number.isInteger(r.firstHitMinute) || r.firstHitMinute < 1 || r.firstHitMinute > r.observedMinutes) ||
        p.futureStartsAt !== e.ts || p.plannedThrough !== e.ts + r.horizonMin * MIN || p.observedThrough !== e.ts + r.observedMinutes * MIN ||
        !stamp(p.labelKnownAt) || p.labelKnownAt < p.observedThrough || p.observedThrough > finalFrom || p.labelKnownAt > finalFrom ||
        r.partition !== pathPartition(e.ts, Math.max(p.plannedThrough, p.labelKnownAt), m.partitions)) throw new Error('invalid, orphaned or final path row');
    const key = JSON.stringify([e.decisionId, r.side, r.targetAtr, r.stopAtr, r.horizonMin]);
    if (unique.has(key)) throw new Error('duplicate path label'); unique.add(key); head.found++;
    if (!d || r.partition !== 'train' || r.horizonMin > maxHorizonMin || p.labelKnownAt > trainBefore || p.plannedThrough > trainBefore) continue;
    if (e.asset !== d.asset || e.price !== d.price || e.inputSha256 !== d.inputSha256 || e.f?.knownAt !== d.at || e.f.atrBps !== d.atrBps || e.anchorDefinition !== d.anchorDefinition) throw new Error('decision/path join mismatch');
    paths.push({ decisionId: e.decisionId, at: e.ts, asset: e.asset, side: r.side, targetAtr: r.targetAtr, stopAtr: r.stopAtr,
      horizonMin: r.horizonMin, observedMinutes: r.observedMinutes, cause: r.firstHit, hitMinute: r.firstHitMinute,
      plannedThrough: p.plannedThrough, knownAt: p.labelKnownAt, censored: r.censorReason !== null });
  }
  if (first) throw new Error('missing path stream metadata');
  if (counts.decisions !== m.outputs.decisions.rows || counts.paths !== m.outputs.paths.rows || [...headers.values()].some((h) => h.expected !== h.found)) throw new Error('incomplete dataset stream or joins');
  if (await sha256File(mf) !== manifestSha256) throw new Error('manifest changed during joint read');
  for (const [file, hash] of hashes) if (await sha256File(file) !== hash) throw new Error('dataset changed during joint read');
  counts.eligiblePaths = paths.length;
  return { studyPolicyId: policy.id, decisions, paths, manifestSha256, runId: m.runId, trainBefore, finalFrom, maxHorizonMin, counts,
    inputHashes: { 'manifest.json': manifestSha256, ...Object.fromEntries([...hashes].map(([file, hash]) => [path.basename(file), hash])) } };
}

export interface TimeWindow { from: number; through: number }
export function selectPathEpisodes(data: JointPathDataset, window: TimeWindow, completeOnly = false): PathObservation[] {
  const selected = new Map<string, PathObservation>();
  for (const p of data.paths) {
    if (p.at < window.from || p.at >= window.through || Math.max(p.plannedThrough, p.knownAt) > window.through || (completeOnly && p.censored)) continue;
    const key = JSON.stringify([p.decisionId, p.side, p.targetAtr, p.stopAtr]), old = selected.get(key);
    if (!old || p.horizonMin > old.horizonMin) selected.set(key, p); // schedule-based; never select by label value
  }
  // Provenance hashes/IDs may change with future file revisions; they must not order training rows.
  return [...selected.values()].sort((a, b) => a.at - b.at || a.asset.localeCompare(b.asset) || a.side.localeCompare(b.side) || a.targetAtr - b.targetAtr || a.stopAtr - b.stopAtr);
}
export interface RiskRow { decisionId: string; values: Record<string, number>; query: Record<string, number>; minute: number; cause: FirstCause; weight: number }
export const riskValue = (r: RiskRow, name: string) => r.query[name] ?? r.values[name] ?? NaN;
export function pathQueryValues(p: Pick<PathObservation, 'side' | 'targetAtr' | 'stopAtr'>, minute: number) {
  return { 'query:side': p.side === 'long' ? 1 : -1, 'query:target': Math.log(p.targetAtr), 'query:stop': Math.log(p.stopAtr), 'query:minute': Math.log1p(minute) };
}
export function riskRows(data: JointPathDataset, episodes: PathObservation[], maxRows = 200000): RiskRow[] {
  const multiplicity = new Map<string, number>();
  for (const p of episodes) multiplicity.set(p.decisionId, (multiplicity.get(p.decisionId) ?? 0) + 1);
  const rows: RiskRow[] = [];
  for (const p of episodes) {
    const d = data.decisions.get(p.decisionId)!;
    const through = p.hitMinute ?? p.observedMinutes;
    for (let minute = 1; minute <= through; minute++) {
      if (rows.length >= maxRows) throw new Error('risk-row limit exceeded');
      rows.push({ decisionId: p.decisionId, values: d.values, query: pathQueryValues(p, minute), minute,
        cause: p.hitMinute === minute ? p.cause : 'none', weight: 1 / multiplicity.get(p.decisionId)! });
    }
  }
  return rows;
}
