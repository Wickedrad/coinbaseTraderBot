// Tennis TA rulebook trial: the sweep CLI the GitHub workflow runs (pre-registration and its amendments:
// /mnt/project-files/tennis-ta/preregistration.md; thread "Build a profitable tennis TA rulebook", Nov 5 2026). The request
// file format and the run mechanics are documented in research/tennis-ta/README.md.
//
//   units   --from D --to D [--out F]          the tournament-week unit table (Monday 05:00 UTC weeks, Slams whole), calendar only
//   fees    --series S,S --out F               Kalshi fee changes per series (GET /series/fee_changes, show_historical)
//   days    --hist DIR --out DIR --from D --to D --series S,S   build history replay days (research/history/historyReplay.ts)
//   prep    --request F --units F --out F [--specs F] [--openings F]   validate a sweep request and write the plan (shards
//           and sub-slices by unit); stage hold needs --openings (the openings ledger as read from Drive, empty if none)
//   plan    --units F --from D --to D --shards N [--pool disc|old|hold] [--stage 1|2|hold]   the shard plan alone (JSON)
//   subplan --units F --units-list U,U [--parts 4]               a shard's sub-slices (JSON; the same cut prep made)
//   run     --replay DIR --from D --to D --units-list U,U --stage 1|2|hold --pool disc|old|hold --units F --out F.json.gz
//           [--fees F] [--hist DIR] [--family-b true] [--data-version S] [--request F] [--run ID] [--k K --j J
//           --shards N --sub-shards M] [--specs F]
//   coverage --hist DIR --from D --to D [--series S,S] [--stratum H|R]   the history is complete over a span (exit 1 if not)
//   check   --dir DIR --listing F --prep F --run ID [--out F]   every planned shard file present once, one data version, and
//           the history complete over every slice (download listing and trade tapes)
//   pool-hours --units F [--pool disc|old|hold]   the pool's wall-clock intervals per unit (the embargo day left out)
//
// Pools (C9: the start era and HO-1, the project's held-out standard; registry README "Held-out standard HO-1"): history
// stops at Nov 5 02:00 UTC (Nov 4 9:00 PM EST) and starts at HISTORY_FROM (2025-06-18, Kalshi's first tennis match
// markets); a match is in a pool only if its start is in the history and both its start and its close are before the
// cutoff (and, with a later cutoff, every lockbox week it reaches is opened: L1 = Nov 6 05:00 to Nov 13 05:00 UTC, then
// 7-day steps). Units are Monday 05:00 UTC weeks with each Grand Slam as one unit; they are the bootstrap's blocks and the
// slicing's edges. Before about April 2026 Kalshi published no start time (occurrence_datetime) and settled on an older
// "advances past the round" rule, a different product: units starting before START_ERA_FROM are pool 'old' (stratum H0, a
// stress test for stage 2 finalists only). From START_ERA_FROM a match needs a published start ('nostart' otherwise:
// excluded and counted). HO-1: settings are chosen only on H-DEV ('disc': start-era matches closing before DEV_TO) and a
// frozen list is scored once on H-HOLD ('hold': matches starting from HOLD_FROM, 2026-08-01 to the cutoff, in 6
// consecutive folds with registry.py's edges); the matches in between (Jul 31 and those straddling it) are 'embargo'. A
// run scores one pool: 'disc' (stages 1 and 2), 'old' (stage 2) or 'hold' (stage hold only: the frozen spec list
// research/tennis-ta/hold-specs.json, refused when its hash is already in the openings ledger). The A3 hash seal and the
// dev-check pool are retired: the contiguous hold block replaces them (the old era needs no seal, since nothing is chosen
// there), and the unit table's legacy `sealed` flags are ignored.
//
// Slicing (C5): shards and their sub-slices are cut at unit edges, so a unit is never split and the cross-match state
// (the tennis-only pacer, the 25% / 10% caps, the coin-placebo stream, family B's placebo reservoir) restarts only at unit
// edges. A slice owns the matches whose start is in [from 00:00, to 00:00) UTC, whose unit is in its unit list and whose
// pool is the run's (a unit can hold matches of several pools: W-2026-07-27 holds disc, embargo and hold matches).

import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import { execSync } from 'child_process';
import { loadConfig, paperEnv } from '../bot/config';
import type { FeeSchedule } from '../bot/fees';
import { REPLAY_VERSION, buildHistoryReplay } from './history/historyReplay';
import { FEES, runSweep, type MatchInfo, type SimRun, type SimSpec } from './tennisTaSim';
import { SignalStudy } from './tennisTaSignals';
import type { FamilyBExport, MatchGrid } from './tennisTaTypes';

export const SIM_VERSION = 'tennis-ta-sim/3';
const DAY = 86_400_000;
const WEEK = 7 * DAY;
/** History and inventory stop here (Nov 4 9:00 PM EST). */
export const HARD_CUTOFF = Date.parse('2026-11-05T02:00:00Z');
/** Kalshi's tennis match history starts here (the first KXATPMATCH / KXWTAMATCH markets): a match starting earlier is out,
 *  and pool hours start here. */
export const HISTORY_FROM = Date.parse('2025-06-18T00:00:00Z');
/** L1 opens Nov 6 05:00 UTC (00:00 EST); lockbox weeks follow in 7-day steps (L2 Nov 13 05:00, ...). */
export const LOCKBOX_FROM = Date.parse('2026-11-06T05:00:00Z');
/** The start era (C6, C9): units starting from here are the product the bot trades (a published start time, the current
 *  settlement rule); units starting earlier are pool 'old' (stratum H0). A Monday 05:00 UTC unit start.
 *  PLACEHOLDER: it is fixed from the weekly inventory (the first week in which Kalshi published occurrence_datetime on
 *  nearly every match) before the first counting run, and a change of it is a new request commit. */
export const START_ERA_FROM = Date.parse('2026-04-27T05:00:00Z');
/** H-DEV ends here (C9): a start-era match is 'disc' (H-DEV, where every setting is chosen) only if it closes before
 *  Jul 31 00:00 UTC. */
export const DEV_TO = Date.parse('2026-07-31T00:00:00Z');
/** H-HOLD starts here (C9): a start-era match starting from Aug 1 00:00 UTC (and closing before the cutoff) is 'hold'. */
export const HOLD_FROM = Date.parse('2026-08-01T00:00:00Z');
/** H-HOLD in UTC days, inclusive, exactly as research/registry.py's H_HOLD (HO-1: 96 days in 6 consecutive folds). */
export const H_HOLD: readonly [string, string] = ['2026-08-01', '2026-11-04'];
export const HOLD_FOLDS = 6;
/** @deprecated Retired with the dev-check pool (C9: HO-1's hold block replaced it); no pool reads it. Kept only because
 *  tests/tennisTaData.test.ts (another owner's) still checks it is a week edge. */
export const CHECK_FROM = Date.parse('2026-09-14T05:00:00Z');
/** R: days before a slice's first day whose market lines the sim reads, so a match the bot listed early is not lost (C1).
 *  H reads one day back whatever is passed (history lists a match 30 min before its start): see lookbackOf. */
export const LOOKBACK_DAYS = 7;
/** Days before a slice's first day whose market lines the sim reads on each stratum (runSweep in research/tennisTaSim.ts):
 *  1 on H (the workflow builds replay days from that day on), LOOKBACK_DAYS on R. */
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
/** Stage hold's frozen spec list (C10): the candidates chosen on H-DEV, each with its F2 neighbour and coin placebo, and the
 *  production-default F1 control. */
export const HOLD_SPECS = 'research/tennis-ta/hold-specs.json';
/** The openings ledger (C10): one JSON line {hash, run, ts, ids, pool: 'hold'} per frozen list scored on H-HOLD. prep
 *  refuses a list whose hash is in it; the report job appends the run's line once its shard set is complete, before
 *  anything is scored (idempotent by run id). */
export const OPENINGS_LEDGER = 'gdrive:kalshi-bot-archive/models/tennis-ta/state/openings.jsonl';
/** The pools a request may name (C10): 'disc' (stages 1 and 2), 'old' (stage 2 finalists) and 'hold' (stage hold). */
export const REQUESTABLE_POOLS: ReadonlyArray<Pool> = ['disc', 'old', 'hold'];
/** The stages: 1 (the H grid), 2 (research/tennis-ta/stage2-specs.json) and hold (research/tennis-ta/hold-specs.json). */
export type Stage = '1' | '2' | 'hold';
export const STAGES: ReadonlyArray<Stage> = ['1', '2', 'hold'];

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

/** A unit: [start, end) between Monday 05:00 UTC edges, a Grand Slam whole. `sealed` is the retired A3 hash seal, kept in
 *  the committed table (models/tennis-ta/state/units.json) and ignored (C9: the hold block replaced it). */
export interface Unit { id: string; start: number; end: number; startDay: string; slam?: string; sealed?: boolean }

export interface SlamUnit { name: string; first: string; final: string; start: number; end: number }

/** Each Grand Slam of SLAMS as its one unit: [the Monday 05:00 UTC at or before its first day, the Monday 05:00 UTC after
 *  its final). */
export const slamUnits = (): SlamUnit[] => SLAMS.map(([name, first, final]) => ({
  name, first, final, start: mondayEdge(Date.parse(first) + 12 * 3_600_000), end: mondayEdge(Date.parse(final) + 12 * 3_600_000) + WEEK,
}));

/** The Monday 05:00 UTC at or before t. */
export function mondayEdge(t: number): number {
  const d = new Date(t - 5 * 3_600_000);
  const midnight = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  const back = (d.getUTCDay() + 6) % 7; // days since Monday
  return midnight - back * DAY + 5 * 3_600_000;
}

/** The unit table over [fromDay, toDay] (calendar only: no market data is read). */
export function buildUnits(fromDay: string, toDay: string): Unit[] {
  const slams = slamUnits();
  const units: Unit[] = [];
  const last = Date.parse(toDay) + DAY;
  for (let t = mondayEdge(Date.parse(fromDay)); t < last;) {
    const s = slams.find((x) => t >= x.start && t < x.end);
    const start = s ? Math.max(s.start, t) : t;
    const end = s ? s.end : t + WEEK;
    const startDay = dayOf(start);
    units.push({ id: s ? `${s.name}-${startDay}` : `W-${startDay}`, start, end, startDay, ...(s ? { slam: s.name } : {}) });
    t = end;
  }
  return units;
}

/** Integrity of a committed unit table: sorted, contiguous, Monday 05:00 UTC edges, ids as the calendar gives them, every
 *  unit as buildUnits gives it over the table's span, and each Grand Slam placed as SLAMS gives it (a Slam unit is a
 *  SLAMS entry's whole span, no week unit overlaps a Slam, and every Slam the table's span reaches is in it as one unit: a
 *  table that starts or ends inside a Slam is refused). A legacy `sealed` flag is ignored (C9). Returns the problems
 *  found (empty = sound). */
export function verifyUnits(units: Unit[]): string[] {
  const p: string[] = [];
  if (!Array.isArray(units) || !units.length) return ['the unit table is empty'];
  units.forEach((u, i) => {
    if (typeof u.id !== 'string' || !Number.isFinite(u.start) || !Number.isFinite(u.end) || !(u.end > u.start)) { p.push(`unit ${i}: malformed`); return; }
    if (mondayEdge(u.start) !== u.start || mondayEdge(u.end) !== u.end) p.push(`${u.id}: edges are not Monday 05:00 UTC`);
    if (u.startDay !== dayOf(u.start)) p.push(`${u.id}: startDay ${u.startDay} is not the start's day`);
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
    // Slam placement against SLAMS itself (buildUnits over the table's own span would accept a table cut inside a Slam).
    const slams = slamUnits(), first = units[0].start;
    for (const u of units) {
      if (u.slam !== undefined) {
        const s = slams.find((x) => x.name === u.slam && x.start === u.start);
        if (!s) p.push(`${u.id}: no Grand Slam ${u.slam} in SLAMS has its unit start on ${u.startDay}`);
        else if (s.end !== u.end) p.push(`${u.id}: Grand Slam ${s.name} (${s.first} to ${s.final}) is one unit to ${dayOf(s.end)}, not to ${dayOf(u.end)}`);
      } else {
        for (const s of slams) if (u.start < s.end && u.end > s.start) p.push(`${u.id}: a week unit overlapping Grand Slam ${s.name} (${s.first} to ${s.final}, one unit ${dayOf(s.start)} to ${dayOf(s.end)})`);
      }
    }
    for (const s of slams) {
      if (!(s.start < last && s.end > first)) continue;
      if (!units.some((u) => u.slam === s.name && u.start === s.start && u.end === s.end)) {
        p.push(`Grand Slam ${s.name} ${s.first} to ${s.final}: not in the table as one unit ${dayOf(s.start)} to ${dayOf(s.end)}${s.start < first || s.end > last ? ' (the table starts or ends inside it)' : ''}`);
      }
    }
  }
  return p;
}

/** C9: 'out' (outside the history, reaching the cutoff or an unopened lockbox week), 'old' (a unit before the start era:
 *  stratum H0, stress only), 'nostart' (a start-era match without a published start: excluded and counted), 'disc'
 *  (H-DEV: a start-era match closing before DEV_TO), 'embargo' (Jul 31 and the matches straddling it: neither disc nor
 *  hold) and 'hold' (H-HOLD: a start-era match starting from HOLD_FROM). */
export type Pool = 'old' | 'nostart' | 'disc' | 'embargo' | 'hold' | 'out';
export const POOLS: ReadonlyArray<Pool> = ['old', 'nostart', 'disc', 'embargo', 'hold', 'out'];
/** The pools with wall-clock hours (poolSpans): the scored ones. 'nostart' matches sit in disc or hold hours. */
export const SPAN_POOLS: ReadonlyArray<Pool> = ['old', 'disc', 'hold'];

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

/** A unit of the start era (its start from START_ERA_FROM): its matches need a published start. */
export const startEra = (u: Unit): boolean => u.start >= START_ERA_FROM;

/** The wall-clock part of a unit that belongs to a pool by time (C9), or undefined: the unit's span cut to the history
 *  [HISTORY_FROM, cutoff), and for the start era cut to H-DEV's [.., DEV_TO) ('disc'), the embargo day [DEV_TO,
 *  HOLD_FROM) ('embargo': in no scored pool's hours) or H-HOLD's [HOLD_FROM, ..) ('hold'); 'old' takes the whole
 *  (history-cut) span of a unit before the start era. 'nostart' and 'out' have no time of their own. */
export function poolInterval(u: Unit, pool: Pool, cutoff = HARD_CUTOFF): [number, number] | undefined {
  let lo = Math.max(u.start, HISTORY_FROM), hi = Math.min(u.end, cutoff);
  if (pool === 'old') { if (startEra(u)) return undefined; }
  else if (pool === 'disc') { if (!startEra(u)) return undefined; hi = Math.min(hi, DEV_TO); }
  else if (pool === 'embargo') { if (!startEra(u)) return undefined; lo = Math.max(lo, DEV_TO); hi = Math.min(hi, HOLD_FROM); }
  else if (pool === 'hold') { if (!startEra(u)) return undefined; lo = Math.max(lo, HOLD_FROM); }
  else return undefined;
  return lo < hi ? [lo, hi] : undefined;
}

/** The pools a unit holds time of ('old', 'disc', 'embargo', 'hold'; W-2026-07-27 holds disc, embargo and hold), or
 *  ['out'] (the same sets as the report's unit_pools). */
export function unitPools(u: Unit, cutoff = HARD_CUTOFF): Pool[] {
  const ps = (['old', 'disc', 'embargo', 'hold'] as Pool[]).filter((p) => poolInterval(u, p, cutoff) !== undefined);
  return ps.length ? ps : ['out'];
}

/** The match as poolOf reads it: start (published, else the earliest market-line time), close (the latest close of its
 *  markets) and whether the start was published (MatchInfo.startPublished). */
export interface PoolMatch { start: number; close: number; startPublished: boolean }

/** The pool a match belongs to (C9, in this order): 'out' unless its start is in the history and both its start and its
 *  close are before the cutoff, and out if any lockbox week it reaches is unopened (only a cutoff after LOCKBOX_FROM lets
 *  a match reach one); 'out' outside the unit table; 'old' when its unit starts before the start era; 'nostart' for a
 *  start-era match without a published start; 'disc' (H-DEV) when it starts and closes before DEV_TO; 'hold' (H-HOLD)
 *  when it starts and closes from HOLD_FROM; else 'embargo' (Jul 31 and the matches straddling an edge; for a match
 *  that starts before it closes, as every well-formed match does, disc is close < DEV_TO and hold is start >= HOLD_FROM).
 *  `opened` holds the lockbox ids ('L1', 'L2', ...) opened through the openings ledger (none: the cutoff is before L1). */
export function poolOf(m: PoolMatch, units: Unit[], opened: Set<string> = new Set(), cutoff = HARD_CUTOFF): Pool {
  const { start, close } = m;
  if (!(start >= HISTORY_FROM) || !(start < cutoff) || !(close < cutoff)) return 'out';
  if (close >= LOCKBOX_FROM) {
    const first = Math.floor((Math.max(start, LOCKBOX_FROM) - LOCKBOX_FROM) / WEEK), last = Math.floor((close - LOCKBOX_FROM) / WEEK);
    for (let i = first; i <= last; i++) if (!opened.has(`L${i + 1}`)) return 'out';
  }
  const u = units.find((x) => start >= x.start && start < x.end);
  if (!u) return 'out';
  if (!startEra(u)) return 'old';
  if (m.startPublished !== true) return 'nostart';
  if (Math.max(start, close) < DEV_TO) return 'disc';
  if (Math.min(start, close) >= HOLD_FROM) return 'hold';
  return 'embargo';
}

export const unitOf = (start: number, units: Unit[]): string | undefined => units.find((x) => start >= x.start && start < x.end)?.id;

/** Python's round() (half to even), as research/registry.py's ho1_fill computes its fold edges. */
const pyRound = (x: number): number => {
  const f = Math.floor(x), d = x - f;
  return d > 0.5 ? f + 1 : d < 0.5 ? f : f % 2 === 0 ? f : f + 1;
};

/** HO-1's fold edges over H-HOLD, exactly as research/registry.py's ho1_fill: span = H_HOLD's days (96), edge i = its
 *  first day + round(i * span / 6) days for i = 0..6 (UTC days; fold i is [edge i-1, edge i), and the last fold also
 *  holds H_HOLD's last day). */
export function holdFoldEdges(): string[] {
  const d0 = Date.parse(H_HOLD[0]), span = Math.round((Date.parse(H_HOLD[1]) - d0) / DAY) + 1;
  return Array.from({ length: HOLD_FOLDS + 1 }, (_, i) => dayOf(d0 + pyRound((i * span) / HOLD_FOLDS) * DAY));
}

/** The HO-1 fold (1..6) of a UTC match day, or null outside H_HOLD (a hold match on Nov 5 UTC, 00:00 to the 02:00
 *  cutoff, is in pool hold but in no registry fold: ho1_fill reads H_HOLD's days only). */
export function holdFold(day: string): number | null {
  if (!(day >= H_HOLD[0] && day <= H_HOLD[1])) return null;
  const e = holdFoldEdges();
  for (let i = 0; i < HOLD_FOLDS; i++) if (day >= e[i] && day < e[i + 1]) return i + 1;
  return HOLD_FOLDS;
}

/** The six folds as day ranges (to inclusive), for the plan, the shard meta and the report. */
export function holdFolds(): Array<{ fold: number; from: string; to: string }> {
  const e = holdFoldEdges();
  return Array.from({ length: HOLD_FOLDS }, (_, i) => ({ fold: i + 1, from: e[i], to: i === HOLD_FOLDS - 1 ? H_HOLD[1] : dayOf(Date.parse(e[i + 1]) - DAY) }));
}

export interface PoolSpan { unit: string; start: number; end: number; intervals: Array<[number, number]>; hours: number }

/** The wall-clock time each unit of a pool contributes to $/h (section 8: every hour counts, matches or not): the unit's
 *  part of the pool (poolInterval: cut to the history [HISTORY_FROM, cutoff), and in the start era to H-DEV or H-HOLD,
 *  so the embargo day is in no scored pool's hours). The report clips these intervals to the data span; every pool unit
 *  is listed whether or not it holds a match. The scored pools with hours are SPAN_POOLS ('old', 'disc', 'hold');
 *  'embargo' gives the excluded day; 'nostart' matches sit in disc or hold hours. `only` limits the list to the given
 *  unit ids. */
export function poolSpans(units: Unit[], pool: Pool, cutoff = HARD_CUTOFF, only?: Set<string>): PoolSpan[] {
  const out: PoolSpan[] = [];
  for (const u of units) {
    if (only && !only.has(u.id)) continue;
    const iv = poolInterval(u, pool, cutoff);
    if (iv) out.push({ unit: u.id, start: u.start, end: u.end, intervals: [iv], hours: (iv[1] - iv[0]) / 3_600_000 });
  }
  return out;
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
/** The harness rules research/tennisTaSim.ts reads from a spec's overrides (the HARNESS_* list SimSpec.overrides
 *  documents; ConfigSim reads each as spec.overrides.HARNESS_*, and tests/tennisTaSweep.test.ts holds this list to the
 *  sim's source), each with its value check. Any other HARNESS_* key would be ignored by the sim, so it is refused. */
export const HARNESS_RULES: Readonly<Record<string, (v: OverrideValue) => string | undefined>> = {
  HARNESS_PACER: (v) => (v === 'tennis' || v === 'off' ? undefined : `must be 'tennis' or 'off'`),
  HARNESS_LOSER_STOP: numIn(0, 1),
  HARNESS_BANKROLL: numIn(0, 1e6, true),
  HARNESS_FEE_MULT: numIn(0, 10),
  HARNESS_LATENCY_MS: numIn(0, 60_000),
};
/** The stress adversaries and measuring settings (section 7) at production's values: never a hypothesis, so only a
 *  measuring stick moves one off its default (the report's STICK_KEYS in research/tennis_ta_report.py, whose check_runs
 *  refuses any other run that does; tests/tennisTaSweep.test.ts holds the two lists together). */
export const STICK_KEYS: Readonly<Record<string, OverrideValue>> = {
  HARNESS_FEE_MULT: 1, HARNESS_LATENCY_MS: 0, HARNESS_PACER: 'tennis', HARNESS_BANKROLL: 200, TENNIS_END_LOSER_CUT: true,
};
/** What else a measuring stick may set: the harness loser stop (an exits stick; the report's stick_modules reads it). On
 *  H the ratchet is off for every spec (section 4), so that is production there. */
const STICK_EXTRA = ['HARNESS_LOSER_STOP'];
/** v equals the default d by value, as loadConfig and the sim read it (booleans also as 'true' / '1', 'false' / '0';
 *  numbers by value): the report's knob_val comparison. */
function sameValue(v: OverrideValue, d: OverrideValue): boolean {
  if (typeof d === 'boolean') return v === d || (typeof v !== 'boolean' && (d ? ['true', '1'] : ['false', '0']).includes(String(v).trim()));
  if (typeof d === 'number') return typeof v !== 'boolean' && String(v).trim() !== '' && Number(v) === d;
  return String(v).trim() === d;
}
/** A spec list's tags for its shard runs[] entries (C4): stick: true on measuring sticks, and the spec's offsetMs when it
 *  sets one (the sim's run drops it; the report's twin and cross-file checks read it, and the registry row its env). */
export function runTags(specs: SweepSpec[]): Map<string, { stick?: true; offsetMs?: number }> {
  return new Map(specs.map((s) => [s.id, { ...(s.stick ? { stick: true as const } : {}), ...(s.offsetMs !== undefined ? { offsetMs: s.offsetMs } : {}) }]));
}
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
let defaultReads: Set<string> | undefined;
/** The TENNIS_* / PACER* keys production's loadConfig (bot/config.ts) reads on the default env: a key outside this set
 *  (and not read on the spec's own env, where a key read only under another setting shows up) is unknown to it. */
export function configKeys(): Set<string> {
  defaultReads ??= new Set([...configRead({}).read].filter((k) => k.startsWith('TENNIS_') || k.startsWith('PACER')));
  return defaultReads;
}

/** A stage 2 id is 'A|s2|<config>|<arm>' (stage hold: 'A|hold|<config>|<arm>') where the arm is the fill (F0, F1, F2) or
 *  'coin' for the coin placebo; measuring sticks are 'A|s2|prod|<name>|<fill>' ('A|hold|prod|<name>|<fill>') and nothing
 *  else is. */
const specIdTag = (stage: '2' | 'hold') => (stage === '2' ? 's2' : 'hold');
const specIdRe = (stage: '2' | 'hold') => new RegExp(`^A\\|${specIdTag(stage)}\\|(.+)\\|(F0|F1|F2|coin)$`);
const stickIdRe = (stage: '2' | 'hold') => new RegExp(`^A\\|${specIdTag(stage)}\\|prod\\|.+\\|[^|]+$`);
/** The harness rules' defaults (the sim's, SimSpec in research/tennisTaSim.ts): an arm with every HARNESS_* key unset or at
 *  these values runs production's harness. */
const HARNESS_DEFAULTS: Readonly<Record<string, OverrideValue>> = { HARNESS_PACER: 'tennis', HARNESS_LOSER_STOP: 0, HARNESS_BANKROLL: 200, HARNESS_FEE_MULT: 1, HARNESS_LATENCY_MS: 0 };

/** Validate stage 2's spec list (research/tennis-ta/stage2-specs.json): an array of {id, overrides, fill, placebo?} with
 *  unique ids 'A|s2|<config>|<arm>', the arm suffix agreeing with the spec (|coin for the coin placebo, else |F0, |F1 or
 *  |F2 as its fill); optional stick: true (measuring stick, id 'A|s2|prod|<name>|<fill>', and every such id is a stick)
 *  and offsetMs (noise-floor clock phase). Every arm of one config (F0, F1, F2, coin) runs the same overrides, written
 *  alike (the report compares a config's arms as written, value types included), at one offsetMs; an F2 or coin arm
 *  needs its config's F1 arm (the report pairs them with it as their control). Stress adversaries and measuring settings
 *  (STICK_KEYS) are never hypotheses: only a stick moves one, and a stick runs production plus those settings (and
 *  HARNESS_LOSER_STOP, and offsetMs) only, so no threshold trial runs unscreened and uncounted as a stick. Overrides are
 *  env-style TENNIS_* / PACER_* / HARNESS_* keys with string,
 *  number or boolean values. Every TENNIS_* / PACER_* key must be one production's loadConfig reads (a misspelt key would
 *  run as the production default and still count) with a value loadConfig accepts, and each must change the simulated
 *  config (tennis and pacer) given the spec's other keys (a default value, or a key landing in a part of the config the
 *  sim does not run, is refused); every HARNESS_* key must be one the sim reads (HARNESS_RULES) with a valid value. Two
 *  arms that would run identically (same simulated config, harness rules, fill and clock phase; coin-placebo arms
 *  excepted, their streams are seeded by id) are refused, and so are two non-stick arms that differ only in the clock
 *  phase (a noise-floor adversary, section 7: a stick at production). On H every spec runs with
 *  TENNIS_TRAIL_RATCHET=false (section 4): it is written as the boolean false when unset or off ('false', '0'), and a
 *  spec that turns it on is refused. Every list this accepts passes the report's check_runs (the tests pipe accepted
 *  lists through it). Throws with every problem listed. */
export function validateStage2Specs(raw: unknown, stratum: 'H' | 'R' = 'H'): SweepSpec[] {
  return checkSpecList(raw, stratum, '2');
}

/** Validate stage hold's frozen spec list (research/tennis-ta/hold-specs.json, C10): every rule of validateStage2Specs
 *  with ids 'A|hold|<config>|<arm>' (sticks 'A|hold|prod|<name>|<fill>'), and the list HO-1 scores: exactly one
 *  production-default F1 control (an F1 arm running production: no TENNIS_* / PACER_* change, every HARNESS_* rule at its
 *  default, offsetMs 0; the report finds it by value and pairs every candidate with it), at least one candidate, and
 *  every candidate config (a config whose F1 arm is not the control) with its F2 neighbour (|F2) and coin placebo
 *  (|coin). An F0 arm and measuring sticks may be added. The candidates are chosen on H-DEV (disc runs) only; the list
 *  is scored once (its specsHash goes into the openings ledger). Throws with every problem listed. */
export function validateHoldSpecs(raw: unknown, stratum: 'H' | 'R' = 'H'): SweepSpec[] {
  return checkSpecList(raw, stratum, 'hold');
}

function checkSpecList(raw: unknown, stratum: 'H' | 'R', stage: '2' | 'hold'): SweepSpec[] {
  const P = `A|${specIdTag(stage)}|`, label = stage === '2' ? 'stage 2 specs' : 'hold specs';
  const S2_ID = specIdRe(stage), S2_STICK = stickIdRe(stage);
  const p: string[] = [];
  if (!Array.isArray(raw)) throw new Error(`${label}: expected a JSON array of {id, overrides, fill, placebo?}`);
  if (!raw.length) throw new Error(`${label}: the list is empty`);
  const production = new Set<string>();
  const seen = new Set<string>();
  const out: SweepSpec[] = [];
  const forced: Record<string, OverrideValue> = stratum === 'H' ? { TENNIS_TRAIL_RATCHET: false } : {};
  const baseline = configRead(configEnv(forced)).sim;
  const known = configKeys();
  const arms = new Map<string, Array<{ id: string; off: number; stick: boolean }>>();
  raw.forEach((x, i) => {
    const at = `spec ${i}${x && typeof x === 'object' && typeof (x as { id?: unknown }).id === 'string' ? ` (${(x as { id: string }).id})` : ''}`;
    if (!x || typeof x !== 'object' || Array.isArray(x)) { p.push(`${at}: not an object`); return; }
    const s = x as Record<string, unknown>;
    for (const k of Object.keys(s)) if (!SPEC_KEYS.has(k)) p.push(`${at}: unknown key ${k}`);
    if (typeof s.id !== 'string' || !s.id.startsWith(P)) p.push(`${at}: id must be a string starting '${P}'`);
    else if (seen.has(s.id)) p.push(`${at}: duplicate id`);
    else seen.add(s.id);
    if (s.fill !== 'F0' && s.fill !== 'F1' && s.fill !== 'F2') p.push(`${at}: fill must be F0, F1 or F2`);
    if (s.placebo !== undefined && s.placebo !== 'coin') p.push(`${at}: placebo must be 'coin' when set`);
    if (s.stick !== undefined && s.stick !== true) p.push(`${at}: stick must be true when set`);
    if (s.offsetMs !== undefined && !(Number.isInteger(s.offsetMs) && (s.offsetMs as number) >= 0 && (s.offsetMs as number) < 5000)) p.push(`${at}: offsetMs must be an integer in [0, 5000)`);
    // The arm in the id (the report and the registry read the arm and the config from it).
    if (typeof s.id === 'string' && s.id.startsWith(P)) {
      const want = s.placebo === 'coin' ? 'coin' : typeof s.fill === 'string' ? s.fill : undefined;
      const m = S2_ID.exec(s.id);
      if (!m) p.push(`${at}: id must be '${P}<config>|<arm>' with the arm ${want ? `|${want}` : '|F0, |F1, |F2 or |coin'} at its end`);
      else if (want && m[2] !== want) p.push(`${at}: id ends |${m[2]} but the spec is ${s.placebo === 'coin' ? "the coin placebo (|coin)" : `fill ${s.fill} (|${s.fill})`}`);
      const stickId = S2_STICK.test(s.id);
      if (s.stick === true && !stickId) p.push(`${at}: a measuring stick's id is '${P}prod|<name>|<fill>'`);
      if (s.stick !== true && stickId) p.push(`${at}: ids '${P}prod|<name>|<arm>' are measuring sticks: set stick: true, or name the arm otherwise`);
      if (s.stick === true && s.placebo !== undefined) p.push(`${at}: a measuring stick has no placebo arm`);
    }
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
      // Stress adversaries and measuring settings are never hypotheses (the report's check_runs refuses a non-stick run
      // that moves one); a stick is production plus those settings only, or a threshold trial would run as a stick,
      // reported but never screened or counted.
      if (s.stick !== true && k in STICK_KEYS && !sameValue(v as OverrideValue, STICK_KEYS[k]))
        p.push(`${at}: override ${k}=${JSON.stringify(v)} is a stress adversary or measuring setting (section 7), never a hypothesis: only a measuring stick moves it (stick: true, id '${P}prod|<name>|<fill>')`);
      if (s.stick === true && !(k in STICK_KEYS) && !STICK_EXTRA.includes(k) && !(stratum === 'H' && k === 'TENNIS_TRAIL_RATCHET'))
        p.push(`${at}: override ${k} is not a measuring setting: a measuring stick runs production with only ${[...Object.keys(STICK_KEYS), ...STICK_EXTRA].join(', ')} (and offsetMs) set; a rulebook change is a config arm '${P}<config>|<arm>', screened and counted`);
    }
    if (stratum === 'H') {
      // Written as the boolean false whatever the spelling, so a config's arms carry it alike (the report compares them as
      // written, and the sweep adds it to the arms that leave it unset).
      if (o.TENNIS_TRAIL_RATCHET === undefined || ['false', '0', 0].includes(o.TENNIS_TRAIL_RATCHET as string | number)) o.TENNIS_TRAIL_RATCHET = false;
      else if (o.TENNIS_TRAIL_RATCHET !== false) p.push(`${at}: TENNIS_TRAIL_RATCHET must be off on H (section 4)`);
    }
    // Production's loadConfig ignores keys it does not read: a misspelt key would run as the default and still count.
    // Checked whatever else is wrong with the spec, against the keys it reads by default and on this spec's env.
    const env = configEnv(o);
    const r = configRead(env);
    for (const k of Object.keys(env)) if (!known.has(k) && !r.read.has(k)) p.push(`${at}: override ${k} is not a key production's loadConfig reads (bot/config.ts): it would run as the production default`);
    if (p.length === before) {
      if (r.error) p.push(`${at}: production's loadConfig refuses the overrides: ${r.error}`);
      const own = Object.keys(env).filter((k) => !(k in forced) || String(forced[k]) !== env[k]);
      if (!r.error && own.length && r.sim === baseline) p.push(`${at}: overrides ${own.join(', ')} leave the simulated config at production's (every value is the default): drop them (overrides {} is the production arm)`);
      else if (!r.error) {
        // Each key must matter given the others: a default value, or a key read into a part of the config the sim does
        // not run (it runs the tennis and pacer config), would sit in the arm's env and change nothing.
        for (const k of own) {
          const rest = { ...env };
          delete rest[k];
          if (configRead(rest).sim === r.sim) p.push(`${at}: override ${k}=${env[k]} changes nothing the sim runs (the production default, or a setting outside the tennis and pacer config): drop it`);
        }
      }
      if (p.length === before && s.placebo === undefined) {
        // Production's arm (stage hold's control): the simulated config and every harness rule at production's.
        if (!r.error && s.stick !== true && s.fill === 'F1' && ((s.offsetMs as number | undefined) ?? 0) === 0 && r.sim === baseline
          && Object.entries(o).every(([k, v]) => !k.startsWith('HARNESS_') || (k in HARNESS_DEFAULTS && sameValue(v as OverrideValue, HARNESS_DEFAULTS[k])))) production.add(s.id as string);
        const h = (k: string, d: OverrideValue) => String(o[k] ?? d);
        const key = JSON.stringify([r.sim, h('HARNESS_PACER', 'tennis'), Number(h('HARNESS_LOSER_STOP', 0)), Number(h('HARNESS_BANKROLL', 200)),
          Number(h('HARNESS_FEE_MULT', 1)), Number(h('HARNESS_LATENCY_MS', 0)), s.fill]);
        const off = (s.offsetMs as number | undefined) ?? 0, stick = s.stick === true;
        const prior = arms.get(key) ?? [];
        const twin = prior.find((a) => a.off === off);
        // Two hypotheses that differ only in the decision-clock phase are one hypothesis and its noise floor (section 7):
        // the report reads such a pair as twins, and a phase-lucky arm must not pass as a config of its own.
        const phase = stick ? undefined : prior.find((a) => !a.stick);
        if (twin) p.push(`${at}: runs exactly as ${twin.id} (same simulated config, harness rules, fill and clock phase): the two arms would give identical results`);
        else if (phase) p.push(`${at}: runs as ${phase.id} at another decision-clock offset only (${off} ms, ${phase.off} ms there): that is a noise-floor adversary (section 7), never a hypothesis: run it as a measuring stick at production ('${P}prod|<name>|<fill>', stick: true, offsetMs)`);
        prior.push({ id: s.id as string, off, stick });
        arms.set(key, prior);
      }
    }
    out.push({ id: s.id as string, overrides: o as SimSpec['overrides'], fill: s.fill as SimSpec['fill'], ...(s.placebo ? { placebo: 'coin' as const } : {}),
      ...(s.offsetMs !== undefined ? { offsetMs: s.offsetMs as number } : {}), ...(s.stick ? { stick: true as const } : {}) });
  });
  // A config's arms (every non-stick id 'A|s2|<config>|<arm>') run the same overrides, written alike: the report's
  // check_runs compares them as written (JSON, value types included: 0.4 and "0.4" differ there), at one clock phase. F2
  // and coin arms are the config's neighbour and placebo: the report pairs each with the config's F1 row.
  const configs = new Map<string, SweepSpec[]>();
  for (const x of out) {
    const m = S2_ID.exec(x.id ?? '');
    if (!m || x.stick) continue;
    configs.set(m[1], [...(configs.get(m[1]) ?? []), x]);
  }
  const asWritten = (v: unknown) => (v === undefined ? 'unset' : JSON.stringify(v));
  for (const [cfg, list] of configs) {
    const f1 = list.find((x) => x.id === `${P}${cfg}|F1`);
    for (const x of list) {
      const arm = x.id!.slice(x.id!.lastIndexOf('|') + 1);
      if (!f1 && (arm === 'F2' || arm === 'coin')) p.push(`${x.id}: its config has no F1 arm (${P}${cfg}|F1): the report pairs the ${arm === 'coin' ? 'coin placebo' : 'F2 neighbour'} with the config's F1 row`);
    }
    const ref = f1 ?? list[0];
    for (const x of list) {
      if (x === ref) continue;
      const keys = [...new Set([...Object.keys(ref.overrides), ...Object.keys(x.overrides)])].sort();
      const diff = keys.filter((k) => asWritten(ref.overrides[k]) !== asWritten(x.overrides[k]));
      if (diff.length) p.push(`${x.id}: overrides differ from ${ref.id}'s (${diff.map((k) => `${k} ${asWritten(x.overrides[k])} vs ${asWritten(ref.overrides[k])}`).join(', ')}): every arm of a config runs the same overrides, written alike (the report compares them as written, value types included)`);
      if ((x.offsetMs ?? 0) !== (ref.offsetMs ?? 0)) p.push(`${x.id}: offsetMs ${x.offsetMs ?? 0} differs from ${ref.id}'s ${ref.offsetMs ?? 0}: a config's arms run at one decision-clock phase`);
    }
  }
  if (stage === 'hold') {
    // HO-1's frozen list: one control, and every candidate with its neighbour and its placebo.
    const control = out.filter((x) => production.has(x.id));
    if (!control.length) p.push(`no production-default F1 control: the list needs one F1 arm '${P}<config>|F1' running production (overrides {}, every HARNESS_* rule at its default, offsetMs 0), the control every candidate is scored against`);
    else if (control.length > 1) p.push(`${control.length} production-default F1 arms (${control.map((x) => x.id).join(', ')}): the list has one control`);
    let candidates = 0;
    for (const [cfg, list] of configs) {
      const f1 = list.find((x) => x.id === `${P}${cfg}|F1`);
      if (!f1) { if (!list.some((x) => x.id.endsWith('|F2') || x.id.endsWith('|coin'))) p.push(`${P}${cfg}: a hold config needs its F1 arm (the candidate HO-1 scores)`); continue; }
      if (production.has(f1.id)) continue;
      candidates++;
      const missing = (['F2', 'coin'] as const).filter((arm) => !list.some((x) => x.id === `${P}${cfg}|${arm}`));
      if (missing.length) p.push(`${f1.id}: a hold candidate needs its ${missing.map((a) => (a === 'coin' ? `coin placebo (${P}${cfg}|coin)` : `F2 neighbour (${P}${cfg}|F2)`)).join(' and ')}: HO-1 scores the gain over the control against the placebo, and the report pairs the neighbour with the candidate`);
    }
    if (!candidates) p.push('the list holds no candidate (an F1 arm other than the control, with its F2 neighbour and coin placebo)');
  }
  if (p.length) throw new Error(`${label}: ${p.length} problem(s):\n  ${p.join('\n  ')}`);
  return out;
}

const canonValue = (v: OverrideValue): string => {
  if (typeof v !== 'string') return String(v);
  const t = v.trim();
  return /^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(t) ? String(Number(t)) : t;
};

/** The canonical form of a spec list (its frozen identity, C10): the specs sorted by id, each as [id, fill, placebo or
 *  null, stick, offsetMs (0 when unset), its overrides sorted by key with each value as the string the sim and loadConfig
 *  read (numbers by value: 0.4, "0.4" and "0.40" are one value)]. Re-ordering the file, re-spacing it or re-spelling a
 *  number leaves it unchanged; any change to what runs or to an id changes it. */
export function canonicalSpecs(specs: SweepSpec[]): string {
  return JSON.stringify([...specs].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)).map((s) => [s.id, s.fill, s.placebo ?? null, s.stick === true, s.offsetMs ?? 0,
    Object.keys(s.overrides).sort().map((k) => [k, canonValue(s.overrides[k])])]));
}

/** sha256 (hex) of canonicalSpecs: the hash the openings ledger keys a frozen list by. */
export const specsHash = (specs: SweepSpec[]): string => sha256(canonicalSpecs(specs));

/** The openings ledger's rows (JSON lines; blank lines skipped). Throws on a line that is not an object with a string
 *  hash: a damaged ledger is never read as "not opened". */
export function parseOpenings(text: string): Array<{ hash: string; run?: unknown; ts?: unknown; ids?: unknown; pool?: unknown }> {
  const rows: Array<{ hash: string }> = [];
  text.split('\n').forEach((line, i) => {
    if (!line.trim()) return;
    let x: unknown;
    try { x = JSON.parse(line); } catch { throw new Error(`openings ledger line ${i + 1}: not JSON (${line.slice(0, 80)}): a damaged ledger is not read as "not opened"`); }
    if (!x || typeof x !== 'object' || typeof (x as { hash?: unknown }).hash !== 'string') throw new Error(`openings ledger line ${i + 1}: not an object with a string hash: a damaged ledger is not read as "not opened"`);
    rows.push(x as { hash: string });
  });
  return rows;
}

/** The spec file a stage reads by default: stage 2's list, or stage hold's frozen list. */
export const specsPathOf = (stage: string): string => (stage === 'hold' ? HOLD_SPECS : STAGE2_SPECS);

/** The spec list of a stage: stage 1 from stage1Specs() (H only), stage 2 and stage hold from their spec files
 *  (validateStage2Specs, validateHoldSpecs). */
export function specsFor(stage: string, stratum: 'H' | 'R', specsPath = specsPathOf(stage)): SweepSpec[] {
  if (stage === '1') {
    if (stratum !== 'H') throw new Error('stage 1 is the H design (ratchet off, windows >= 60 s); an R sweep needs its own stage 2 spec list');
    return stage1Specs();
  }
  if (stage === '2' || stage === 'hold') {
    const what = stage === '2' ? `stage 2 reads its spec list from ${specsPath}` : `stage hold reads its frozen spec list from ${specsPath}`;
    if (!fs.existsSync(specsPath)) throw new Error(`${what}, which does not exist: commit it (array of {id, overrides, fill, placebo?}, ids '${stage === '2' ? 'A|s2|' : 'A|hold|'}...') before requesting stage ${stage}`);
    let raw: unknown;
    try { raw = JSON.parse(fs.readFileSync(specsPath, 'utf8')); } catch (e) { throw new Error(`${specsPath}: not valid JSON (${(e as Error).message})`); }
    return stage === '2' ? validateStage2Specs(raw, stratum) : validateHoldSpecs(raw, stratum);
  }
  throw new Error(`stage must be '1', '2' or 'hold', got ${JSON.stringify(stage)}`);
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

/** The units holding time of a pool (poolInterval), in start order. */
export const poolUnitsOf = (units: Unit[], pool: Pool, cutoff = HARD_CUTOFF): Unit[] => units.filter((u) => poolInterval(u, pool, cutoff) !== undefined);

/** The units of a pool a request sweeps: every pool unit (one holding time of the pool) whose start is in [from, to]
 *  (swept whole, so the plan can run past `to` to the unit's end). Throws when `from` falls after a pool unit's start day
 *  and before its end day (that unit's start is not covered, so it would be swept in part) or [from, to] holds no pool
 *  unit. A unit's end day is the next unit's start day, so from = a unit's start day leaves the unit before it out whole. */
export function requestUnits(units: Unit[], pool: Pool, from: string, to: string): Unit[] {
  const F = Date.parse(from), T = Date.parse(to) + DAY;
  const inPool = poolUnitsOf(units, pool);
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

export interface SweepRequest { stage: Stage; pool: Pool; from: string; to: string; shards: number; familyB: boolean; note?: string }

const REQUEST_KEYS = new Set(['stage', 'pool', 'from', 'to', 'shards', 'familyB', 'note']);
const isDay = (s: unknown): s is string => typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && dayOf(Date.parse(s)) === s;

/** Why a pool cannot be requested (undefined = it can, at this stage). */
export function poolRefusal(pool: unknown, stage?: string): string | undefined {
  if (pool === 'check' || pool === 'sealed') return `pool '${pool}' no longer exists (C9): HO-1 retired dev-check and the hash-sealed units; the held-out data is the contiguous H-HOLD block, pool 'hold', scored once by stage 'hold'`;
  if (pool === 'nostart' || pool === 'embargo' || pool === 'out') return `pool '${pool}' is never scored (C9: 'nostart' matches are excluded and counted in every run's coverage; embargoed and out matches are streamed past): request 'disc', 'old' at stage 2, or 'hold' at stage hold`;
  if (typeof pool !== 'string' || !REQUESTABLE_POOLS.includes(pool as Pool)) return `pool must be 'disc', 'old' (stage 2) or 'hold' (stage hold), one pool per run, got ${JSON.stringify(pool)}`;
  if (stage === 'hold' && pool !== 'hold') return `stage 'hold' scores pool 'hold' (H-HOLD) only, got pool ${JSON.stringify(pool)}`;
  if (pool === 'old' && stage !== undefined && stage !== '2') return `pool 'old' (stratum H0: units before the start era ${dayOf(START_ERA_FROM)}, no published start, the older settlement rule) is a stress test for stage 2 finalists only, got stage ${JSON.stringify(stage)}`;
  if (pool === 'hold' && stage !== undefined && stage !== 'hold') return `pool 'hold' (H-HOLD, ${H_HOLD[0]} to ${H_HOLD[1]}) is scored only by stage 'hold', once per frozen spec list (${HOLD_SPECS}), got stage ${JSON.stringify(stage)}: choose settings on 'disc' (H-DEV)`;
  return undefined;
}

/** The default request span of a pool: its first unit's start day to its last day (old: the day before the start era;
 *  disc: Jul 30, the last day a disc match can close on; hold: H-HOLD's last day). */
export function poolDefaults(units: Unit[], pool: Pool): { from?: string; to: string } {
  const first = poolUnitsOf(units, pool)[0]?.startDay;
  return { from: first, to: pool === 'old' ? dayOf(START_ERA_FROM - DAY) : pool === 'hold' ? H_HOLD[1] : dayOf(DEV_TO - DAY) };
}

/** Validate a request; defaults: pool disc ('hold' at stage hold), from/to = the whole pool, shards 8, familyB false. A
 *  hold request scores the whole of H-HOLD (from and to, when given, must be the defaults) without family B (a discovery
 *  design: every cell is a hypothesis, so it runs on disc). Throws with every problem. */
export function parseRequest(raw: unknown, units: Unit[]): SweepRequest {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('sweep request: expected a JSON object');
  const r = raw as Record<string, unknown>;
  const p: string[] = [];
  for (const k of Object.keys(r)) if (!REQUEST_KEYS.has(k)) p.push(`unknown key ${k} (allowed: ${[...REQUEST_KEYS].join(', ')})`);
  const stage = String(r.stage ?? '');
  const known = (STAGES as readonly string[]).includes(stage);
  if (!known) p.push(`stage must be 1, 2 or hold, got ${JSON.stringify(r.stage)}`);
  const pool = (r.pool ?? (stage === 'hold' ? 'hold' : 'disc')) as Pool;
  const refused = poolRefusal(pool, known ? stage : undefined);
  if (refused) p.push(refused);
  const def = poolDefaults(units, refused ? 'disc' : pool);
  const from = r.from ?? def.from, to = r.to ?? def.to;
  if (!isDay(from)) p.push(`from must be a YYYY-MM-DD day, got ${JSON.stringify(r.from)}`);
  if (!isDay(to)) p.push(`to must be a YYYY-MM-DD day, got ${JSON.stringify(r.to)}`);
  if (isDay(from) && isDay(to) && from > to) p.push(`from ${from} is after to ${to}`);
  if (pool === 'hold' && !refused && (from !== def.from || to !== def.to)) p.push(`a hold run scores the whole of H-HOLD once (${H_HOLD[0]} to ${H_HOLD[1]}, 6 folds): leave from and to out (they default to ${def.from} and ${def.to}, every unit holding hold time), got ${from} to ${to}`);
  const shards = r.shards ?? 8;
  if (!Number.isInteger(shards) || (shards as number) < 1 || (shards as number) > 16) p.push(`shards must be an integer from 1 to 16, got ${JSON.stringify(r.shards)}`);
  if (r.familyB !== undefined && typeof r.familyB !== 'boolean') p.push(`familyB must be true or false, got ${JSON.stringify(r.familyB)}`);
  if (stage === 'hold' && r.familyB === true) p.push('familyB is a discovery design (every cell is a hypothesis), never scored on H-HOLD: a hold run is family A\'s frozen list only');
  if (r.note !== undefined && typeof r.note !== 'string') p.push('note must be a string');
  if (p.length) throw new Error(`sweep request: ${p.length} problem(s):\n  ${p.join('\n  ')}`);
  return { stage: stage as Stage, pool, from: from as string, to: to as string, shards: shards as number, familyB: r.familyB === true, ...(r.note !== undefined ? { note: r.note as string } : {}) };
}

export interface EraEdges { historyFrom: string; startEraFrom: string; devTo: string; holdFrom: string; cutoff: string }
export const eraEdges = (): EraEdges => ({
  historyFrom: new Date(HISTORY_FROM).toISOString(), startEraFrom: new Date(START_ERA_FROM).toISOString(),
  devTo: new Date(DEV_TO).toISOString(), holdFrom: new Date(HOLD_FROM).toISOString(), cutoff: new Date(HARD_CUTOFF).toISOString(),
});
export const stratumLabelOf = (pool: Pool, stratum: 'H' | 'R'): 'H' | 'H0' | 'R' => (stratum === 'H' && pool === 'old' ? 'H0' : stratum);

export interface Prep {
  request: SweepRequest;
  requestSha: string;
  unitsSha: string;
  simVersion: string;
  /** The history replay's REPLAY_VERSION (research/history/historyReplay.ts) the shards build their days with. */
  replayVersion: number;
  stage: Stage;
  pool: Pool;
  familyB: boolean;
  stratum: 'H';
  /** 'H0' for pool 'old' (history before the start era), else 'H'. */
  stratumLabel: 'H' | 'H0';
  /** The era edges this plan was cut with (START_ERA_FROM is fixed from the weekly inventory before the first counting
   *  run; a run records the value it used). */
  era: EraEdges;
  /** HO-1's six folds over H-HOLD (registry.py's edges; to inclusive): matchList[].fold of a hold match. */
  holdFolds: Array<{ fold: number; from: string; to: string }>;
  /** Units per pool over the whole unit table (a unit holding time of several pools counts in each; 'out' = none). */
  poolUnits: Partial<Record<Pool, number>>;
  configs: number;
  /** sha256 of the stage's canonical spec list (canonicalSpecs) and its ids: stage hold's frozen-list identity, the key
   *  of the openings ledger (C10). */
  specsHash: string;
  specIds: string[];
  /** Stage hold: the openings-ledger rows read (none of them holds specsHash). */
  openingsRead?: number;
  /** One entry per shard job (the matrix). */
  plan: PlanEntry[];
  /** subPlans[k] = shard k's sub-slices (one process each), cut by the same rule (subplan re-derives them). */
  subPlans: PlanEntry[][];
  /** Every shard file the run must produce, each exactly once. */
  expected: string[];
  /** Units swept and the pool's wall-clock intervals per unit (the embargo day left out), for the report's $/h. */
  units: string[];
  poolSpans: PoolSpan[];
}

/** Validate a request against the unit table and the stage's spec list; the plan for the workflow. `specsPath` defaults
 *  to the stage's spec file (specsPathOf). Stage hold also needs the openings ledger's text (opts.openings: the ledger as
 *  read from Drive, '' when it does not exist yet) and refuses a frozen list whose specsHash is in it (C10). */
export function prepare(requestText: string, unitsText: string, specsPath?: string, opts: { openings?: string } = {}): Prep {
  let raw: unknown;
  try { raw = JSON.parse(requestText); } catch (e) { throw new Error(`sweep request: not valid JSON (${(e as Error).message})`); }
  const units = JSON.parse(unitsText) as Unit[];
  const bad = verifyUnits(units);
  if (bad.length) throw new Error(`unit table: ${bad.length} problem(s):\n  ${bad.slice(0, 20).join('\n  ')}`);
  const req = parseRequest(raw, units);
  const specs = specsFor(req.stage, 'H', specsPath ?? specsPathOf(req.stage));
  const hash = specsHash(specs);
  let openingsRead: number | undefined;
  if (req.stage === 'hold') {
    if (opts.openings === undefined) throw new Error(`stage hold needs the openings ledger (--openings F: ${OPENINGS_LEDGER} as read from Drive, an empty file when it does not exist yet): H-HOLD is scored once per frozen list`);
    const rows = parseOpenings(opts.openings);
    const hit = rows.find((x) => x.hash === hash);
    if (hit) throw new Error(`the frozen list ${specsPathOf(req.stage)} (specsHash ${hash}) was already opened on H-HOLD (run ${String(hit.run ?? '?')}, ${String(hit.ts ?? '?')}): HO-1 scores a frozen list once. A new hold run needs a new list, chosen on H-DEV`);
    openingsRead = rows.length;
  }
  const sel = requestUnits(units, req.pool, req.from, req.to);
  if (req.pool === 'hold') {
    const all = poolUnitsOf(units, 'hold').map((u) => u.id);
    if (JSON.stringify(sel.map((u) => u.id)) !== JSON.stringify(all)) throw new Error(`a hold run sweeps every unit holding hold time (${all[0]} to ${all[all.length - 1]}), got ${sel.map((u) => u.id).join(', ')}`);
  }
  const plan = planUnits(sel, req.shards);
  const byId = new Map(units.map((u) => [u.id, u]));
  const subPlans = plan.map((e) => planUnits(e.units.map((id) => byId.get(id)!), SUB_SHARDS));
  const poolUnits: Partial<Record<Pool, number>> = {};
  for (const u of units) for (const up of unitPools(u)) poolUnits[up] = (poolUnits[up] ?? 0) + 1;
  return {
    request: req, requestSha: sha256(requestText), unitsSha: sha256(unitsText), simVersion: SIM_VERSION, replayVersion: REPLAY_VERSION, stage: req.stage, pool: req.pool,
    familyB: req.familyB, stratum: 'H', stratumLabel: req.pool === 'old' ? 'H0' : 'H', era: eraEdges(), holdFolds: holdFolds(), poolUnits, configs: specs.length,
    specsHash: hash, specIds: specs.map((x) => x.id), ...(openingsRead !== undefined ? { openingsRead } : {}), plan, subPlans,
    expected: plan.flatMap((e) => subPlans[e.k].map((s) => shardFile(req.stage, e.k, s.k))),
    units: sel.map((u) => u.id), poolSpans: poolSpans(units, req.pool, HARD_CUTOFF, new Set(sel.map((u) => u.id))),
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
  /** Owned matches per pool (matchList[].pool) and the distinct units holding them; the requested pool and 'nostart'
   *  are always present. A start-era match without a published start is admitted as its times would place it with one
   *  (the sim's admit() is not told whether a start was published), runs with the others (production trades it too, so
   *  the cross-match state stays production's), and is labelled 'nostart': the report leaves it out and counts it. */
  pools?: Partial<Record<Pool, { matches: number; units: number }>>;
  /** Tennis match tickers with book or trade lines but no market line in what the sim read (lost matches). */
  lostTickers?: number;
  /** The sim's feed bookkeeping (SweepResult): R feed outages (gaps, their ms, those found only by a resubscribe: blind
   *  days, or reconnects the beats masked), day files that show or hide the feed's liveness, and grids not delivered to
   *  family B because their day was already released. */
  feed?: { gaps: number; gapMs: number; blindGaps: number; liveDays: number; blindDays: number; lateGrids: number };
}

export interface ShardMeta {
  simVersion: string; stage: string; pool: Pool; run: string; k: number; j: number; shards: number; subShards: number;
  from: string; to: string; units: string[]; dataVersion: string; coverage: Coverage; requestSha: string; families: Array<'A' | 'B'>;
  /** Beyond C4: the history replay's REPLAY_VERSION the slice's days were built with (C11: the registry rows'
   *  data.replay_version), and sha256 of the canonical spec list the slice ran (stage hold: the frozen list's hash). */
  replayVersion: number; specsHash: string;
  [extra: string]: unknown;
}

export interface ShardOut {
  meta: ShardMeta;
  /** fold: the HO-1 fold (1..6) of a hold match's UTC day (holdFold), else null. */
  matchList: Array<MatchInfo & { pool: Pool; unit?: string; fold: number | null }>;
  runs: Array<Omit<SimRun, 'episodes'> & { episodes: unknown[][]; stick?: true; offsetMs?: number }>;
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

/** Accept only a requestable pool here too (the workflow's prep already refused anything else); with a stage, 'old'
 *  only at stage 2 and 'hold' only at stage hold (and stage hold only on 'hold'). */
export function assertPool(pool: string, stage?: string): Pool {
  const refused = poolRefusal(pool, stage);
  if (refused) throw new Error(refused);
  return pool as Pool;
}

/** Owned matches per pool and the distinct units holding them (Coverage.pools); `pool` (the requested one) and 'nostart'
 *  are listed even when empty. */
export function poolCounts(matchList: Array<{ pool: Pool; unit?: string }>, pool: Pool): Partial<Record<Pool, { matches: number; units: number }>> {
  const units = new Map<Pool, Set<string>>([[pool, new Set()], ['nostart', new Set()]]);
  const out: Partial<Record<Pool, { matches: number; units: number }>> = { [pool]: { matches: 0, units: 0 }, nostart: { matches: 0, units: 0 } };
  for (const m of matchList) {
    const c = (out[m.pool] ??= { matches: 0, units: 0 });
    c.matches++;
    const us = units.get(m.pool) ?? new Set<string>();
    units.set(m.pool, us);
    us.add(m.unit ?? '');
    c.units = us.size;
  }
  return out;
}

/** One sub-slice (the run command): sweep its units, write its shard file (C4). */
export async function cmdRun(a: Args): Promise<void> {
  const unitsText = fs.readFileSync(a.units, 'utf8');
  const units: Unit[] = JSON.parse(unitsText);
  const bad = verifyUnits(units);
  if (bad.length) throw new Error(`unit table: ${bad.slice(0, 10).join('; ')}`);
  // Lockbox weeks are opened only through the openings ledger, and the cutoff is before L1: none here.
  const opened = new Set<string>();
  const stratum = (a.stratum ?? 'H') as 'H' | 'R';
  if (stratum !== 'H' && stratum !== 'R') throw new Error(`stratum must be H or R, got ${a.stratum}`);
  const stage = String(a.stage ?? '');
  const pool = assertPool(a.pool ?? (stage === 'hold' ? 'hold' : 'disc'), stage);
  const specs = specsFor(stage, stratum, a.specs ?? specsPathOf(stage));
  const sticks = new Set(specs.filter((s) => s.stick).map((s) => s.id));
  // stick: true and the spec's offsetMs on each runs[] entry (the sim's run carries neither).
  const tags = runTags(specs);
  const byId = new Map(units.map((u) => [u.id, u]));
  const unitIds = a['units-list'] ? a['units-list'].split(',').filter(Boolean)
    : units.filter((u) => u.start >= Date.parse(a.from) && u.start < Date.parse(a.to)).map((u) => u.id);
  for (const id of unitIds) if (!byId.has(id)) throw new Error(`--units-list: unit ${id} is not in ${a.units}`);
  if (!unitIds.length) throw new Error(`no unit to sweep in [${a.from}, ${a.to})`);
  const unitSet = new Set(unitIds);
  const feeAt = a.fees ? feeLookup(JSON.parse(fs.readFileSync(a.fees, 'utf8'))) : undefined;
  const familyB = a['family-b'] === 'true';
  if (familyB && stage === 'hold') throw new Error('family B is a discovery design, never run on H-HOLD (stage hold scores family A\'s frozen list only)');
  // The stratum is given up front: a slice with no owned two-market match has no grid to take it from, and exportCells
  // refuses a study without one.
  const study = familyB ? new SignalStudy({ ...FAMILY_B, stratum, ...(stratum === 'H' ? { bars: H_BARS } : {}) }) : undefined;
  // The start the sim used for ownership (published, else the earliest market-line time): family B's unit comes from it,
  // so a grid lands in the same unit as its matchList row.
  const startOf = new Map<string, number>();
  const gridPublished = new Map<string, boolean>();
  let familyBNoStart = 0;
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
      // admit() is not told whether the start was published: a start-era match without one is admitted as its times
      // would place it with one and labelled 'nostart' in matchList below (Coverage.pools says why it still runs).
      const ok = u !== undefined && unitSet.has(u) && poolOf({ start: m.start, close: m.closeTime, startPublished: true }, units, opened) === pool;
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
      // A start-era match without a published start is 'nostart' (excluded and counted): family B leaves it out too.
      const gu = g.unit !== undefined ? byId.get(g.unit) : undefined;
      if (!g.startPublished && gu && startEra(gu)) { familyBNoStart++; return; }
      study.addMatch(g);
    } : undefined,
    log: (m) => console.log(`[tennis-ta] ${m}`),
  });
  // fold: a hold match's HO-1 fold by its UTC day (MatchInfo.day, the day of its start, which the report files its by_day
  // under), with exactly registry.py's edges.
  const matchList = r.matchList.map((m) => {
    const mp = poolOf({ start: m.start, close: m.close, startPublished: m.startPublished }, units, opened);
    return { ...m, pool: mp, unit: unitOf(m.start, units), fold: mp === 'hold' ? holdFold(m.day) : null };
  });
  const noStart = matchList.filter((m) => !m.startPublished);
  const pools = poolCounts(matchList, pool);
  const coverage: Coverage = {
    span: [a.from, a.to],
    series: seriesCov,
    matches: matchList.length, noPublishedStart: noStart.length, noPublishedStartEvents: noStart.slice(0, 50).map((m) => m.event), pools, lostTickers: r.lost,
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
      sim_version: SIM_VERSION, replayVersion: REPLAY_VERSION, sha: gitSha(), unitsSha: sha256(unitsText), stratum, stratumLabel: stratumLabelOf(pool, stratum), era: eraEdges(),
      holdFolds: holdFolds(), lookbackDays: lookback,
      evidence: stratum === 'R' ? 'recorded books' : pool === 'old' ? 'history before the start era (H0: no published start, older settlement rule), synthetic depth'
        : pool === 'hold' ? 'history, H-HOLD (a frozen list scored once), synthetic depth' : 'history, H-DEV, synthetic depth',
      doge_excluded: true, configs: specs.length, specsHash: specsHash(specs),
      sticks: [...sticks], poolSpans: poolSpans(units, pool, HARD_CUTOFF, unitSet),
      stateRestarts: 'cross-match state (pacer, caps, placebo streams) restarts at this slice\'s first unit edge',
      matches: r.matches, oneLegged: r.oneLegged, unresolved: r.unresolved, decisions: r.decisions, ms: Date.now() - t0,
      ...(study ? { familyBGrids: gridPublished.size, familyBStartMismatch: gridStartMismatch, familyBNoStart } : {}),
      written_utc: new Date().toISOString(), written_eastern: eastern(Date.now()), episodeCols: EPISODE_COLS,
    },
    matchList,
    runs: r.runs.map((x) => ({ ...x, ...tags.get(x.id),
      episodes: x.episodes.map((e) => EPISODE_COLS.map((c) => (e as unknown as Record<string, unknown>)[c] ?? 0)) })),
    ...(exportB ? { familyB: exportB } : {}),
  };
  fs.mkdirSync(path.dirname(path.resolve(a.out)), { recursive: true });
  fs.writeFileSync(a.out, zlib.gzipSync(JSON.stringify(out)));
  console.log(`[tennis-ta] wrote ${a.out}: ${r.matches} matches (${noStart.length} without a published start; pools ${Object.entries(pools).map(([k, c]) => `${k} ${c!.matches}`).join(', ')}), ${unitIds.length} unit(s), ${specs.length} configs${exportB ? `, family B ${exportB.cells.length} cells` : ''}, ${r.decisions} decisions, ${((Date.now() - t0) / 60_000).toFixed(1)} min`);
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
  run: string; files: number; dataVersion: string; simVersion: string; replayVersion?: number; specsHash: string; requestSha: string; stage: string; pool: string;
  families: string[]; shards: number; subSlices: number; units: number; matches: number; noPublishedStart: number;
  /** Owned matches and their units per pool, summed over the slices (Coverage.pools; units never repeat across slices). */
  pools: Partial<Record<Pool, { matches: number; units: number }>>;
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
  one('replayVersion', ms.map((m) => m.replayVersion));
  one('specsHash', ms.map((m) => m.specsHash));
  one('coverage.series first/last', ms.map((m) => m.coverage?.series && Object.fromEntries(Object.entries(m.coverage.series).map(([s, c]) => [s, [c.first, c.last, c.files]]))));
  const unitSeen = new Map<string, string>();
  for (const { file, meta } of metas) {
    const want = (key: string, got: unknown, exp: unknown) => { if (JSON.stringify(got) !== JSON.stringify(exp)) p.push(`${file}: ${key} ${JSON.stringify(got)}, expected ${JSON.stringify(exp)}`); };
    want('simVersion', meta.simVersion, SIM_VERSION);
    // The replay version the shard built its days with, and the spec list it ran (stage hold: the frozen list prep checked
    // against the openings ledger).
    want('replayVersion', meta.replayVersion, prep.replayVersion);
    want('specsHash', meta.specsHash, prep.specsHash);
    want('run', String(meta.run), run);
    want('requestSha', meta.requestSha, prep.requestSha);
    want('stage', meta.stage, prep.stage);
    want('pool', meta.pool, prep.pool);
    want('families', meta.families, prep.familyB ? ['A', 'B'] : ['A']);
    want('shards', meta.shards, prep.plan.length);
    if (meta.unitsSha !== undefined) want('unitsSha', meta.unitsSha, prep.unitsSha);
    const m = /^a-s(1|2|hold)-(\d+)-(\d+)\.json\.gz$/.exec(file);
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
  const pools: CheckSummary['pools'] = {};
  for (const meta of ms) for (const [k, c] of Object.entries(meta.coverage?.pools ?? {})) {
    const t = (pools[k as Pool] ??= { matches: 0, units: 0 });
    t.matches += c?.matches ?? 0;
    t.units += c?.units ?? 0;
  }
  const first = ms[0];
  return {
    problems: p,
    summary: {
      run, files: metas.length, dataVersion: first?.dataVersion ?? '', simVersion: first?.simVersion ?? '', replayVersion: prep.replayVersion, specsHash: prep.specsHash,
      requestSha: prep.requestSha, stage: prep.stage, pool: prep.pool,
      families: prep.familyB ? ['A', 'B'] : ['A'], shards: prep.plan.length, subSlices: prep.expected.length, units: unitSeen.size,
      matches: ms.reduce((s, m) => s + (m.coverage?.matches ?? 0), 0), noPublishedStart: ms.reduce((s, m) => s + (m.coverage?.noPublishedStart ?? 0), 0), pools, series,
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
  console.log(`[tennis-ta] ${s.matches} owned matches, ${s.noPublishedStart} without a published start (their unit and pool use the earliest market-line time); `
    + `by pool: ${Object.entries(s.pools).map(([k, c]) => `${k} ${c!.matches} in ${c!.units} unit(s)`).join(', ') || 'none recorded'}`);
  for (const [k, c] of Object.entries(s.series)) {
    console.log(`[tennis-ta] ${k}: history ${c.first ?? '-'} to ${c.last ?? '-'}, ${c.spanDays - c.missing.length} of ${c.spanDays} swept days have a file${c.missing.length ? ` (missing ${c.missing.slice(0, 12).join(', ')}${c.missing.length > 12 ? ', ...' : ''})` : ''}; `
      + `complete listing ${c.listed ? `${c.listed.from.slice(0, 16)} to ${c.listed.to.slice(0, 16)} UTC` : 'none'}; ${c.tapesMissing} traded market(s) without a tape`);
  }
  if (r.problems.length) {
    for (const x of r.problems.slice(0, 60)) console.error(`::error::${x}`);
    throw new Error(`${r.problems.length} problem(s) with the shard set or its history: nothing is scored and no registry rows are written or uploaded`);
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
      console.error(`${u.length} units, ${u.filter((x) => x.slam).length} Slam units; by pool ${(['old', 'disc', 'hold', 'out'] as Pool[]).map((p) => `${p} ${u.filter((x) => unitPools(x).includes(p)).length}`).join(', ')}`);
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
      const p = prepare(fs.readFileSync(a.request!, 'utf8'), fs.readFileSync(a.units, 'utf8'), a.specs, { openings: a.openings !== undefined ? fs.readFileSync(a.openings, 'utf8') : undefined });
      if (a.out) fs.writeFileSync(a.out, JSON.stringify(p, null, 1) + '\n'); else console.log(JSON.stringify(p));
      console.error(`[tennis-ta] stage ${p.stage}, pool ${p.pool}, ${p.configs} configs${p.familyB ? ' + family B' : ''}, ${p.units.length} unit(s) from ${p.plan[0].from} to ${p.plan[p.plan.length - 1].to}, ${p.plan.length} shard(s) x up to ${SUB_SHARDS} sub-slices = ${p.expected.length} file(s); specs ${p.specsHash.slice(0, 16)}`
        + (p.stage === 'hold' ? `, a frozen list not in the openings ledger (${p.openingsRead} row(s) read)` : ''));
      break;
    }
    case 'run':
      await cmdRun(a);
      break;
    case 'plan': {
      const pool = assertPool(a.pool ?? (a.stage === 'hold' ? 'hold' : 'disc'), a.stage);
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
      const pool = (a.pool ?? 'disc') as Pool;
      if (!SPAN_POOLS.includes(pool)) throw new Error(`pool-hours: pool must be ${SPAN_POOLS.join(', ')} (the pools with hours), got ${pool}`);
      const s = poolSpans(loadUnits(), pool);
      console.log(JSON.stringify(s));
      console.error(`${s.length} unit(s), ${s.reduce((x, u) => x + u.hours, 0).toFixed(0)} pool hours (the embargo day left out)`);
      break;
    }
    default:
      throw new Error(`unknown command ${cmd}: units | fees | days | prep | plan | subplan | run | coverage | check | pool-hours`);
  }
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) void main().catch((e) => { console.error(e instanceof Error ? e.stack ?? e.message : e); process.exitCode = 1; });
