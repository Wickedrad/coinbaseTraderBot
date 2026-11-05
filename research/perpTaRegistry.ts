// Rows for the project trial registry (meta plan thread; gdrive:kalshi-bot-archive/registry/shards/perp-ta/<run>.jsonl;
// schema: research/registry.py "registry trial row v1"). One row per trial; the sweep's own record (funnel, N_raw, the
// group's statistics) is kept verbatim under raw. trial_id = registry.py make_id: sha1 of Python's json.dumps of
// [thread, family, arm, code_sha, sorted days, seed, sorted phases, env] with sort_keys, first 16 hex digits.

import crypto from 'crypto';
import fs from 'fs';
import path from 'path';

export const REG_THREAD = 'perp-ta';
export const REG_FAMILY = 'perp-ta-rulebook';
/** Steven 21:59 UTC Nov 5: $/h is tracked per contract type (registry.py CONTRACT_TYPES; the contract ledger). */
export const REG_CONTRACT = 'perpetual';

/** The bot modules a perp TA rulebook touches (registry.py: the contract ledger only adds results whose module sets are
 *  disjoint, so a module read as an input is listed too: a change to it would not add to the rulebook's result).
 *  changes: which setups the perp trader takes (bot/setups/detectors.ts, setupTrader.ts), how they exit (stop, target and
 *  hold: bot/setups/exits.ts) and how the entry order rests (the post-only executor: bot/perps/perpTrader.ts).
 *  reads: the bot's TA modules every primitive comes from (research/perpTaModules.ts); conviction from round 2 on (a row
 *  without a round gets the current set). */
export function regModules(round = Infinity): { modules: string[]; module_roles: { changes: string[]; reads: string[] } } {
  const changes = ['perp-setups', 'perp-exits', 'perp-entry-orders'];
  const reads = ['ta-indicators', 'ta-analyzer', 'ta-confluence', 'ta-lib', 'ta-character', 'ta-net', 'librarian', 'cross-graph', ...(round >= 2 ? ['ta-conviction'] : [])];
  return { modules: [...changes, ...reads].sort(), module_roles: { changes, reads } };
}

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
  contract_type: typeof REG_CONTRACT; modules: string[]; module_roles: { changes: string[]; reads: string[] };
  /** true only when by_day is out of sample for the choice of the arm (the sealed blind test). */
  held_out: boolean; /** hours of trading behind by_day (perps trade around the clock: 24 a day). */ hours?: number;
  /** The held-out standard HO-1 evidence (research/registry.py heldout), on blind rows that read the sealed block. */
  heldout?: { standard: 'HO-1'; tier: 'history'; days: number; folds: number; folds_won: number; worst_fold_per_hour: number; terciles_covered: number; terciles_won: number; worst_tercile_per_hour?: number; beats_placebo: boolean };
}

/** The simulator behind a row (meta plan thread, Nov 5: perp rows are exempt from REPLAY_VERSION, which is the Kalshi
 *  replay's; a later fix to the perp minute simulator must be traceable): "perp-minute-sim <sha12> (<what ran>)". */
export const simEpoch = (codeSha: string, what?: string) => `perp-minute-sim ${codeSha.slice(0, 12)}${what ? ` (${what})` : ''}`;

/** A v1 row. days: the days whose P&L is in by_day (empty when the trial has no daily P&L: counted, not scored). */
export function regRow(o: { arm: string; role: RegRow['role']; round?: number; codeSha: string; codeEpoch?: string; control?: string; days?: string[]; byDay?: Record<string, number>; fills?: number; verdict?: string; ref?: string; raw?: Record<string, unknown>; heldOut?: boolean; heldout?: RegRow['heldout']; at?: Date }): RegRow {
  const days = o.days ?? Object.keys(o.byDay ?? {}).sort();
  const row: RegRow = {
    v: 1, trial_id: makeId(REG_THREAD, REG_FAMILY, o.arm, o.codeSha, days), ts: (o.at ?? new Date()).toISOString(), thread: REG_THREAD, family: REG_FAMILY,
    arm: o.arm, role: o.role, code_sha: o.codeSha, seed: null, data: { source: 'history', days, doge: false, benches: 'own' }, by_day: o.byDay ?? {},
    contract_type: REG_CONTRACT, ...regModules(o.round), held_out: o.heldOut ?? false,
  };
  if (days.length) row.hours = 24 * days.length;
  if (o.control) row.control = o.control;
  row.code_epoch = simEpoch(o.codeSha, o.codeEpoch);
  if (o.fills !== undefined) row.fills = o.fills;
  if (o.verdict) row.verdict = o.verdict;
  if (o.ref) row.ref = o.ref;
  if (o.raw) row.raw = o.raw;
  if (o.heldout) row.heldout = o.heldout;
  return row;
}

/** The random-entry control of a sweep run: every candidate's excess is measured against random entries through the same
 *  exits, on the same days and coins (the pairing the registry asks for). */
export const controlArm = (run: string) => `random-entries:run-${run}`;
export const runRef = (run: string) => (run === 'local' ? 'local' : `https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/${run}`);

type Legacy = Record<string, unknown> & { kind?: string; run?: string; sha?: string; round?: number; at_utc?: string };
const roundOfArm = (arm: string) => { const m = /^r(\d+):/.exec(arm); return m ? +m[1] : undefined; };

/** Every perp TA round as registry v1 shards (Steven 21:59 UTC Nov 5: $/h per contract type, with the modules each touches).
 *  legacy: the rows the sweep, study and blind wrote before registry v1 (registry/perp-ta-<kind>run-<id>.jsonl), converted
 *  to the rows the current writers make from the same record (same arms, code sha and days, so the same trial ids; the
 *  record kept under raw). v1: shards already in registry/shards/perp-ta/, given the fields they lack (contract_type,
 *  modules, module_roles, held_out, hours) with every other field and the trial id unchanged. Returns the shards to
 *  (re)write: name -> rows. A legacy file whose shard already exists is skipped (the v1 rows win). */
export function backfill(legacy: Record<string, Legacy[]>, v1: Record<string, Record<string, unknown>[]>): { out: Record<string, RegRow[]>; log: string[] } {
  const out: Record<string, RegRow[]> = {}, log: string[] = [];
  // The round each sweep run tested (legacy run rows carry it from round 2 on; round 1 rows have none).
  const roundOf: Record<string, number> = {};
  for (const rows of Object.values(legacy)) for (const r of rows) if (r.kind === 'run' && r.run) roundOf[String(r.run)] = r.round ?? 1;
  for (const rows of Object.values(v1)) for (const r of rows) { const m = /^r(\d+):sweep:run-(\d+)$/.exec(String(r.arm)); if (m) roundOf[m[2]] = +m[1]; }
  for (const [name, rows] of Object.entries(legacy).sort()) {
    const shard = name.replace(/^perp-ta-/, '');
    if (v1[shard]) { log.push(`${name}: ${shard} already a v1 shard, skipped`); continue; }
    const conv: RegRow[] = [];
    for (const r of rows) {
      const run = String(r.run ?? ''), sha = String(r.sha ?? ''), at = r.at_utc ? new Date(r.at_utc) : undefined;
      if (!run || !sha) throw new Error(`${name}: a ${r.kind} row without run or sha`);
      if (r.kind === 'run' || r.kind === 'group') {
        const round = r.round ?? 1, codeEpoch = `perp-ta round ${round}`, ref = runRef(run);
        const ctl = regRow({ arm: controlArm(run), role: 'control', round, codeSha: sha, codeEpoch, ref, at, verdict: 'random entries through the same exits (the excess baseline)' });
        if (r.kind === 'run') {
          const passed = ((r.funnel ?? {}) as Record<string, number>)['+validation'] ?? 0;
          conv.push(ctl, regRow({ arm: `r${round}:sweep:run-${run}`, role: 'candidate', round, control: ctl.trial_id, codeSha: sha, codeEpoch, ref, at, verdict: `${r.n_raw} cells tested; ${passed} pass validation`, raw: r }));
        } else {
          conv.push(regRow({ arm: `r${round}:run-${run}:${r.group}|${r.pol}|${r.cond}`, role: 'candidate', round, control: ctl.trial_id, codeSha: sha, codeEpoch, ref, at, verdict: String(r.verdict ?? ''), raw: r }));
        }
      } else if (r.kind === 'study') {
        const of = String(r.of_sweep_run ?? '');
        conv.push(regRow({ arm: `study:of-run-${of}`, role: 'candidate', round: roundOf[of], codeSha: sha, codeEpoch: 'perp-ta study', ref: runRef(run), at, verdict: `validation SPA p ${r.spa_validation_p}; N_raw ${r.n_raw}, N_eff ${r.n_eff}`, raw: r }));
      } else if (r.kind === 'blind-test') {
        // A blind test before registry v1: the record has no $ per day, so its rows are counted, not scored (and not held out).
        const from = String(r.frozen_from_run ?? ''), h = String(r.set_hash ?? '').slice(0, 12), codeEpoch = `perp-ta blind of run ${from}`, ref = runRef(run);
        const v = (r.verdict ?? {}) as { rulebook?: { pass?: boolean; why?: string[] }; passersRulebook?: { pass?: boolean; why?: string[] } | null };
        const say = (b?: { pass?: boolean; why?: string[] } | null) => `${b?.pass ? 'PASS' : (b?.why ?? []).join('; ') || 'no verdict'} (legacy row: no $ per day kept)`;
        const flat = regRow({ arm: `blind:${h}:flat`, role: 'control', round: roundOf[from], codeSha: sha, codeEpoch, ref, at, verdict: 'flat: no position (the rulebook benchmark)' });
        conv.push(flat, regRow({ arm: `blind:${h}:all`, role: 'candidate', round: roundOf[from], control: flat.trial_id, codeSha: sha, codeEpoch, ref, at, verdict: say(v.rulebook), raw: r }));
        if (v.passersRulebook) conv.push(regRow({ arm: `blind:${h}:passers`, role: 'candidate', round: roundOf[from], control: flat.trial_id, codeSha: sha, codeEpoch, ref, at, verdict: say(v.passersRulebook), raw: { kind: 'blind-test-passers', set_hash: r.set_hash } }));
      } else throw new Error(`${name}: unknown legacy row kind ${r.kind}`);
    }
    out[shard] = conv;
    log.push(`${name} -> ${shard}: ${conv.length} rows`);
  }
  for (const [name, rows] of Object.entries(v1).sort()) {
    // A file's random-entry control takes the round of the file's sweep row; a study the round of the run it studied.
    const fileRound = rows.map((r) => roundOfArm(String(r.arm))).find((x) => x !== undefined);
    let changed = 0;
    const filled = rows.map((r) => {
      const epochOk = String(r.code_epoch ?? '').startsWith('perp-minute-sim ');
      if (r.contract_type && r.modules && r.module_roles && r.held_out !== undefined && epochOk) return r as unknown as RegRow;
      const arm = String(r.arm), study = /^study:of-run-(\d+)$/.exec(arm);
      const round = roundOfArm(arm) ?? (arm.startsWith('random-entries:') ? fileRound : study ? roundOf[study[1]] : undefined);
      const days = Object.keys((r.by_day ?? {}) as Record<string, number>);
      const add: Partial<RegRow> = { contract_type: REG_CONTRACT, ...regModules(round), held_out: /^blind:[^:]+:(all|flat)$/.test(arm) && days.length > 0 };
      if (days.length && r.hours === undefined) add.hours = 24 * days.length;
      changed++;
      return { ...add, ...r, ...(epochOk ? {} : { code_epoch: simEpoch(String(r.code_sha), r.code_epoch ? String(r.code_epoch) : undefined) }) } as unknown as RegRow;
    });
    if (changed) { out[name] = filled; log.push(`${name}: ${changed} of ${rows.length} rows given contract_type, modules and the simulator epoch`); }
    else log.push(`${name}: complete, left as is`);
  }
  return { out, log };
}

const readJsonl = (f: string) => fs.readFileSync(f, 'utf8').split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l));
const jsonlIn = (dir: string | undefined, re: RegExp) => Object.fromEntries((dir && fs.existsSync(dir) ? fs.readdirSync(dir) : []).filter((f) => re.test(f)).map((f) => [f, readJsonl(path.join(dir!, f))]));

// CLI: npx tsx research/perpTaRegistry.ts backfill --legacy <dir of registry/perp-ta-*.jsonl> --v1 <dir of shards/perp-ta/*.jsonl> --out <dir>
if (process.argv[1] && /perpTaRegistry\.ts$/.test(process.argv[1]) && process.argv[2] === 'backfill') {
  const arg = (k: string) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : undefined; };
  const outDir = arg('out') ?? 'registry-out';
  const { out, log } = backfill(jsonlIn(arg('legacy'), /^perp-ta-.*\.jsonl$/), jsonlIn(arg('v1'), /\.jsonl$/));
  fs.mkdirSync(outDir, { recursive: true });
  for (const [name, rows] of Object.entries(out)) fs.writeFileSync(path.join(outDir, name), rows.map((x) => JSON.stringify(x)).join('\n') + '\n');
  for (const l of log) console.log(`[perp-ta-registry] ${l}`);
  console.log(`[perp-ta-registry] ${Object.keys(out).length} shard(s) to write`);
}
