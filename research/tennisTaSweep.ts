// Tennis TA rulebook trial: the sweep CLI the GitHub workflow runs (pre-registration and its amendments:
// /mnt/project-files/tennis-ta/preregistration.md; thread "Build a profitable tennis TA rulebook", Nov 5 2026). The request
// file format and the run mechanics are documented in research/tennis-ta/README.md.
//
//   units   --from D --to D [--out F]          the tournament-week unit table with the hashed seal (A3), calendar only
//   fees    --series S,S --out F               Kalshi fee changes per series (GET /series/fee_changes, show_historical)
//   days    --hist DIR --out DIR --from D --to D --series S,S   build history replay days (research/history/historyReplay.ts)
//   prep    --request F --units F --out F      validate a sweep request and write the plan (shards and sub-slices by unit)
//   plan    --units F --from D --to D --shards N [--pool disc]   the shard plan alone (JSON)
//   subplan --units F --units-list U,U [--parts 4]               a shard's sub-slices (JSON; the same cut prep made)
//   run     --replay DIR --from D --to D --units-list U,U --stage 1|2 --pool disc --units F --out F.json.gz
//           [--fees F] [--hist DIR] [--family-b true] [--data-version S] [--request F] [--run ID] [--k K --j J
//           --shards N --sub-shards M] [--specs F]
//   coverage --hist DIR --from D --to D [--series S,S] [--stratum H|R]   the history is complete over a span (exit 1 if not)
//   check   --dir DIR --listing F --prep F --run ID [--out F]   every planned shard file present once, one data version, and
//           the history complete over every slice (download listing and trade tapes)
//   pool-hours --units F [--pool disc]         the pool's wall-clock intervals per unit, embargoed time left out
//
// Pools (Amendment 1, A3): history stops at Nov 5 02:00 UTC (Nov 4 9:00 PM EST); a match is in a pool only if both its
// start and its close are before that cutoff, and a match closing in a lockbox week (L1 = Nov 6 05:00 to Nov 13 05:00 UTC,
// then 7-day steps) is out unless that lockbox id is opened; units are Monday 05:00 UTC weeks with each Grand Slam as one
// unit; a unit is sealed when sha256("tennis-ta-seal|" + its start date) begins with a number = 0 mod 3; matches within
// 24 h of a sealed unit are embargoed; dev-discovery = unsealed units starting before 2026-04-01, dev-check = the unsealed
// rest. A run scores one pool, and only 'disc' can be requested until the openings ledger exists ('check' and sealed
// units need an entry there naming them). Sealed matches are streamed past, never simulated.
//
// Slicing (C5): shards and their sub-slices are cut at unit edges, so a unit is never split and the cross-match state
// (the tennis-only pacer, the 25% / 10% caps, the coin-placebo stream, family B's placebo reservoir) restarts only at unit
// edges. A slice owns the matches whose start is in [from 00:00, to 00:00) UTC and whose unit is in its unit list.

import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import { execSync } from 'child_process';
import { loadConfig, paperEnv } from '../bot/config';
import type { FeeSchedule } from '../bot/fees';
import { buildHistoryReplay } from './history/historyReplay';
import { FEES, runSweep, type MatchInfo, type SimRun, type SimSpec } from './tennisTaSim';
import { SignalStudy } from './tennisTaSignals';
import type { FamilyBExport, MatchGrid } from './tennisTaTypes';

export const SIM_VERSION = 'tennis-ta-sim/2';
const DAY = 86_400_000;
const WEEK = 7 * DAY;
/** History and inventory stop here (Nov 4 9:00 PM EST). */
export const HARD_CUTOFF = Date.parse('2026-11-05T02:00:00Z');
/** L1 opens Nov 6 05:00 UTC (00:00 EST); lockbox weeks follow in 7-day steps (L2 Nov 13 05:00, ...). */
export const LOCKBOX_FROM = Date.parse('2026-11-06T05:00:00Z');
/** Dev-check starts with the units starting on or after this date. */
export const CHECK_FROM = Date.parse('2026-04-01T00:00:00Z');
const EMBARGO = DAY;
/** R: days before a slice's first day whose market lines the sim reads, so a match the bot listed early is not lost (C1).
 *  H reads one day back whatever is passed (history lists a match 30 min before its start): see lookbackOf. */
export const LOOKBACK_DAYS = 7;
/** Days before a slice's first day whose market lines the sim reads on each stratum (runSweep in research/tennisTaSim.ts). */
export const lookbackOf = (stratum: 'H' | 'R'): number => (stratum === 'R' ? LOOKBACK_DAYS : 1);
/** Days after a slice's last day in which its matches may still close (the shard job builds replay days this far too). */
export const CLOSE_TAIL_DAYS = 2;
/** Sub-slices per shard job (one process per core of a GitHub runner). */
export const SUB_SHARDS = 4;
/** Family B (sterile event study) settings for every sweep that carries it. */
export const FAMILY_B = { orderUsd: 15, latencySec: 1, seed: 20261105 } as const;
/** History bars (A1: one-level minute books make 10 s / 30 s bars near copies). */
export const H_BARS = ['1m', '5m'];
export const STAGE2_SPECS = 'research/tennis-ta/stage2-specs.json';
/** The only pool a request may name until the openings ledger exists. */
export const REQUESTABLE_POOLS: ReadonlyArray<Pool> = ['disc'];

const dayOf = (t: number) => new Date(t).toISOString().slice(0, 10);
const sha256 = (b: Buffer | string) => crypto.createHash('sha256').update(b).digest('hex');

// ---------------------------------------------------------------------------------------------------------------------
// Units

/** Grand Slam main draws (first day, final), from the official calendars; each is one unit from the Monday 05:00 UTC
 *  at or before its first day to the Monday 05:00 UTC after its final. */
export const SLAMS: ReadonlyArray<[string, string, string]> = [
  ['AO', '2025-01-12', '2025-01-26'], ['RG', '2025-05-25', '2025-06-08'], ['WIM', '2025-06-30', '2025-07-13'], ['USO', '2025-08-24', '2025-09-07'],
  ['AO', '2026-01-18', '2026-02-01'], ['RG', '2026-05-24', '2026-06-07'], ['WIM', '2026-06-29', '2026-07-12'], ['USO', '2026-08-30', '2026-09-13'],
];

export interface Unit { id: string; start: number; end: number; startDay: string; slam?: string; sealed: boolean }

/** The Monday 05:00 UTC at or before t. */
export function mondayEdge(t: number): number {
  const d = new Date(t - 5 * 3_600_000);
  const midnight = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  const back = (d.getUTCDay() + 6) % 7; // days since Monday
  return midnight - back * DAY + 5 * 3_600_000;
}

/** Sealed iff the first 8 hex characters of sha256("tennis-ta-seal|YYYY-MM-DD") are 0 mod 3. */
export function sealedByHash(startDay: string): boolean {
  return parseInt(sha256(`tennis-ta-seal|${startDay}`).slice(0, 8), 16) % 3 === 0;
}

/** The unit table over [fromDay, toDay] (calendar only: no market data is read). */
export function buildUnits(fromDay: string, toDay: string): Unit[] {
  const slams = SLAMS.map(([name, a, b]) => ({ name, start: mondayEdge(Date.parse(a) + 12 * 3_600_000), end: mondayEdge(Date.parse(b) + 12 * 3_600_000) + WEEK }));
  const units: Unit[] = [];
  const last = Date.parse(toDay) + DAY;
  for (let t = mondayEdge(Date.parse(fromDay)); t < last;) {
    const s = slams.find((x) => t >= x.start && t < x.end);
    const start = s ? Math.max(s.start, t) : t;
    const end = s ? s.end : t + WEEK;
    const startDay = dayOf(start);
    units.push({ id: s ? `${s.name}-${startDay}` : `W-${startDay}`, start, end, startDay, ...(s ? { slam: s.name } : {}), sealed: sealedByHash(startDay) });
    t = end;
  }
  return units;
}

/** Integrity of a committed unit table: sorted, contiguous, Monday 05:00 UTC edges, ids and seals as the calendar and the
 *  hash give them, and every unit as buildUnits gives it over the table's span (each Grand Slam in SLAMS one unit, never
 *  split into weeks or merged into a neighbour). Returns the problems found (empty = sound). */
export function verifyUnits(units: Unit[]): string[] {
  const p: string[] = [];
  if (!Array.isArray(units) || !units.length) return ['the unit table is empty'];
  units.forEach((u, i) => {
    if (typeof u.id !== 'string' || !Number.isFinite(u.start) || !Number.isFinite(u.end) || !(u.end > u.start)) { p.push(`unit ${i}: malformed`); return; }
    if (mondayEdge(u.start) !== u.start || mondayEdge(u.end) !== u.end) p.push(`${u.id}: edges are not Monday 05:00 UTC`);
    if (u.startDay !== dayOf(u.start)) p.push(`${u.id}: startDay ${u.startDay} is not the start's day`);
    if (u.sealed !== sealedByHash(u.startDay)) p.push(`${u.id}: sealed=${u.sealed} disagrees with the seal hash`);
    if (u.id !== `${u.slam ?? 'W'}-${u.startDay}`) p.push(`${u.id}: id does not match its start`);
    if (i > 0 && units[i - 1].end !== u.start) p.push(`${u.id}: not contiguous with ${units[i - 1].id}`);
  });
  // The calendar itself, once the table is well formed: each unit must be the unit buildUnits starts at the same edge.
  if (!p.length) {
    const gen = buildUnits(units[0].startDay, units[units.length - 1].startDay);
    const at = new Map(gen.map((g) => [g.start, g]));
    for (const u of units) {
      const g = at.get(u.start);
      if (!g) {
        const inside = gen.find((x) => u.start > x.start && u.start < x.end);
        p.push(`${u.id}: the calendar has no unit edge at its start${inside ? ` (it falls inside ${inside.id}, ${inside.startDay} to ${dayOf(inside.end)})` : ''}`);
      } else if (g.id !== u.id || g.end !== u.end || (g.slam ?? '') !== (u.slam ?? '')) {
        p.push(`${u.id}: the calendar gives ${g.id} from ${g.startDay} to ${dayOf(g.end)}${g.slam ? ` (Grand Slam ${g.slam}, one unit)` : ''}, not ${u.id} to ${dayOf(u.end)}`);
      }
    }
    const last = units[units.length - 1].end;
    const starts = new Set(units.map((u) => u.start));
    for (const g of gen) if (g.start >= units[0].start && g.start < last && !starts.has(g.start)) p.push(`${g.id}: a calendar unit edge the table does not hold`);
  }
  return p;
}

export type Pool = 'disc' | 'check' | 'sealed' | 'embargo' | 'out';

export interface Lockbox { id: string; start: number; end: number }

/** The lockbox week holding t (L1 from LOCKBOX_FROM, then 7-day steps), or undefined before L1. */
export function lockboxOf(t: number): string | undefined {
  return t >= LOCKBOX_FROM ? `L${1 + Math.floor((t - LOCKBOX_FROM) / WEEK)}` : undefined;
}

/** The lockbox table [start, end) from LOCKBOX_FROM in 7-day steps, up to the week holding `until`. */
export function lockboxes(until: number): Lockbox[] {
  const out: Lockbox[] = [];
  for (let s = LOCKBOX_FROM, i = 1; s <= until; s += WEEK, i++) out.push({ id: `L${i}`, start: s, end: s + WEEK });
  return out;
}

/** The pool a unit's matches fall in before the embargo and lockbox tests. */
export function unitPool(u: Unit, opened: Set<string> = new Set(), cutoff = HARD_CUTOFF): Pool {
  if (u.start >= cutoff) return 'out';
  if (u.sealed && !opened.has(u.id)) return 'sealed';
  return u.start < CHECK_FROM ? 'disc' : 'check';
}

/** The pool a match belongs to, by its start and its close (the latest close of its markets). `opened` holds sealed unit
 *  ids and lockbox ids ('L1', 'L2', ...) already opened through the openings ledger (none exists yet). A match is out
 *  unless both its start and its close are before the cutoff, and out if any lockbox week it reaches is unopened. */
export function poolOf(start: number, close: number, units: Unit[], opened: Set<string> = new Set(), cutoff = HARD_CUTOFF): Pool {
  if (!(start < cutoff) || !(close < cutoff)) return 'out';
  if (close >= LOCKBOX_FROM) {
    const first = Math.floor((Math.max(start, LOCKBOX_FROM) - LOCKBOX_FROM) / WEEK), last = Math.floor((close - LOCKBOX_FROM) / WEEK);
    for (let i = first; i <= last; i++) if (!opened.has(`L${i + 1}`)) return 'out';
  }
  const u = units.find((x) => start >= x.start && start < x.end);
  if (!u) return 'out';
  const up = unitPool(u, opened, cutoff);
  if (up !== 'disc' && up !== 'check') return up;
  for (const s of units) if (s.sealed && !opened.has(s.id) && ((start >= s.start - EMBARGO && start < s.start) || (start >= s.end && start < s.end + EMBARGO))) return 'embargo';
  return up;
}

export const unitOf = (start: number, units: Unit[]): string | undefined => units.find((x) => start >= x.start && start < x.end)?.id;

/** [a, b) minus the given windows. */
function subtract(a: number, b: number, cuts: Array<[number, number]>): Array<[number, number]> {
  let parts: Array<[number, number]> = a < b ? [[a, b]] : [];
  for (const [c, d] of cuts) {
    const next: Array<[number, number]> = [];
    for (const [x, y] of parts) {
      if (d <= x || c >= y) { next.push([x, y]); continue; }
      if (c > x) next.push([x, c]);
      if (d < y) next.push([d, y]);
    }
    parts = next;
  }
  return parts;
}

export interface PoolSpan { unit: string; start: number; end: number; intervals: Array<[number, number]>; hours: number }

/** The wall-clock time each unit of a pool contributes to $/h (section 8: every hour counts, matches or not): the unit's
 *  span cut at the hard cutoff, minus the embargo windows of unopened sealed units. The report clips these intervals to
 *  the data span; every pool unit is listed whether or not it holds a match. */
export function poolSpans(units: Unit[], pool: Pool, opened: Set<string> = new Set(), cutoff = HARD_CUTOFF, only?: Set<string>): PoolSpan[] {
  const cuts: Array<[number, number]> = [];
  for (const s of units) if (s.sealed && !opened.has(s.id)) cuts.push([s.start - EMBARGO, s.start], [s.end, s.end + EMBARGO]);
  return units.filter((u) => unitPool(u, opened, cutoff) === pool && (!only || only.has(u.id))).map((u) => {
    const intervals = subtract(u.start, Math.min(u.end, cutoff), cuts);
    return { unit: u.id, start: u.start, end: u.end, intervals, hours: intervals.reduce((s, [a, b]) => s + (b - a), 0) / 3_600_000 };
  });
}

// ---------------------------------------------------------------------------------------------------------------------
// Fees by date

export interface FeeEra { from: number; fees: FeeSchedule }

/** Kalshi fee_type to bot/fees.ts multipliers (bot/kalshi/feeSchedule.ts: quadratic = taker only; quadratic_with_maker_fees
 *  = plus the maker fee at the multiplier; the combo variant charges the maker fee twice). */
export function feesOfType(type: string, multiplier: number): FeeSchedule {
  if (type === 'quadratic_with_maker_fees') return { takerMultiplier: multiplier, makerMultiplier: multiplier };
  if (type === 'quadratic_with_combo_maker_fees') return { takerMultiplier: multiplier, makerMultiplier: 2 * multiplier };
  return { takerMultiplier: multiplier, makerMultiplier: 0 };
}

/** A lookup from fee eras per series; before the first change, the first era's schedule (the conservative choice when
 *  Kalshi lists no earlier change). */
export function feeLookup(eras: Record<string, FeeEra[]>): (series: string, t: number) => FeeSchedule {
  const sorted = Object.fromEntries(Object.entries(eras).map(([s, l]) => [s, [...l].sort((a, b) => a.from - b.from)]));
  return (series, t) => {
    const l = sorted[series];
    if (!l?.length) return FEES;
    let f = l[0].fees;
    for (const e of l) if (e.from <= t) f = e.fees; else break;
    return f;
  };
}

async function fetchFeeEras(series: string[]): Promise<Record<string, FeeEra[]>> {
  const base = process.env.KALSHI_REST_URL ?? 'https://external-api.kalshi.com/trade-api/v2';
  const out: Record<string, FeeEra[]> = {};
  for (const s of series) {
    const r = await fetch(`${base}/series/fee_changes?series_ticker=${s}&show_historical=true`);
    if (!r.ok) throw new Error(`fee_changes ${s}: HTTP ${r.status}`);
    const j = (await r.json()) as { series_fee_change_arr?: Array<{ series_ticker: string; fee_type: string; fee_multiplier: number; scheduled_ts: string }> };
    out[s] = (j.series_fee_change_arr ?? []).filter((x) => x.series_ticker === s).map((x) => ({ from: Date.parse(x.scheduled_ts), fees: feesOfType(x.fee_type, Number(x.fee_multiplier)) }));
  }
  return out;
}

// ---------------------------------------------------------------------------------------------------------------------
// The staged design (Amendment 1, A1)

/** A sweep spec; measuring sticks are reported but never screened or counted as hypotheses (C4). */
export type SweepSpec = SimSpec & { stick?: true };

const PROD = { TENNIS_CONF_MOMENTUM_CENTS: 0.01, TENNIS_CONF_FLOW: 0.2, TENNIS_CONF_OPPONENT_CENTS: 0.01, TENNIS_CONF_WINDOW_SEC: 60 };
/** Section 4: the LiquidityRatchet (book-wall trailing stop) means nothing on H's one-level synthetic book; H runs it off. */
const H_FIXED = { TENNIS_TRAIL_RATCHET: false };

/** Stage 1 (H): momentum x flow x opponent x window (3 x 3 x 3 x 3 = 81 configs; production's point is in the grid), each
 *  under F1, F2 and its coin-flip placebo (F1), plus two measuring sticks at production: the settle-hold arm (production's
 *  end loser cut off, TENNIS_END_LOSER_CUT=false) and the pacer-off arm. History windows are at least 60 s. Every spec
 *  runs with the ratchet off (section 4). 245 specs. */
export function stage1Specs(): SweepSpec[] {
  const specs: SweepSpec[] = [];
  for (const m of [0.005, 0.01, 0.02]) for (const f of [0.05, 0.2, 0.4]) for (const o of [0.005, 0.01, 0.02]) for (const w of [60, 120, 300]) {
    const overrides = { TENNIS_CONF_MOMENTUM_CENTS: m, TENNIS_CONF_FLOW: f, TENNIS_CONF_OPPONENT_CENTS: o, TENNIS_CONF_WINDOW_SEC: w, ...H_FIXED };
    const id = `A|s1|m${m}|f${f}|o${o}|w${w}`;
    specs.push({ id: `${id}|F1`, overrides, fill: 'F1' }, { id: `${id}|F2`, overrides, fill: 'F2' }, { id: `${id}|coin`, overrides, fill: 'F1', placebo: 'coin' });
  }
  specs.push({ id: 'A|s1|prod|settlehold|F1', overrides: { ...PROD, ...H_FIXED, TENNIS_END_LOSER_CUT: false }, fill: 'F1', stick: true });
  specs.push({ id: 'A|s1|prod|nopacer|F1', overrides: { ...PROD, ...H_FIXED, HARNESS_PACER: 'off' }, fill: 'F1', stick: true });
  return specs;
}

const SPEC_KEYS = new Set(['id', 'overrides', 'fill', 'placebo', 'stick', 'offsetMs']);

type OverrideValue = string | number | boolean;
const numIn = (lo: number, hi: number, loOpen = false) => (v: OverrideValue): string | undefined => {
  const x = typeof v === 'boolean' || (typeof v === 'string' && !v.trim()) ? NaN : Number(v);
  return Number.isFinite(x) && (loOpen ? x > lo : x >= lo) && x <= hi ? undefined : `must be a number in ${loOpen ? '(' : '['}${lo}, ${hi}]`;
};
/** The harness rules research/tennisTaSim.ts reads from a spec's overrides (SimSpec.overrides; ConfigSim), each with its
 *  value check. Any other HARNESS_* key would be ignored by the sim, so it is refused. */
export const HARNESS_RULES: Readonly<Record<string, (v: OverrideValue) => string | undefined>> = {
  HARNESS_PACER: (v) => (v === 'tennis' || v === 'off' ? undefined : `must be 'tennis' or 'off'`),
  HARNESS_LOSER_STOP: numIn(0, 1),
  HARNESS_BANKROLL: numIn(0, 1e6, true),
  HARNESS_FEE_MULT: numIn(0, 10),
  HARNESS_LATENCY_MS: numIn(0, 60_000),
};
/** The TENNIS_* / PACER* overrides as the sim hands them to production's loadConfig (tennisTaSim.ts configOf). */
const configEnv = (o: Record<string, unknown>): Record<string, string> =>
  Object.fromEntries(Object.entries(o).filter(([k]) => k.startsWith('TENNIS_') || k.startsWith('PACER')).map(([k, v]) => [k, String(v)]));
/** Production's loadConfig on an env, recording every key it reads: the parts the sim uses (tennis config and the pacer
 *  config) as JSON, or the error loadConfig throws on a bad value. */
export function configRead(env: Record<string, string>): { read: Set<string>; sim?: string; error?: string } {
  const read = new Set<string>();
  const spy = new Proxy(paperEnv(env), {
    get: (t, k) => { if (typeof k === 'string') read.add(k); return Reflect.get(t, k); },
    has: (t, k) => { if (typeof k === 'string') read.add(k); return Reflect.has(t, k); },
  });
  try {
    const c = loadConfig(spy);
    return { read, sim: JSON.stringify([c.tennis, c.strategy.pacer]) };
  } catch (e) { return { read, error: (e as Error).message }; }
}

/** Validate stage 2's spec list (research/tennis-ta/stage2-specs.json): an array of {id, overrides, fill, placebo?} with
 *  ids starting 'A|s2|', unique; optional stick: true (measuring stick) and offsetMs (noise-floor clock phase). Overrides
 *  are env-style TENNIS_* / PACER_* / HARNESS_* keys with string, number or boolean values. Every TENNIS_* / PACER_* key
 *  must be one production's loadConfig reads (a misspelt key would run as the production default and still count) with
 *  a value loadConfig accepts, and together they must change the simulated config; every HARNESS_* key must be one the
 *  sim reads (HARNESS_RULES) with a valid value. Two arms that would run identically (same simulated config, harness
 *  rules, fill and clock phase; coin-placebo arms excepted, their streams are seeded by id) are refused. On H every spec
 *  runs with TENNIS_TRAIL_RATCHET=false (section 4): it is added when unset and a spec that turns it on is refused.
 *  Throws with every problem listed. */
export function validateStage2Specs(raw: unknown, stratum: 'H' | 'R' = 'H'): SweepSpec[] {
  const p: string[] = [];
  if (!Array.isArray(raw)) throw new Error('stage 2 specs: expected a JSON array of {id, overrides, fill, placebo?}');
  if (!raw.length) throw new Error('stage 2 specs: the list is empty');
  const seen = new Set<string>();
  const out: SweepSpec[] = [];
  const forced: Record<string, OverrideValue> = stratum === 'H' ? { TENNIS_TRAIL_RATCHET: false } : {};
  const baseline = configRead(configEnv(forced)).sim;
  const arms = new Map<string, string>();
  raw.forEach((x, i) => {
    const at = `spec ${i}${x && typeof x === 'object' && typeof (x as { id?: unknown }).id === 'string' ? ` (${(x as { id: string }).id})` : ''}`;
    if (!x || typeof x !== 'object' || Array.isArray(x)) { p.push(`${at}: not an object`); return; }
    const s = x as Record<string, unknown>;
    for (const k of Object.keys(s)) if (!SPEC_KEYS.has(k)) p.push(`${at}: unknown key ${k}`);
    if (typeof s.id !== 'string' || !s.id.startsWith('A|s2|')) p.push(`${at}: id must be a string starting 'A|s2|'`);
    else if (seen.has(s.id)) p.push(`${at}: duplicate id`);
    else seen.add(s.id);
    if (s.fill !== 'F0' && s.fill !== 'F1' && s.fill !== 'F2') p.push(`${at}: fill must be F0, F1 or F2`);
    if (s.placebo !== undefined && s.placebo !== 'coin') p.push(`${at}: placebo must be 'coin' when set`);
    if (s.stick !== undefined && s.stick !== true) p.push(`${at}: stick must be true when set`);
    if (s.offsetMs !== undefined && !(Number.isInteger(s.offsetMs) && (s.offsetMs as number) >= 0 && (s.offsetMs as number) < 5000)) p.push(`${at}: offsetMs must be an integer in [0, 5000)`);
    const ov = s.overrides;
    if (!ov || typeof ov !== 'object' || Array.isArray(ov)) { p.push(`${at}: overrides must be an object`); return; }
    const o = { ...(ov as Record<string, unknown>) };
    const before = p.length;
    for (const [k, v] of Object.entries(o)) {
      if (!/^(TENNIS|PACER|HARNESS)_[A-Z0-9_]+$/.test(k)) p.push(`${at}: override ${k} is not a TENNIS_*, PACER_* or HARNESS_* key`);
      if (!['string', 'number', 'boolean'].includes(typeof v) || (typeof v === 'number' && !Number.isFinite(v))) { p.push(`${at}: override ${k} must be a string, finite number or boolean`); continue; }
      if (typeof v === 'string' && !v.trim()) p.push(`${at}: override ${k} is empty (loadConfig reads an empty value as unset, the production default)`);
      if (k === 'HARNESS_LOSER_CUT') p.push(`${at}: HARNESS_LOSER_CUT no longer exists (the settle-hold arm is TENNIS_END_LOSER_CUT=false)`);
      else if (k.startsWith('HARNESS_')) {
        const check = HARNESS_RULES[k];
        if (!check) p.push(`${at}: override ${k} is not a harness rule the sim reads (${Object.keys(HARNESS_RULES).join(', ')}): it would be ignored`);
        else { const bad = check(v as OverrideValue); if (bad) p.push(`${at}: override ${k}=${JSON.stringify(v)} ${bad}`); }
      }
    }
    if (stratum === 'H') {
      if (o.TENNIS_TRAIL_RATCHET === undefined) o.TENNIS_TRAIL_RATCHET = false;
      else if (o.TENNIS_TRAIL_RATCHET !== false && o.TENNIS_TRAIL_RATCHET !== 'false') p.push(`${at}: TENNIS_TRAIL_RATCHET must be off on H (section 4)`);
    }
    if (p.length === before) {
      // Production's loadConfig ignores keys it does not read: a misspelt key would run as the default and still count.
      const env = configEnv(o);
      const r = configRead(env);
      for (const k of Object.keys(env)) if (!r.read.has(k)) p.push(`${at}: override ${k} is not a key production's loadConfig reads (bot/config.ts): it would run as the production default`);
      if (r.error) p.push(`${at}: production's loadConfig refuses the overrides: ${r.error}`);
      const own = Object.keys(env).filter((k) => !(k in forced) || String(forced[k]) !== env[k]);
      if (p.length === before && own.length && r.sim === baseline) p.push(`${at}: overrides ${own.join(', ')} leave the simulated config at production's (every value is the default): drop them (overrides {} is the production arm)`);
      if (p.length === before && s.placebo === undefined) {
        const h = (k: string, d: OverrideValue) => String(o[k] ?? d);
        const key = JSON.stringify([r.sim, h('HARNESS_PACER', 'tennis'), Number(h('HARNESS_LOSER_STOP', 0)), Number(h('HARNESS_BANKROLL', 200)),
          Number(h('HARNESS_FEE_MULT', 1)), Number(h('HARNESS_LATENCY_MS', 0)), s.fill, s.offsetMs ?? 0]);
        const twin = arms.get(key);
        if (twin) p.push(`${at}: runs exactly as ${twin} (same simulated config, harness rules, fill and clock phase): the two arms would give identical results`);
        else arms.set(key, s.id as string);
      }
    }
    out.push({ id: s.id as string, overrides: o as SimSpec['overrides'], fill: s.fill as SimSpec['fill'], ...(s.placebo ? { placebo: 'coin' as const } : {}),
      ...(s.offsetMs !== undefined ? { offsetMs: s.offsetMs as number } : {}), ...(s.stick ? { stick: true as const } : {}) });
  });
  if (p.length) throw new Error(`stage 2 specs: ${p.length} problem(s):\n  ${p.join('\n  ')}`);
  return out;
}

/** The spec list of a stage: stage 1 from stage1Specs() (H only), stage 2 from its spec file (validated). */
export function specsFor(stage: string, stratum: 'H' | 'R', specsPath = STAGE2_SPECS): SweepSpec[] {
  if (stage === '1') {
    if (stratum !== 'H') throw new Error('stage 1 is the H design (ratchet off, windows >= 60 s); an R sweep needs its own stage 2 spec list');
    return stage1Specs();
  }
  if (stage === '2') {
    if (!fs.existsSync(specsPath)) throw new Error(`stage 2 reads its spec list from ${specsPath}, which does not exist: commit it (array of {id, overrides, fill, placebo?}, ids 'A|s2|...') before requesting stage 2`);
    let raw: unknown;
    try { raw = JSON.parse(fs.readFileSync(specsPath, 'utf8')); } catch (e) { throw new Error(`${specsPath}: not valid JSON (${(e as Error).message})`); }
    return validateStage2Specs(raw, stratum);
  }
  throw new Error(`stage must be '1' or '2', got ${JSON.stringify(stage)}`);
}

// ---------------------------------------------------------------------------------------------------------------------
// Plans (C5): cuts at unit edges only

export interface PlanEntry { k: number; from: string; to: string; units: string[] }

/** Split weights into exactly min(parts, n) contiguous non-empty runs with the smallest possible largest run sum
 *  (dynamic programme; ties go to the earliest last cut, so the result is deterministic). Returns the run lengths. */
export function partition(w: number[], parts: number): number[] {
  const n = w.length;
  if (!n) return [];
  const p = Math.min(Math.max(1, Math.floor(parts)), n);
  const pre = [0];
  for (const x of w) pre.push(pre[pre.length - 1] + x);
  const best: number[][] = Array.from({ length: p + 1 }, () => new Array<number>(n + 1).fill(Infinity));
  const cut: number[][] = Array.from({ length: p + 1 }, () => new Array<number>(n + 1).fill(-1));
  best[0][0] = 0;
  for (let k = 1; k <= p; k++) for (let i = k; i <= n; i++) for (let s = k - 1; s < i; s++) {
    const v = Math.max(best[k - 1][s], pre[i] - pre[s]);
    if (v < best[k][i] - 1e-9) { best[k][i] = v; cut[k][i] = s; }
  }
  const lens: number[] = [];
  for (let k = p, i = n; k > 0; k--) { const s = cut[k][i]; lens.unshift(i - s); i = s; }
  return lens;
}

/** Cut a run of units (in start order) into at most `parts` slices at unit edges, balanced by unit length. Each entry:
 *  from = the first unit's start day, to = the day after the last unit's end day (ownership is [from, to) and the unit
 *  list, so the day both neighbours touch is told apart by unit). */
export function planUnits(units: Unit[], parts: number): PlanEntry[] {
  const sorted = [...units].sort((a, b) => a.start - b.start);
  const lens = partition(sorted.map((u) => (u.end - u.start) / DAY), parts);
  const out: PlanEntry[] = [];
  let i = 0;
  lens.forEach((len, k) => {
    const chunk = sorted.slice(i, i + len);
    i += len;
    out.push({ k, from: chunk[0].startDay, to: dayOf(Date.parse(dayOf(chunk[chunk.length - 1].end)) + DAY), units: chunk.map((u) => u.id) });
  });
  return out;
}

/** The units of a pool a request sweeps: every pool unit whose start is in [from, to] (swept whole, so the plan can run
 *  past `to` to the unit's end). Throws when `from` falls after a pool unit's start day and before its end day (that
 *  unit's start is not covered, so it would be swept in part) or [from, to] holds no pool unit. A unit's end day is the
 *  next unit's start day, so from = a unit's start day leaves the unit before it out whole. */
export function requestUnits(units: Unit[], pool: Pool, from: string, to: string, opened: Set<string> = new Set()): Unit[] {
  const F = Date.parse(from), T = Date.parse(to) + DAY;
  const inPool = units.filter((u) => unitPool(u, opened) === pool);
  const cut = inPool.filter((u) => u.start < F && Date.parse(dayOf(u.end)) > F);
  if (cut.length) throw new Error(`[from, to] = [${from}, ${to}] does not cover the start of ${pool} unit ${cut.map((u) => `${u.id} (${dayOf(u.start)} to ${dayOf(u.end)})`).join(', ')}: set from to ${cut[0].startDay} to sweep it whole, or to ${dayOf(cut[cut.length - 1].end)} to leave it out`);
  const sel = inPool.filter((u) => u.start >= F && u.start < T);
  if (!sel.length) throw new Error(`[from, to] = [${from}, ${to}] holds no ${pool} unit`);
  return sel;
}

/** Shard file name of sub-slice j of shard k. */
export const shardFile = (stage: string, k: number, j: number) => `a-s${stage}-${k}-${j}.json.gz`;

// ---------------------------------------------------------------------------------------------------------------------
// Requests (research/tennis-ta/sweep-request.json; format in research/tennis-ta/README.md)

export interface SweepRequest { stage: '1' | '2'; pool: Pool; from: string; to: string; shards: number; familyB: boolean; note?: string }

const REQUEST_KEYS = new Set(['stage', 'pool', 'from', 'to', 'shards', 'familyB', 'note']);
const isDay = (s: unknown): s is string => typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && dayOf(Date.parse(s)) === s;

/** Validate a request; defaults: pool disc, from/to = the whole pool, shards 8, familyB false. Throws with every problem. */
export function parseRequest(raw: unknown, units: Unit[]): SweepRequest {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('sweep request: expected a JSON object');
  const r = raw as Record<string, unknown>;
  const p: string[] = [];
  for (const k of Object.keys(r)) if (!REQUEST_KEYS.has(k)) p.push(`unknown key ${k} (allowed: ${[...REQUEST_KEYS].join(', ')})`);
  const stage = String(r.stage ?? '');
  if (stage !== '1' && stage !== '2') p.push(`stage must be 1 or 2, got ${JSON.stringify(r.stage)}`);
  const pool = (r.pool ?? 'disc') as Pool;
  if (typeof pool !== 'string' || !REQUESTABLE_POOLS.includes(pool)) {
    p.push(pool === 'check' || pool === 'sealed'
      ? `pool '${pool}' needs an openings-ledger entry naming its units, written before the read (Amendment 1, A3); no openings ledger exists yet, so only pool 'disc' can be swept`
      : `pool must be 'disc' (one pool per run; 'check' and sealed units need an openings-ledger entry first), got ${JSON.stringify(r.pool)}`);
  }
  const poolUnits = units.filter((u) => unitPool(u) === 'disc');
  const from = r.from ?? poolUnits[0]?.startDay, to = r.to ?? dayOf(CHECK_FROM - DAY);
  if (!isDay(from)) p.push(`from must be a YYYY-MM-DD day, got ${JSON.stringify(r.from)}`);
  if (!isDay(to)) p.push(`to must be a YYYY-MM-DD day, got ${JSON.stringify(r.to)}`);
  if (isDay(from) && isDay(to) && from > to) p.push(`from ${from} is after to ${to}`);
  const shards = r.shards ?? 8;
  if (!Number.isInteger(shards) || (shards as number) < 1 || (shards as number) > 16) p.push(`shards must be an integer from 1 to 16, got ${JSON.stringify(r.shards)}`);
  if (r.familyB !== undefined && typeof r.familyB !== 'boolean') p.push(`familyB must be true or false, got ${JSON.stringify(r.familyB)}`);
  if (r.note !== undefined && typeof r.note !== 'string') p.push('note must be a string');
  if (p.length) throw new Error(`sweep request: ${p.length} problem(s):\n  ${p.join('\n  ')}`);
  return { stage: stage as '1' | '2', pool, from: from as string, to: to as string, shards: shards as number, familyB: r.familyB === true, ...(r.note !== undefined ? { note: r.note as string } : {}) };
}

export interface Prep {
  request: SweepRequest;
  requestSha: string;
  unitsSha: string;
  simVersion: string;
  stage: '1' | '2';
  pool: Pool;
  familyB: boolean;
  stratum: 'H';
  configs: number;
  /** One entry per shard job (the matrix). */
  plan: PlanEntry[];
  /** subPlans[k] = shard k's sub-slices (one process each), cut by the same rule (subplan re-derives them). */
  subPlans: PlanEntry[][];
  /** Every shard file the run must produce, each exactly once. */
  expected: string[];
  /** Units swept and the pool's wall-clock intervals per unit (embargoed time left out), for the report's $/h. */
  units: string[];
  poolSpans: PoolSpan[];
}

/** Validate a request against the unit table and the stage's spec list; the plan for the workflow. */
export function prepare(requestText: string, unitsText: string, specsPath = STAGE2_SPECS): Prep {
  let raw: unknown;
  try { raw = JSON.parse(requestText); } catch (e) { throw new Error(`sweep request: not valid JSON (${(e as Error).message})`); }
  const units = JSON.parse(unitsText) as Unit[];
  const bad = verifyUnits(units);
  if (bad.length) throw new Error(`unit table: ${bad.length} problem(s):\n  ${bad.slice(0, 20).join('\n  ')}`);
  const req = parseRequest(raw, units);
  const specs = specsFor(req.stage, 'H', specsPath);
  const sel = requestUnits(units, req.pool, req.from, req.to);
  const plan = planUnits(sel, req.shards);
  const byId = new Map(units.map((u) => [u.id, u]));
  const subPlans = plan.map((e) => planUnits(e.units.map((id) => byId.get(id)!), SUB_SHARDS));
  return {
    request: req, requestSha: sha256(requestText), unitsSha: sha256(unitsText), simVersion: SIM_VERSION, stage: req.stage, pool: req.pool,
    familyB: req.familyB, stratum: 'H', configs: specs.length, plan, subPlans,
    expected: plan.flatMap((e) => subPlans[e.k].map((s) => shardFile(req.stage, e.k, s.k))),
    units: sel.map((u) => u.id), poolSpans: poolSpans(units, req.pool, new Set(), HARD_CUTOFF, new Set(sel.map((u) => u.id))),
  };
}

// ---------------------------------------------------------------------------------------------------------------------
// Output (one gzip JSON per sub-slice, C4; episodes as compact rows)

export const EPISODE_COLS = ['m', 'k', 't', 'leg', 'px', 'n', 'ph', 'sig', 'x', 'hold', 'pnl', 'br'] as const;

export interface SeriesCoverage {
  /** First and last day with a market file in the history (whole tarball), files in all. */
  first?: string; last?: string; files: number;
  /** Days of the slice's span [from, to), those with a market file and those with a trade-tape file. */
  spanDays: number; withFile: number; withTrades: number;
  /** Span days with no market file (with a complete listing below, days on which no market closed). */
  missing: string[];
  /** The close-time range the downloader listed from Kalshi and stored completely (<S>/.index.json "listed", set by
   *  research/history/kalshiHistory.ts only when a download run listed every settled market and stored each one).
   *  Absent when no download has finished: the download runs newest first and can stop at its time budget. */
  listed?: { from: string; to: string };
  /** The close times this slice reads: [its first day minus the sim's lookback, its last day plus CLOSE_TAIL_DAYS),
   *  cut at the hard cutoff. The history must be listed completely over it. */
  need?: { from: string; to: string };
  /** Market lines closing in `need` (torn lines skipped), those stored never traded or rejected by the API (no tape is
   *  fetched for them), and traded ones without a tape line in trades/ (the tape download is unfinished; first 20). */
  markets?: number; untraded?: number; tapesMissing?: number; tapesMissingTickers?: string[];
}

export interface Coverage {
  span: [string, string];
  /** Per series, from the extracted history (null when the run was given no --hist). */
  series: Record<string, SeriesCoverage> | null;
  /** Owned matches, and those whose start was not published (their unit and pool use the earliest market-line time). */
  matches: number;
  noPublishedStart: number;
  noPublishedStartEvents: string[];
  /** Tennis match tickers with book or trade lines but no market line in what the sim read (lost matches). */
  lostTickers?: number;
  /** The sim's feed bookkeeping (SweepResult): R feed outages (gaps, their ms, those found on blind days), day files that
   *  show or hide the feed's liveness, and grids not delivered to family B because their day was already released. */
  feed?: { gaps: number; gapMs: number; blindGaps: number; liveDays: number; blindDays: number; lateGrids: number };
}

export interface ShardMeta {
  simVersion: string; stage: string; pool: Pool; run: string; k: number; j: number; shards: number; subShards: number;
  from: string; to: string; units: string[]; dataVersion: string; coverage: Coverage; requestSha: string; families: Array<'A' | 'B'>;
  [extra: string]: unknown;
}

export interface ShardOut {
  meta: ShardMeta;
  matchList: Array<MatchInfo & { pool: Pool; unit?: string }>;
  runs: Array<Omit<SimRun, 'episodes'> & { episodes: unknown[][]; stick?: true }>;
  familyB?: FamilyBExport;
}

/** Each complete line of a JSON-lines file (a torn last line, with no newline and no closing brace, is skipped). */
function eachLine(file: string, f: (line: string) => void): void {
  if (!fs.existsSync(file)) return;
  const text = fs.readFileSync(file, 'utf8');
  for (let start = 0; start < text.length;) {
    let end = text.indexOf('\n', start);
    if (end === -1) end = text.length;
    if (end > start) f(text.slice(start, end));
    start = end + 1;
  }
}

/** A stored market line's ticker and flags without parsing its candles (research/history/kalshiHistory.ts storedOf:
 *  candles are objects of numbers, so the first ']' after "candles" closes the array and the flags follow it). */
function storedMarket(line: string): { ticker: string; untraded: boolean } | undefined {
  try {
    const at = line.indexOf(',"candles":[');
    let head: { ticker?: unknown; noVolume?: unknown; error?: unknown }, flags: { noVolume?: unknown; error?: unknown } = {};
    if (at < 0) head = JSON.parse(line);
    else {
      head = JSON.parse(`${line.slice(0, at)}}`);
      const tail = line.slice(line.indexOf(']', at) + 1);
      flags = tail.startsWith(',') ? JSON.parse(`{${tail.slice(1)}`) : {};
    }
    if (typeof head.ticker !== 'string' || !head.ticker) return undefined;
    return { ticker: head.ticker, untraded: Boolean(head.noVolume || head.error || flags.noVolume || flags.error) };
  } catch { return undefined; }
}

/** Coverage of one series directory of the extracted history (<hist>/<S>/<day>.jsonl, trades/<day>.jsonl, .index.json)
 *  for a slice [from, to): day files over the span, the downloader's complete-listing record, and the trade tapes of
 *  every traded market closing in the span the slice reads (seriesCoverageProblems says what must hold). */
export function seriesCoverage(dir: string, from: string, to: string, lookbackDays = 1): SeriesCoverage {
  const days = (d: string) => (fs.existsSync(d) ? fs.readdirSync(d).filter((f) => /^\d{4}-\d{2}-\d{2}\.jsonl$/.test(f)).map((f) => f.slice(0, 10)).sort() : []);
  const all = days(dir), tr = new Set(days(path.join(dir, 'trades'))), have = new Set(all);
  const c: SeriesCoverage = { ...(all.length ? { first: all[0], last: all[all.length - 1] } : {}), files: all.length, spanDays: 0, withFile: 0, withTrades: 0, missing: [] };
  for (let t = Date.parse(from); t < Date.parse(to); t += DAY) {
    const d = dayOf(t);
    c.spanDays++;
    if (have.has(d)) c.withFile++; else c.missing.push(d);
    if (tr.has(d)) c.withTrades++;
  }
  try {
    const l = (JSON.parse(fs.readFileSync(path.join(dir, '.index.json'), 'utf8')) as { listed?: { from?: unknown; to?: unknown } }).listed;
    if (l && Number.isFinite(l.from) && Number.isFinite(l.to)) c.listed = { from: new Date(l.from as number).toISOString(), to: new Date(l.to as number).toISOString() };
  } catch { /* no index, or a damaged one: no complete-listing record */ }
  const needFrom = Date.parse(from) - lookbackDays * DAY, needTo = Math.min(Date.parse(to) + CLOSE_TAIL_DAYS * DAY, HARD_CUTOFF);
  c.need = { from: new Date(needFrom).toISOString(), to: new Date(needTo).toISOString() };
  let markets = 0, untraded = 0;
  const missing: string[] = [];
  for (let t = needFrom; t < needTo; t += DAY) {
    const d = dayOf(t);
    if (!have.has(d)) continue;
    // The downloader files a market's tape under its close day, the day of its market line.
    const tapes = new Set<string>();
    eachLine(path.join(dir, 'trades', `${d}.jsonl`), (line) => {
      if (line.startsWith('{"ticker":"') && line.endsWith('}')) { const e = line.indexOf('"', 11); if (e > 11) tapes.add(line.slice(11, e)); }
    });
    eachLine(path.join(dir, `${d}.jsonl`), (line) => {
      const m = storedMarket(line);
      if (!m) return;
      markets++;
      if (m.untraded) untraded++;
      else if (!tapes.has(m.ticker)) missing.push(m.ticker);
    });
  }
  Object.assign(c, { markets, untraded, tapesMissing: missing.length, tapesMissingTickers: missing.slice(0, 20) });
  return c;
}

/** What must hold of a series' history over a slice before its results count: the download's complete listing covers
 *  every close time the slice reads (so a day without a market file is a day on which no market closed, not one the
 *  download never reached), and every traded market closing then has its trade tape (else its match would be dropped
 *  as "no tape", A5, for want of a download). Empty = complete. */
export function seriesCoverageProblems(series: string, c: SeriesCoverage | undefined): string[] {
  if (!c) return [`${series}: no coverage record (the history of this series was not read)`];
  if (!c.need || c.tapesMissing === undefined) return [`${series}: the coverage record has no completeness fields (written by an older sweep)`];
  const p: string[] = [];
  const span = `${c.need.from.slice(0, 16)} to ${c.need.to.slice(0, 16)} UTC`;
  if (!c.listed) p.push(`${series}: the history holds no complete-download record (.index.json "listed"): no Tennis TA data download has yet listed and stored every settled market (it runs newest first and stops at its budget). Run that workflow until a download finishes, then run the sweep again`);
  else if (c.listed.from > c.need.from || c.listed.to < c.need.to) p.push(`${series}: the history is complete for closes ${c.listed.from.slice(0, 16)} to ${c.listed.to.slice(0, 16)} UTC only, and the slice reads ${span}`);
  if (c.tapesMissing > 0) p.push(`${series}: ${c.tapesMissing} traded market(s) closing ${span} have no trade tape (${(c.tapesMissingTickers ?? []).slice(0, 5).join(', ')}${c.tapesMissing > 5 ? ', ...' : ''}): the tape download is unfinished`);
  return p;
}

/** The series named in a data version ("KXATPMATCH:sha256:<hex>,KXWTAMATCH:sha256:<hex>"). */
export const seriesOfDataVersion = (v: string | undefined): string[] => (v ?? '').split(',').map((x) => /^([A-Z0-9]+):sha256:[0-9a-f]+$/.exec(x.trim())?.[1]).filter((x): x is string => Boolean(x));

/** The report gate's history check: every shard file read the history (--hist), and every series it read, and every
 *  series its data version names, is complete over the slice (seriesCoverageProblems). */
export function coverageProblems(metas: Array<{ file: string; meta: ShardMeta }>): string[] {
  const p: string[] = [];
  for (const { file, meta } of metas) {
    const cs = meta.coverage?.series;
    if (!cs) { p.push(`${file}: no history coverage (the slice ran without --hist)`); continue; }
    for (const s of [...new Set([...Object.keys(cs), ...seriesOfDataVersion(meta.dataVersion)])].sort()) for (const x of seriesCoverageProblems(s, cs[s])) p.push(`${file}: ${x}`);
  }
  return p;
}

function gitSha(): string {
  try { return execSync('git rev-parse HEAD', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim(); } catch { return process.env.GITHUB_SHA ?? 'unknown'; }
}

const eastern = (t: number) => new Date(t).toLocaleString('en-US', { timeZone: 'America/New_York', hour12: false });

/** Accept only a requestable pool here too (the workflow's prep already refused anything else). */
export function assertPool(pool: string): Pool {
  if (!REQUESTABLE_POOLS.includes(pool as Pool)) {
    throw new Error(pool === 'check' || pool === 'sealed'
      ? `pool '${pool}' needs an openings-ledger entry naming its units (Amendment 1, A3); none exists yet`
      : `pool must be one of ${REQUESTABLE_POOLS.join(', ')}, got '${pool}'`);
  }
  return pool as Pool;
}

/** One sub-slice (the run command): sweep its units, write its shard file (C4). */
export async function cmdRun(a: Args): Promise<void> {
  const unitsText = fs.readFileSync(a.units, 'utf8');
  const units: Unit[] = JSON.parse(unitsText);
  const bad = verifyUnits(units);
  if (bad.length) throw new Error(`unit table: ${bad.slice(0, 10).join('; ')}`);
  // Opened sealed units and lockbox weeks come only from the openings ledger, which does not exist yet: none here.
  const opened = new Set<string>();
  const pool = assertPool(a.pool ?? 'disc');
  const stratum = (a.stratum ?? 'H') as 'H' | 'R';
  if (stratum !== 'H' && stratum !== 'R') throw new Error(`stratum must be H or R, got ${a.stratum}`);
  const stage = String(a.stage ?? '');
  const specs = specsFor(stage, stratum, a.specs ?? STAGE2_SPECS);
  const sticks = new Set(specs.filter((s) => s.stick).map((s) => s.id));
  const byId = new Map(units.map((u) => [u.id, u]));
  const unitIds = a['units-list'] ? a['units-list'].split(',').filter(Boolean)
    : units.filter((u) => u.start >= Date.parse(a.from) && u.start < Date.parse(a.to)).map((u) => u.id);
  for (const id of unitIds) if (!byId.has(id)) throw new Error(`--units-list: unit ${id} is not in ${a.units}`);
  if (!unitIds.length) throw new Error(`no unit to sweep in [${a.from}, ${a.to})`);
  const unitSet = new Set(unitIds);
  const feeAt = a.fees ? feeLookup(JSON.parse(fs.readFileSync(a.fees, 'utf8'))) : undefined;
  const familyB = a['family-b'] === 'true';
  // The stratum is given up front: a slice with no owned two-market match has no grid to take it from, and exportCells
  // refuses a study without one.
  const study = familyB ? new SignalStudy({ ...FAMILY_B, stratum, ...(stratum === 'H' ? { bars: H_BARS } : {}) }) : undefined;
  // The start the sim used for ownership (published, else the earliest market-line time): family B's unit comes from it,
  // so a grid lands in the same unit as its matchList row.
  const startOf = new Map<string, number>();
  const gridPublished = new Map<string, boolean>();
  const lookback = lookbackOf(stratum);
  // History coverage first (it reads the slice's day files once, before the sweep's memory peak). The report gate refuses
  // a slice whose history is incomplete (coverageProblems); the shard job checks the same before it sweeps.
  const series = (a.series ?? 'KXATPMATCH,KXWTAMATCH').split(',');
  const seriesCov = a.hist ? Object.fromEntries(series.map((s) => [s, seriesCoverage(path.join(a.hist!, s), a.from, a.to, lookback)])) : null;
  for (const [s, c] of Object.entries(seriesCov ?? {})) for (const x of seriesCoverageProblems(s, c)) console.warn(`[tennis-ta] history incomplete: ${x}`);
  const t0 = Date.now();
  const r = await runSweep({
    dir: a.replay, fromDay: a.from, toDay: a.to, lookbackDays: lookback, stratum, specs, feeAt,
    admit: (m) => {
      const u = unitOf(m.start, units);
      const ok = u !== undefined && unitSet.has(u) && poolOf(m.start, m.closeTime, units, opened) === pool;
      if (ok && study) startOf.set(m.event, m.start);
      return ok;
    },
    onGrid: study ? (g: MatchGrid) => {
      const s = startOf.get(g.event) ?? g.start;
      g.unit = unitOf(s, units);
      // The sim sets startPublished on every grid (start = the published start, else the earliest market-line time); the
      // comparison below is only a fallback for a grid that lacks it.
      g.startPublished ??= g.start === s;
      gridPublished.set(g.event, g.startPublished);
      startOf.delete(g.event);
      study.addMatch(g);
    } : undefined,
    log: (m) => console.log(`[tennis-ta] ${m}`),
  });
  const matchList = r.matchList.map((m) => ({ ...m, pool: poolOf(m.start, m.close, units, opened), unit: unitOf(m.start, units) }));
  const noStart = matchList.filter((m) => !m.startPublished);
  const coverage: Coverage = {
    span: [a.from, a.to],
    series: seriesCov,
    matches: matchList.length, noPublishedStart: noStart.length, noPublishedStartEvents: noStart.slice(0, 50).map((m) => m.event), lostTickers: r.lost,
    feed: { gaps: r.gaps, gapMs: r.gapMs, blindGaps: r.blindGaps, liveDays: r.liveDays, blindDays: r.blindDays, lateGrids: r.lateGrids },
  };
  let gridStartMismatch = 0;
  for (const m of matchList) { const g = gridPublished.get(m.event); if (g !== undefined && g !== m.startPublished) gridStartMismatch++; }
  const exportB = study?.exportCells();
  const out: ShardOut = {
    meta: {
      simVersion: SIM_VERSION, stage, pool, run: a.run ?? process.env.GITHUB_RUN_ID ?? 'local',
      k: Number(a.k ?? 0), j: Number(a.j ?? 0), shards: Number(a.shards ?? 1), subShards: Number(a['sub-shards'] ?? 1),
      from: a.from, to: a.to, units: unitIds, dataVersion: a['data-version'] ?? 'unversioned', coverage,
      requestSha: a.request ? sha256(fs.readFileSync(a.request)) : 'none', families: familyB ? ['A', 'B'] : ['A'],
      // Bookkeeping beyond C4 (sim_version is the name the report read before C4).
      sim_version: SIM_VERSION, sha: gitSha(), unitsSha: sha256(unitsText), stratum, lookbackDays: lookback,
      evidence: stratum === 'H' ? 'history, synthetic depth' : 'recorded books', doge_excluded: true, configs: specs.length,
      sticks: [...sticks], poolSpans: poolSpans(units, pool, opened, HARD_CUTOFF, unitSet),
      stateRestarts: 'cross-match state (pacer, caps, placebo streams) restarts at this slice\'s first unit edge',
      matches: r.matches, oneLegged: r.oneLegged, unresolved: r.unresolved, decisions: r.decisions, ms: Date.now() - t0,
      ...(study ? { familyBGrids: gridPublished.size, familyBStartMismatch: gridStartMismatch } : {}),
      written_utc: new Date().toISOString(), written_eastern: eastern(Date.now()), episodeCols: EPISODE_COLS,
    },
    matchList,
    runs: r.runs.map((x) => ({ ...x, ...(sticks.has(x.id) ? { stick: true as const } : {}),
      episodes: x.episodes.map((e) => EPISODE_COLS.map((c) => (e as unknown as Record<string, unknown>)[c] ?? 0)) })),
    ...(exportB ? { familyB: exportB } : {}),
  };
  fs.mkdirSync(path.dirname(path.resolve(a.out)), { recursive: true });
  fs.writeFileSync(a.out, zlib.gzipSync(JSON.stringify(out)));
  console.log(`[tennis-ta] wrote ${a.out}: ${r.matches} matches (${noStart.length} without a published start), ${unitIds.length} unit(s), ${specs.length} configs${exportB ? `, family B ${exportB.cells.length} cells` : ''}, ${r.decisions} decisions, ${((Date.now() - t0) / 60_000).toFixed(1)} min`);
}

// ---------------------------------------------------------------------------------------------------------------------
// The report job's gate: every planned shard file present exactly once, from one run, one request, one data version

/** The meta object at the head of a shard file, read without inflating the rest (JSON.stringify wrote meta first). */
export async function readShardMeta(file: string, maxBytes = 64 << 20): Promise<ShardMeta> {
  const src = fs.createReadStream(file);
  const gz = src.pipe(zlib.createGunzip());
  const chunks: Buffer[] = [];
  const head = Buffer.from('{"meta":');
  let len = 0, depth = 0, inStr = false, esc = false, end = -1;
  try {
    for await (const c of gz as AsyncIterable<Buffer>) {
      const base = len;
      chunks.push(c);
      len += c.length;
      for (let i = 0; i < c.length; i++) {
        const pos = base + i;
        if (pos < head.length) { if (c[i] !== head[pos]) throw new Error(`${file}: not a shard file (it does not start with {"meta":)`); continue; }
        const b = c[i];
        if (inStr) { if (esc) esc = false; else if (b === 0x5c) esc = true; else if (b === 0x22) inStr = false; continue; }
        if (b === 0x22) inStr = true;
        else if (b === 0x7b || b === 0x5b) depth++;
        else if (b === 0x7d || b === 0x5d) { depth--; if (depth === 0) { end = pos + 1; break; } }
      }
      if (end >= 0) break;
      if (len > maxBytes) throw new Error(`${file}: meta is longer than ${maxBytes} bytes`);
    }
  } finally { gz.destroy(); src.destroy(); }
  if (end < 0) throw new Error(`${file}: the meta object never closes`);
  return JSON.parse(Buffer.concat(chunks).subarray(head.length, end).toString('utf8')) as ShardMeta;
}

export interface CheckSummary {
  run: string; files: number; dataVersion: string; simVersion: string; requestSha: string; stage: string; pool: string;
  families: string[]; shards: number; subSlices: number; units: number; matches: number; noPublishedStart: number;
  /** Per series over every slice: history day files, the download's complete listing (one tarball, so one value) and
   *  traded markets without a tape (summed over slices; neighbouring slices read a few of the same days). */
  series: Record<string, { first?: string; last?: string; spanDays: number; missing: string[]; listed?: { from: string; to: string }; tapesMissing: number }>;
}

/** Every problem with a run's shard set: `listing` = the names in the run's Drive shard folder (one line each, as
 *  rclone lsf prints them, duplicates included), `metas` = the metas of the files copied down. */
export function checkShards(prep: Prep, listing: string[], metas: Array<{ file: string; meta: ShardMeta }>, run: string): { problems: string[]; summary: CheckSummary } {
  const p: string[] = [];
  const count = new Map<string, number>();
  for (const n of listing.map((x) => x.trim()).filter(Boolean)) count.set(n, (count.get(n) ?? 0) + 1);
  const expected = new Set(prep.expected);
  for (const n of prep.expected) {
    const c = count.get(n) ?? 0;
    if (c === 0) p.push(`${n}: missing on Drive`);
    else if (c > 1) p.push(`${n}: ${c} copies on Drive`);
  }
  for (const n of count.keys()) if (!expected.has(n)) p.push(`${n}: not in the plan`);
  const read = new Set(metas.map((m) => m.file));
  for (const n of prep.expected) if (!read.has(n)) p.push(`${n}: not copied down`);
  const one = (key: string, vals: unknown[]) => {
    const s = new Set(vals.map((v) => JSON.stringify(v)));
    if (s.size > 1) p.push(`${key} differs across shards: ${[...s].join(' / ')}`);
  };
  const ms = metas.map((m) => m.meta);
  one('dataVersion', ms.map((m) => m.dataVersion));
  if (ms.some((m) => !m.dataVersion || m.dataVersion === 'unversioned')) p.push('a shard has no data version');
  one('simVersion', ms.map((m) => m.simVersion));
  one('coverage.series first/last', ms.map((m) => m.coverage?.series && Object.fromEntries(Object.entries(m.coverage.series).map(([s, c]) => [s, [c.first, c.last, c.files]]))));
  const unitSeen = new Map<string, string>();
  for (const { file, meta } of metas) {
    const want = (key: string, got: unknown, exp: unknown) => { if (JSON.stringify(got) !== JSON.stringify(exp)) p.push(`${file}: ${key} ${JSON.stringify(got)}, expected ${JSON.stringify(exp)}`); };
    want('simVersion', meta.simVersion, SIM_VERSION);
    want('run', String(meta.run), run);
    want('requestSha', meta.requestSha, prep.requestSha);
    want('stage', meta.stage, prep.stage);
    want('pool', meta.pool, prep.pool);
    want('families', meta.families, prep.familyB ? ['A', 'B'] : ['A']);
    want('shards', meta.shards, prep.plan.length);
    if (meta.unitsSha !== undefined) want('unitsSha', meta.unitsSha, prep.unitsSha);
    const m = /^a-s(\d)-(\d+)-(\d+)\.json\.gz$/.exec(file);
    if (!m) { p.push(`${file}: not a shard file name`); continue; }
    const k = Number(m[2]), j = Number(m[3]);
    want('k', meta.k, k);
    want('j', meta.j, j);
    const sub = prep.subPlans[k]?.[j];
    if (!sub) { p.push(`${file}: shard ${k} has no sub-slice ${j} in the plan`); continue; }
    want('subShards', meta.subShards, prep.subPlans[k].length);
    want('from', meta.from, sub.from);
    want('to', meta.to, sub.to);
    want('units', meta.units, sub.units);
    if (prep.familyB && !(meta.families ?? []).includes('B')) p.push(`${file}: family B missing`);
    for (const u of meta.units ?? []) {
      if (unitSeen.has(u)) p.push(`${file}: unit ${u} also swept by ${unitSeen.get(u)}`);
      unitSeen.set(u, file);
    }
  }
  for (const u of prep.units) if (!unitSeen.has(u) && metas.length) p.push(`unit ${u}: swept by no shard`);
  // Coverage summed over the shards (spans of neighbouring slices share a day; the union is reported).
  const series: CheckSummary['series'] = {};
  const spanDays: Record<string, Set<string>> = {}, missing: Record<string, Set<string>> = {};
  for (const meta of ms) for (const [s, c] of Object.entries(meta.coverage?.series ?? {})) {
    const cur = (series[s] ??= { first: c.first, last: c.last, spanDays: 0, missing: [], tapesMissing: 0 });
    if (c.listed && !cur.listed) cur.listed = c.listed;
    cur.tapesMissing += c.tapesMissing ?? 0;
    if (c.first && (!cur.first || c.first < cur.first)) cur.first = c.first;
    if (c.last && (!cur.last || c.last > cur.last)) cur.last = c.last;
    const [f, t] = meta.coverage.span;
    for (let x = Date.parse(f); x < Date.parse(t); x += DAY) (spanDays[s] ??= new Set()).add(dayOf(x));
    for (const d of c.missing) (missing[s] ??= new Set()).add(d);
  }
  for (const s of Object.keys(series)) { series[s].spanDays = spanDays[s]?.size ?? 0; series[s].missing = [...(missing[s] ?? [])].sort(); }
  const first = ms[0];
  return {
    problems: p,
    summary: {
      run, files: metas.length, dataVersion: first?.dataVersion ?? '', simVersion: first?.simVersion ?? '', requestSha: prep.requestSha, stage: prep.stage, pool: prep.pool,
      families: prep.familyB ? ['A', 'B'] : ['A'], shards: prep.plan.length, subSlices: prep.expected.length, units: unitSeen.size,
      matches: ms.reduce((s, m) => s + (m.coverage?.matches ?? 0), 0), noPublishedStart: ms.reduce((s, m) => s + (m.coverage?.noPublishedStart ?? 0), 0), series,
    },
  };
}

async function cmdCheck(a: Args): Promise<void> {
  const prep = JSON.parse(fs.readFileSync(a.prep!, 'utf8')) as Prep;
  const listing = fs.readFileSync(a.listing!, 'utf8').split('\n');
  const names = fs.readdirSync(a.dir!).filter((f) => f.endsWith('.json.gz')).sort();
  const metas: Array<{ file: string; meta: ShardMeta }> = [];
  const p: string[] = [];
  for (const f of names) {
    try { metas.push({ file: f, meta: await readShardMeta(path.join(a.dir!, f)) }); } catch (e) { p.push((e as Error).message); }
  }
  const r = checkShards(prep, listing, metas, a.run ?? process.env.GITHUB_RUN_ID ?? 'local');
  r.problems.unshift(...p);
  // The history must be complete over every slice: an unfinished download is never scored.
  r.problems.push(...coverageProblems(metas));
  if (a.out) fs.writeFileSync(a.out, JSON.stringify({ ...r.summary, problems: r.problems }, null, 1) + '\n');
  const s = r.summary;
  console.log(`[tennis-ta] ${s.files} shard file(s) of ${prep.expected.length} planned (${s.shards} shards), ${s.units} unit(s), data ${s.dataVersion}, ${s.simVersion}`);
  console.log(`[tennis-ta] ${s.matches} owned matches, ${s.noPublishedStart} without a published start (their unit and pool use the earliest market-line time)`);
  for (const [k, c] of Object.entries(s.series)) {
    console.log(`[tennis-ta] ${k}: history ${c.first ?? '-'} to ${c.last ?? '-'}, ${c.spanDays - c.missing.length} of ${c.spanDays} swept days have a file${c.missing.length ? ` (missing ${c.missing.slice(0, 12).join(', ')}${c.missing.length > 12 ? ', ...' : ''})` : ''}; `
      + `complete listing ${c.listed ? `${c.listed.from.slice(0, 16)} to ${c.listed.to.slice(0, 16)} UTC` : 'none'}; ${c.tapesMissing} traded market(s) without a tape`);
  }
  if (r.problems.length) {
    for (const x of r.problems.slice(0, 60)) console.error(`::error::${x}`);
    throw new Error(`${r.problems.length} problem(s) with the shard set or its history: nothing is scored or appended`);
  }
}

/** The coverage command: the history complete over [from, to) for every series, or exit 1 with the problems (the shard
 *  job runs it before it sweeps, so an unfinished download fails in minutes, not after the sweep). */
function cmdCoverage(a: Args): void {
  const stratum = (a.stratum ?? 'H') as 'H' | 'R';
  if (stratum !== 'H' && stratum !== 'R') throw new Error(`stratum must be H or R, got ${a.stratum}`);
  const p: string[] = [];
  for (const s of (a.series ?? 'KXATPMATCH,KXWTAMATCH').split(',').filter(Boolean)) {
    const c = seriesCoverage(path.join(a.hist!, s), a.from, a.to, lookbackOf(stratum));
    console.log(`[tennis-ta] ${s}: ${c.files} day file(s) ${c.first ?? '-'} to ${c.last ?? '-'}; complete listing ${c.listed ? `${c.listed.from.slice(0, 16)} to ${c.listed.to.slice(0, 16)} UTC` : 'none'}; `
      + `${c.markets} market(s) closing ${c.need!.from.slice(0, 10)} to ${c.need!.to.slice(0, 10)}, ${c.untraded} untraded, ${c.tapesMissing} traded without a tape`);
    p.push(...seriesCoverageProblems(s, c));
  }
  if (p.length) {
    for (const x of p) console.error(`::error::${x}`);
    throw new Error(`the history is incomplete over ${a.from} to ${a.to}: ${p.length} problem(s)`);
  }
}

export interface Args { [k: string]: string | undefined; from: string; to: string; out: string; replay: string; units: string }

function parseArgs(argv: string[]): Args {
  const a: Record<string, string> = {};
  for (let i = 0; i < argv.length; i++) if (argv[i].startsWith('--')) a[argv[i].slice(2)] = argv[i + 1]?.startsWith('--') || argv[i + 1] === undefined ? 'true' : argv[++i];
  return a as Args;
}

async function main(): Promise<void> {
  const [cmd, ...rest] = process.argv.slice(2);
  const a = parseArgs(rest);
  const loadUnits = (): Unit[] => JSON.parse(fs.readFileSync(a.units, 'utf8'));
  switch (cmd) {
    case 'units': {
      const u = buildUnits(a.from, a.to);
      const s = JSON.stringify(u, null, 1);
      if (a.out) fs.writeFileSync(a.out, s + '\n'); else console.log(s);
      console.error(`${u.length} units, ${u.filter((x) => x.sealed).length} sealed, ${u.filter((x) => x.slam).length} Slam units`);
      break;
    }
    case 'fees': {
      const eras = await fetchFeeEras((a.series ?? 'KXATPMATCH,KXWTAMATCH').split(','));
      fs.writeFileSync(a.out, JSON.stringify(eras, null, 1) + '\n');
      for (const [s, l] of Object.entries(eras)) console.log(`${s}: ${l.map((e) => `${new Date(e.from).toISOString()} taker x${e.fees.takerMultiplier} maker x${e.fees.makerMultiplier}`).join('; ') || 'no changes listed'}`);
      break;
    }
    case 'days': {
      const series = (a.series ?? 'KXATPMATCH,KXWTAMATCH').split(',');
      const r = await buildHistoryReplay({ historyDir: a.hist!, kalshiDir: a.hist, outDir: a.out, assets: [], fromDay: a.from, toDay: a.to, tennisSeries: series, synthetic: false, log: (m) => { if (!/day \d{4}-/.test(m)) console.log(`[replay] ${m}`); } });
      console.log(`[tennis-ta] replay days ${r.days} (written ${r.written}, skipped ${r.skipped}), tennis markets ${r.tennis ?? 0}`);
      break;
    }
    case 'prep': {
      const p = prepare(fs.readFileSync(a.request!, 'utf8'), fs.readFileSync(a.units, 'utf8'), a.specs ?? STAGE2_SPECS);
      if (a.out) fs.writeFileSync(a.out, JSON.stringify(p, null, 1) + '\n'); else console.log(JSON.stringify(p));
      console.error(`[tennis-ta] stage ${p.stage}, pool ${p.pool}, ${p.configs} configs${p.familyB ? ' + family B' : ''}, ${p.units.length} unit(s) from ${p.plan[0].from} to ${p.plan[p.plan.length - 1].to}, ${p.plan.length} shard(s) x up to ${SUB_SHARDS} sub-slices = ${p.expected.length} file(s)`);
      break;
    }
    case 'run':
      await cmdRun(a);
      break;
    case 'plan': {
      const pool = assertPool(a.pool ?? 'disc');
      console.log(JSON.stringify(planUnits(requestUnits(loadUnits(), pool, a.from, a.to), Number(a.shards ?? 8))));
      break;
    }
    case 'subplan': {
      const units = loadUnits(), byId = new Map(units.map((u) => [u.id, u]));
      const list = (a['units-list'] ?? '').split(',').filter(Boolean).map((id) => { const u = byId.get(id); if (!u) throw new Error(`unit ${id} is not in ${a.units}`); return u; });
      if (!list.length) throw new Error('subplan: --units-list is empty');
      console.log(JSON.stringify(planUnits(list, Number(a.parts ?? SUB_SHARDS))));
      break;
    }
    case 'check':
      await cmdCheck(a);
      break;
    case 'coverage':
      cmdCoverage(a);
      break;
    case 'pool-hours': {
      const s = poolSpans(loadUnits(), (a.pool ?? 'disc') as Pool);
      console.log(JSON.stringify(s));
      console.error(`${s.length} unit(s), ${s.reduce((x, u) => x + u.hours, 0).toFixed(0)} pool hours (embargoed time left out)`);
      break;
    }
    default:
      throw new Error(`unknown command ${cmd}: units | fees | days | prep | plan | subplan | run | coverage | check | pool-hours`);
  }
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) void main().catch((e) => { console.error(e instanceof Error ? e.stack ?? e.message : e); process.exitCode = 1; });
