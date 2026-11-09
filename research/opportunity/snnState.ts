/** A synchronous observer of the existing SNN. Never steps, scores, tags or trains it. */
import { createHash } from 'node:crypto';
import type { SnnNetwork } from '../../bot/snn/network';
import { stageFlags } from '../../bot/snn/params';

export const ATLAS_SNN_SCHEMA = 'opportunity-snn-state-v1';
export interface SnnProvenance {
  checkpointSha256: string; checkpointKnownAt: number; trainedThrough: number;
  inputSourceSha256: string;
  domain: 'crypto' | 'perps' | 'combined';
  /** Conservative lag for rounded legacy tape calls; zero for an exact observed clock. */
  inputLagMs?: number;
  /** Longer observed-input gaps clear transient state and pending labels in research replay. */
  maximumInputGapMs?: number;
  /** The source tape emitted a column only while its observed index price met this age limit. */
  maximumInputPriceAgeMs?: number;
  /** Latest arrival used by the caller's causal replay, including input and settlement messages. */
  inputKnownAt: number; basis: 'observed-tape' | 'forward-paper'; variant: 'S5' | 'S6';
}
export interface AtlasSnnState {
  schema: typeof ATLAS_SNN_SCHEMA; asOf: number; stateAt: number; version: string;
  provenance: SnnProvenance; flagsSha256: string;
  flags: Record<string, boolean>;
  components?: Array<{ domain: 'crypto' | 'perps'; version: string; flagsSha256: string; checkpointSha256: string; inputSourceSha256: string }>;
  columns: Array<{ key: string; asset: string; horizonSec: number; values: Record<string, number | null> }>;
}
const timestamp = (n: number) => Number.isSafeInteger(n) && n >= 0;
const finite = (n: number | null | undefined) => typeof n === 'number' && Number.isFinite(n) ? n : null;

export function validateSnnState(s: AtlasSnnState, asOf: number, maximumAgeMs = 2000) {
  const p = s.provenance;
  const flagsHash = createHash('sha256').update(JSON.stringify(s.flags)).digest('hex');
  if (!Number.isSafeInteger(maximumAgeMs) || maximumAgeMs < 0 || s.schema !== ATLAS_SNN_SCHEMA || !s.version || flagsHash !== s.flagsSha256 ||
      Object.values(s.flags).some((v) => typeof v !== 'boolean') || !/^[a-f0-9]{64}$/.test(p.inputSourceSha256) ||
      !['crypto', 'perps', 'combined'].includes(p.domain) ||
      !Number.isSafeInteger(p.inputLagMs ?? 0) || (p.inputLagMs ?? 0) < 0 || (p.inputLagMs ?? 0) > 60000 ||
      (p.maximumInputGapMs !== undefined && (!Number.isSafeInteger(p.maximumInputGapMs) || p.maximumInputGapMs < 1000 || p.maximumInputGapMs > 60000)) ||
      (p.maximumInputPriceAgeMs !== undefined && (!Number.isSafeInteger(p.maximumInputPriceAgeMs) || p.maximumInputPriceAgeMs < 1 || p.maximumInputPriceAgeMs > 60000)) ||
      !s.flags.lateral || !s.flags.pc || (p.variant === 'S6' ? !s.flags.plasticity || !s.flags.pcLearn : s.flags.plasticity || s.flags.pcLearn) ||
      !/^[a-f0-9]{64}$/.test(p.checkpointSha256) || !['S5', 'S6'].includes(p.variant) ||
      !['observed-tape', 'forward-paper'].includes(p.basis) ||
      ![s.asOf, s.stateAt, p.checkpointKnownAt, p.trainedThrough, p.inputKnownAt, asOf].every(timestamp) ||
      s.asOf !== asOf || s.stateAt > asOf || asOf - s.stateAt > maximumAgeMs ||
      Math.max(p.checkpointKnownAt, p.trainedThrough, p.inputKnownAt) > asOf ||
      !s.columns.length || s.columns.length > 64 || new Set(s.columns.map((c) => c.key)).size !== s.columns.length) throw new Error('unavailable, stale or noncausal SNN state');
  for (const c of s.columns) {
    if (p.maximumInputPriceAgeMs !== undefined && (![0, 1].includes(c.values.observed_input_available!) ||
        (c.values.observed_input_available === 0 && Object.entries(c.values).some(([k, v]) => k !== 'observed_input_available' && v !== null)))) throw new Error('missing observed SNN input must be explicitly masked');
    if (!/^[A-Za-z0-9_-]+$/.test(c.key) || !/^[A-Z]+$/.test(c.asset) || !(c.horizonSec > 0) || !Number.isFinite(c.horizonSec) ||
        Object.keys(c.values).length > 256 || Object.entries(c.values).some(([k, v]) => !/^[a-z0-9_]+$/.test(k) || (v !== null && !Number.isFinite(v)))) throw new Error('invalid SNN column');
    const domain = p.domain === 'combined' ? c.key.split('_')[0] : p.domain;
    if (!(domain === 'crypto' ? [900, 3600] : domain === 'perps' ? [3600, 14400] : []).includes(c.horizonSec)) throw new Error('SNN horizon is incompatible with declared domain');
  }
  if (p.domain === 'combined' && (!s.components || s.components.length !== 2 || new Set(s.components.map((c) => c.domain)).size !== 2 ||
      s.components.some((c) => !['crypto', 'perps'].includes(c.domain) || !c.version || [c.flagsSha256, c.checkpointSha256, c.inputSourceSha256].some((h) => !/^[a-f0-9]{64}$/.test(h))))) throw new Error('invalid combined SNN provenance');
}

/** Pool actual rates and predictive-coding latents, rather than the distance-gated contract
 * features (which erase pooled rates at d=0). Provenance is supplied by the recorder, never
 * inferred from a checkpoint's mtime. A later-trained checkpoint is invalid in an earlier replay. */
export function captureSnnState(net: SnnNetwork, asOf: number, provenance: SnnProvenance, availableKeys?: ReadonlySet<string>): AtlasSnnState {
  if (provenance.domain === 'combined') throw new Error('use combineSnnStates for the isolated network fleet');
  if (provenance.maximumInputPriceAgeMs !== undefined && !availableKeys) throw new Error('observed input availability is required for the declared price-age policy');
  const dirs = new Map(net.directions().map((d) => [d.key, d]));
  const columns = net.sortedColumns().filter((c) => c.kind === 'crypto').map((c) => {
    const values: Record<string, number | null> = {};
    const pool = (name: string, array: ArrayLike<number>, bins = 8) => {
      for (let b = 0; b < bins; b++) {
        const from = Math.floor(b * array.length / bins), to = Math.floor((b + 1) * array.length / bins);
        let sum = 0;
        for (let i = from; i < to; i++) sum += array[i];
        values[`${name}_${b}`] = to > from ? finite(sum / (to - from)) : null;
      }
    };
    pool('rate_l0', c.rate0); pool('rate_l1', c.rate1); pool('rate_l2', c.rate2);
    pool('latent_l1', c.z1); pool('latent_l2', c.z2); pool('prediction_error', c.err0);
    const d = dirs.get(c.key)!;
    Object.assign(values, { governor: finite(c.G), surprise: finite(c.surprise), error_z: finite(c.errZ),
      excitatory: finite(c.exc), inhibitory: finite(c.inh), saturation: finite(c.fSat),
      salience: finite(net.salience[c.key]), readout_p_up: finite(d.pUp), readout_move_bps: finite(d.expMove),
      readout_signed_bps: finite(d.expSignedMove), readout_skill: finite(d.skill), readout_calibration: finite(d.calConf),
      readout_contract_skill: finite(d.contractSkill), readout_labelled: finite(d.labelled) });
    if (provenance.maximumInputPriceAgeMs !== undefined) {
      const available = availableKeys!.has(c.key);
      if (!available) for (const key of Object.keys(values)) values[key] = null;
      values.observed_input_available = Number(available);
    }
    return { key: c.key, asset: c.asset, horizonSec: c.horizonSec, values };
  });
  const s: AtlasSnnState = { schema: ATLAS_SNN_SCHEMA, asOf, stateAt: net.lastTs, version: net.version,
    provenance: { ...provenance }, flags: { ...net.p.flags },
    flagsSha256: createHash('sha256').update(JSON.stringify(net.p.flags)).digest('hex'), columns };
  validateSnnState(s, asOf);
  return s;
}

/** Optional crypto + perps fleet context. Isolated domains cannot be silently swapped,
 * and a missing domain cannot stand in for a model trained with both. */
export function combineSnnStates(states: AtlasSnnState[]): AtlasSnnState {
  if (states.length !== 2 || states.some((s) => s.provenance.domain === 'combined') || new Set(states.map((s) => s.provenance.domain)).size !== 2) throw new Error('one crypto and one perps SNN state required');
  const ordered = [...states].sort((a, b) => a.provenance.domain.localeCompare(b.provenance.domain)), first = ordered[0];
  for (const s of ordered) { validateSnnState(s, first.asOf); if (s.provenance.variant !== first.provenance.variant || s.provenance.basis !== first.provenance.basis ||
    (s.provenance.inputLagMs ?? 0) !== (first.provenance.inputLagMs ?? 0) ||
    s.provenance.maximumInputGapMs !== first.provenance.maximumInputGapMs ||
    s.provenance.maximumInputPriceAgeMs !== first.provenance.maximumInputPriceAgeMs) throw new Error('incompatible SNN variants/bases/input clocks'); }
  const hash = (x: unknown) => createHash('sha256').update(JSON.stringify(x)).digest('hex');
  const components = ordered.map((s) => ({ domain: s.provenance.domain as 'crypto' | 'perps', version: s.version,
    flagsSha256: s.flagsSha256, checkpointSha256: s.provenance.checkpointSha256, inputSourceSha256: s.provenance.inputSourceSha256 }));
  const flags = { ...stageFlags(first.provenance.variant) };
  const combined: AtlasSnnState = { schema: ATLAS_SNN_SCHEMA, asOf: first.asOf, stateAt: Math.min(...ordered.map((s) => s.stateAt)),
    version: hash(components.map((c) => [c.domain, c.version, c.flagsSha256])), flags, flagsSha256: hash(flags), components,
    provenance: { domain: 'combined', variant: first.provenance.variant, basis: first.provenance.basis,
      checkpointSha256: hash(components.map((c) => c.checkpointSha256)), inputSourceSha256: hash(components.map((c) => c.inputSourceSha256)),
      checkpointKnownAt: Math.max(...ordered.map((s) => s.provenance.checkpointKnownAt)),
      inputLagMs: Math.max(...ordered.map((s) => s.provenance.inputLagMs ?? 0)),
      ...(first.provenance.maximumInputGapMs !== undefined ? { maximumInputGapMs: first.provenance.maximumInputGapMs } : {}),
      ...(first.provenance.maximumInputPriceAgeMs !== undefined ? { maximumInputPriceAgeMs: first.provenance.maximumInputPriceAgeMs } : {}),
      trainedThrough: Math.max(...ordered.map((s) => s.provenance.trainedThrough)), inputKnownAt: Math.max(...ordered.map((s) => s.provenance.inputKnownAt)) },
    columns: ordered.flatMap((s) => s.columns.map((c) => ({ ...c, key: `${s.provenance.domain}_${c.key}`, values: { ...c.values } }))) };
  validateSnnState(combined, combined.asOf); return combined;
}

/** State identity remains metadata; hashes, raw timestamps and model versions are not inputs. */
export function encodeSnnState(s: AtlasSnnState | null, asOf: number): Record<string, number> {
  if (!s) return { 'snn:available': 0 };
  validateSnnState(s, asOf);
  const values: Record<string, number> = { 'snn:available': 1, 'snn:age_sec': (asOf - s.stateAt) / 1000 };
  for (const c of s.columns) for (const [k, v] of Object.entries(c.values)) {
    values[`snn:${c.key}:${k}`] = v ?? NaN;
    values[`snn:${c.key}:missing_${k}`] = v === null ? 1 : 0;
  }
  return values;
}
