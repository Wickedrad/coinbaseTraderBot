// Rows for the project trial registry (meta plan thread; gdrive:kalshi-bot-archive/registry/shards/perp-ta/<run>.jsonl;
// schema: research/registry.py "registry trial row v1"). One row per trial; the sweep's own record (funnel, N_raw, the
// group's statistics) is kept verbatim under raw. trial_id = registry.py make_id: sha1 of Python's json.dumps of
// [thread, family, arm, code_sha, sorted days, seed, sorted phases, env] with sort_keys, first 16 hex digits.

import crypto from 'crypto';

export const REG_THREAD = 'perp-ta';
export const REG_FAMILY = 'perp-ta-rulebook';

/** Python's json.dumps(x, sort_keys=True) with the default separators and ensure_ascii, for strings, finite numbers,
 *  null, booleans, arrays and plain objects. */
export function pyDumps(x: unknown): string {
  if (x === null || x === undefined) return 'null';
  if (typeof x === 'boolean') return x ? 'true' : 'false';
  if (typeof x === 'number') {
    // Integers only: Python and JS print some floats differently (1e-07 / 1e-7), and make_id keys hold none.
    if (!Number.isInteger(x)) throw new Error('pyDumps: integers only');
    return String(x);
  }
  if (typeof x === 'string') return JSON.stringify(x).replace(/[\u0080-\uffff]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);
  if (Array.isArray(x)) return `[${x.map(pyDumps).join(', ')}]`;
  const o = x as Record<string, unknown>;
  return `{${Object.keys(o).sort().map((k) => `${pyDumps(k)}: ${pyDumps(o[k])}`).join(', ')}}`;
}

export function makeId(thread: string, family: string, arm: string, codeSha: string, days: string[], seed: number | null = null, phases: number[] = [], env: Record<string, string> = {}): string {
  const key = pyDumps([thread, family, arm, codeSha, [...days].sort(), seed, [...phases].sort((a, b) => a - b), env]);
  return crypto.createHash('sha1').update(key).digest('hex').slice(0, 16);
}

export interface RegRow {
  v: 1; trial_id: string; ts: string; thread: string; family: string; arm: string; role: 'control' | 'candidate' | 'placebo' | 'loo' | 'neighbour';
  control?: string; env?: Record<string, string>; code_sha: string; code_epoch?: string; seed: number | null;
  data: { source: 'history'; days: string[]; doge: false; benches: 'own' };
  by_day: Record<string, number>; fills?: number; flags?: string[]; verdict?: string; ref?: string; raw?: Record<string, unknown>;
}

/** A v1 row. days: the days whose P&L is in by_day (empty when the trial has no daily P&L: counted, not scored). */
export function regRow(o: { arm: string; role: RegRow['role']; codeSha: string; codeEpoch?: string; control?: string; days?: string[]; byDay?: Record<string, number>; fills?: number; verdict?: string; ref?: string; raw?: Record<string, unknown>; at?: Date }): RegRow {
  const days = o.days ?? Object.keys(o.byDay ?? {}).sort();
  const row: RegRow = {
    v: 1, trial_id: makeId(REG_THREAD, REG_FAMILY, o.arm, o.codeSha, days), ts: (o.at ?? new Date()).toISOString(), thread: REG_THREAD, family: REG_FAMILY,
    arm: o.arm, role: o.role, code_sha: o.codeSha, seed: null, data: { source: 'history', days, doge: false, benches: 'own' }, by_day: o.byDay ?? {},
  };
  if (o.control) row.control = o.control;
  if (o.codeEpoch) row.code_epoch = o.codeEpoch;
  if (o.fills !== undefined) row.fills = o.fills;
  if (o.verdict) row.verdict = o.verdict;
  if (o.ref) row.ref = o.ref;
  if (o.raw) row.raw = o.raw;
  return row;
}

/** The random-entry control of a sweep run: every candidate's excess is measured against random entries through the same
 *  exits, on the same days and coins (the pairing the registry asks for). */
export const controlArm = (run: string) => `random-entries:run-${run}`;
export const runRef = (run: string) => (run === 'local' ? 'local' : `https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/${run}`);
