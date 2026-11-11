// Tennis TA rulebook trial: the sweep CLI the GitHub workflow runs (pre-registration and its amendments:
// /mnt/project-files/tennis-ta/preregistration.md; thread "Build a profitable tennis TA rulebook", Nov 5 2026). The request
// file format and the run mechanics are documented in research/tennis-ta/README.md.
//
//   units   --from D --to D [--out F]          the tournament-week unit table (Monday 05:00 UTC weeks, Slams whole), calendar only
//   fees    --series S,S --out F               Kalshi fee changes per series (GET /series/fee_changes, show_historical)
//   days    --hist DIR --out DIR --from D --to D --series S,S   build history replay days (research/history/historyReplay.ts)
//   prep    --request F --units F --out F [--specs F] [--stage2-specs F] [--openings F]   validate a sweep request and
//           write the plan (shards and sub-slices by unit); stage hold needs --openings (the openings ledger as read
//           from Drive, empty if none) and reads its batch (--specs, default research/tennis-ta/hold-batch.json)
//   plan    --units F --from D --to D --shards N [--pool disc|old|hold] [--stage 1|2|hold]   the shard plan alone (JSON)
//   subplan --units F --units-list U,U [--parts 4]               a shard's sub-slices (JSON; the same cut prep made)
//   run     --replay DIR --from D --to D --units-list U,U --stage 1|2|hold --pool disc|old|hold --units F --out F.json.gz
//           [--fees F] [--hist DIR] [--family-b true] [--data-version S] [--request F] [--run ID] [--k K --j J
//           --shards N --sub-shards M] [--specs F] [--stage2-specs F]   (--hist also feeds the one test's candle index)
//   coverage --hist DIR --from D --to D [--series S,S] [--stratum H|R]   the history is complete over a span (exit 1 if not)
//   check   --dir DIR --listing F --prep F --run ID [--out F]   every planned shard file present once, one data version, the
//           history complete over every slice (download listing and trade tapes) and every file's window block whole
//           (C12: the plan's window arms x legs, the matchList's events; before a hold run's opening is recorded)
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
// run scores one pool: 'disc' (stages 1 and 2), 'old' (stage 2) or 'hold' (stage hold only: the one read of Amendment 4,
// the batch research/tennis-ta/hold-batch.json, refused when the batch file's sha256 is already in the openings ledger).
// The A3 hash seal and the dev-check pool are retired: the contiguous hold block replaces them (the old era needs no
// seal, since nothing is chosen there), and the unit table's legacy `sealed` flags are ignored.
//
// The one test (Amendment 4, research/tennisTaWindow.ts): every grid config and stick also runs a '|window' arm (and the
// grid configs a '|coinwindow' coin placebo), whose entry decisions are virtual taker buys judged by the window rule
// against three random twins; the shard file's 'window' block (contract C12) carries one row per window arm and leg,
// built here from the sim's SimRun.instances with the slice's minute candles (SweepOpts.candlesOf, the stored Kalshi
// candles of every market the slice reads). The league (the report, pool disc only) ranks the hot spots by z; the 10
// hottest go into hold-batch.json, listed in the registry and the project calendar BEFORE the read, and stage hold runs
// those configs' |window and |F1 arms once on H-HOLD. The bot's recordings before FULL_BOOK_FROM (Nov 10 03:44 UTC) are
// practice data: on R a match starting before it is pool 'practice', never requestable, never scored, never owned by a
// run (admit() labels an R match by recordedPoolOf: it is streamed past and counted, nothing of it reaches a shard).
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
import type { KalshiCandle } from './history/kalshiHistory';
import { FEES, runSweep, type MatchInfo, type SimRun, type SimSpec, type SweepOpts } from './tennisTaSim';
import { SignalStudy } from './tennisTaSignals';
import type { FamilyBExport, MatchGrid } from './tennisTaTypes';
import {
  HIST_EDGES, ORDER_USD, PLACEBO_SEED, SETTLE_FRAC, TWINS, WINDOW_VERSION, WindowAgg, endRuleTs, minuteCandles, newMinuteCandleStats, type MinuteCandleStats, type MinuteCandles,
  type WindowInstance, type WindowRow,
} from './tennisTaWindow';

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
 *  PINNED Nov 11 2026 from the weekly inventory (Tennis TA data run 43067646856, startEraWeek of both series): the week of
 *  2026-04-20 is the first in which at least 95% of two-market events carry a published start (ATP 113 of 113, WTA 119 of
 *  119; the week before, 11 of 35 and 13 of 42). */
export const START_ERA_FROM = Date.parse('2026-04-20T05:00:00Z');
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
/** Stage hold's batch (Amendment 4 item 7): the 10 hottest family A hot spots of the league (the report's ranking by z on a
 *  disc run), { league_run, batch: [{ id: '<config id without its arm>', leg: 'underdog' | 'fav' | 'both' }] }. A hold run
 *  executes those configs' |window and |F1 arms only, once: the file's sha256 (batchHash) goes into the openings ledger. */
export const HOLD_BATCH = 'research/tennis-ta/hold-batch.json';
/** The most hot spots a batch may name (item 7: the 10 hottest). */
export const HOLD_BATCH_MAX = 10;
/** The openings ledger (C10, Amendment 4 item 7): one JSON line {hash, run, ts, ids, pool: 'hold'} per batch read on
 *  H-HOLD (hash = the batch file's sha256, batchHash). prep refuses a batch whose hash is in it; the report job appends
 *  the run's line once its shard set is complete, before anything is scored (idempotent by run id). */
export const OPENINGS_LEDGER = 'gdrive:kalshi-bot-archive/models/tennis-ta/state/openings.jsonl';
/** Amendment 4 item 9: the bot's recordings before this (Nov 10 03:44 UTC, Nov 9 10:44 PM EST) sat on empty order-book
 *  reads and are practice data. On R a match starting before it is pool 'practice' (recordedPoolOf): never requestable,
 *  never scored, never pooled with later days. Kalshi's own history (H) is unaffected. research/tennisTaData.ts holds
 *  a copy (the download job does not load the sim); tests/tennisTaData.test.ts holds the two together. */
export const FULL_BOOK_FROM = Date.parse('2026-11-10T03:44:00Z');
/** The pools a request may name (C10): 'disc' (stages 1 and 2), 'old' (stage 2 finalists) and 'hold' (stage hold). */
export const REQUESTABLE_POOLS: ReadonlyArray<Pool> = ['disc', 'old', 'hold'];
/** The stages: 1 (the H grid), 2 (research/tennis-ta/stage2-specs.json) and hold (research/tennis-ta/hold-batch.json). */
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
 *  hold) and 'hold' (H-HOLD: a start-era match starting from HOLD_FROM). 'practice' (Amendment 4 item 9) is the recorded
 *  stratum's only: a match of the bot's recordings starting before FULL_BOOK_FROM (recordedPoolOf), never scored. */
export type Pool = 'old' | 'nostart' | 'disc' | 'embargo' | 'hold' | 'out' | 'practice';
export const POOLS: ReadonlyArray<Pool> = ['old', 'nostart', 'disc', 'embargo', 'hold', 'out', 'practice'];
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

/** A recorded (R) match's pool (Amendment 4 item 9): 'practice' when its start is before FULL_BOOK_FROM (the bot's
 *  recordings before the Nov 10 03:44 UTC book fix: never scored, never pooled with later days), else poolOf. The
 *  recorded cut (research/tennisTaData.ts recordedTennis) labels whole days the same way (every line before it). */
export function recordedPoolOf(m: PoolMatch, units: Unit[], opened: Set<string> = new Set(), cutoff = HARD_CUTOFF): Pool {
  return m.start < FULL_BOOK_FROM ? 'practice' : poolOf(m, units, opened, cutoff);
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
/** A spec as the sweep runs it: the sim's SimSpec with the sweep's tags: stick (a measuring stick) and window (a window arm
 *  of the one test, Amendment 4: the sim takes its entry decisions as virtual taker buys and reports them as
 *  SimRun.instances; the fill models play no part, fill is F1 by convention). */
export type SweepSpec = SimSpec & { stick?: true; window?: true };

/** The arms of a config: the fills, the coin placebo, the window arm (fill F1, window: true) and the window arm's coin
 *  placebo (|coinwindow: placebo 'coin', window: true). The report and the registry read the arm from the id's end. */
export const ARMS = ['F0', 'F1', 'F2', 'coin', 'window', 'coinwindow'] as const;
export type Arm = typeof ARMS[number];
/** The arm a spec runs as, from its fields (what its id must end with). */
export const armOf = (s: { fill: string; placebo?: string; window?: true }): string =>
  (s.window ? (s.placebo === 'coin' ? 'coinwindow' : 'window') : s.placebo === 'coin' ? 'coin' : s.fill);
/** The config of a spec id: the id without its arm. */
export const configOf = (id: string): string => id.replace(ARM_SUFFIX, '');
const ARM_SUFFIX = new RegExp(`\\|(${ARMS.join('|')})$`);

const PROD = { TENNIS_CONF_MOMENTUM_CENTS: 0.01, TENNIS_CONF_FLOW: 0.2, TENNIS_CONF_OPPONENT_CENTS: 0.01, TENNIS_CONF_WINDOW_SEC: 60 };
/** Section 4: the LiquidityRatchet (book-wall trailing stop) means nothing on H's one-level synthetic book; H runs it off. */
const H_FIXED = { TENNIS_TRAIL_RATCHET: false };

/** Stage 1 (H): momentum x flow x opponent x window (3 x 3 x 3 x 3 = 81 configs; production's point is in the grid), each
 *  under F1, F2, its coin-flip placebo (F1), its window arm (the one test, Amendment 4) and the window arm's coin placebo
 *  (|coinwindow), plus two measuring sticks at production, the settle-hold arm (production's end loser cut off,
 *  TENNIS_END_LOSER_CUT=false) and the pacer-off arm, each under F1 and as a window arm. History windows are at least
 *  60 s. Every spec runs with the ratchet off (section 4). 81 x 5 + 2 x 2 = 409 specs. */
export function stage1Specs(): SweepSpec[] {
  const specs: SweepSpec[] = [];
  for (const m of [0.005, 0.01, 0.02]) for (const f of [0.05, 0.2, 0.4]) for (const o of [0.005, 0.01, 0.02]) for (const w of [60, 120, 300]) {
    const overrides = { TENNIS_CONF_MOMENTUM_CENTS: m, TENNIS_CONF_FLOW: f, TENNIS_CONF_OPPONENT_CENTS: o, TENNIS_CONF_WINDOW_SEC: w, ...H_FIXED };
    const id = `A|s1|m${m}|f${f}|o${o}|w${w}`;
    specs.push({ id: `${id}|F1`, overrides, fill: 'F1' }, { id: `${id}|F2`, overrides, fill: 'F2' }, { id: `${id}|coin`, overrides, fill: 'F1', placebo: 'coin' },
      { id: `${id}|window`, overrides, fill: 'F1', window: true }, { id: `${id}|coinwindow`, overrides, fill: 'F1', placebo: 'coin', window: true });
  }
  const sticks: Array<[string, SimSpec['overrides']]> = [
    ['settlehold', { ...PROD, ...H_FIXED, TENNIS_END_LOSER_CUT: false }],
    ['nopacer', { ...PROD, ...H_FIXED, HARNESS_PACER: 'off' }],
  ];
  for (const [name, overrides] of sticks) {
    specs.push({ id: `A|s1|prod|${name}|F1`, overrides, fill: 'F1', stick: true }, { id: `A|s1|prod|${name}|window`, overrides, fill: 'F1', stick: true, window: true });
  }
  return specs;
}

const SPEC_KEYS = new Set(['id', 'overrides', 'fill', 'placebo', 'stick', 'offsetMs', 'window']);

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
/** A spec list's tags for its shard runs[] entries (C4): stick: true on measuring sticks, window: true on window arms, and
 *  the spec's offsetMs when it sets one (the sim's run drops them; the report's twin and cross-file checks read them, and
 *  the registry row its env). */
export function runTags(specs: SweepSpec[]): Map<string, { stick?: true; window?: true; offsetMs?: number }> {
  return new Map(specs.map((s) => [s.id, { ...(s.stick ? { stick: true as const } : {}), ...(s.window ? { window: true as const } : {}), ...(s.offsetMs !== undefined ? { offsetMs: s.offsetMs } : {}) }]));
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

/** A stage 2 id is 'A|s2|<config>|<arm>' where the arm is the fill (F0, F1, F2), 'coin' for the coin placebo, 'window' for
 *  the window arm or 'coinwindow' for the window arm's coin placebo (ARMS); measuring sticks are 'A|s2|prod|<name>|<arm>'
 *  and nothing else is. */
const S2_PREFIX = 'A|s2|';
const S2_ID = new RegExp(`^A\\|s2\\|(.+)\\|(${ARMS.join('|')})$`);
const S2_STICK = /^A\|s2\|prod\|.+\|[^|]+$/;
/** The harness rules' defaults (the sim's, SimSpec in research/tennisTaSim.ts): an arm with every HARNESS_* key unset or at
 *  these values runs production's harness. */
const HARNESS_DEFAULTS: Readonly<Record<string, OverrideValue>> = { HARNESS_PACER: 'tennis', HARNESS_LOSER_STOP: 0, HARNESS_BANKROLL: 200, HARNESS_FEE_MULT: 1, HARNESS_LATENCY_MS: 0 };

/** Validate stage 2's spec list (research/tennis-ta/stage2-specs.json): an array of {id, overrides, fill, placebo?,
 *  window?} with unique ids 'A|s2|<config>|<arm>', the arm suffix agreeing with the spec (|coin for the coin placebo,
 *  |window for a window arm, |coinwindow for a window arm's coin placebo, else |F0, |F1 or |F2 as its fill); optional
 *  stick: true (measuring stick, id 'A|s2|prod|<name>|<arm>', and every such id is a stick) and offsetMs (noise-floor
 *  clock phase). A window arm (window: true, the one test of Amendment 4) runs fill F1 (the fill models play no part in
 *  it). Every arm of one config (F0, F1, F2, coin, window, coinwindow) runs the same overrides, written alike (the
 *  report compares a config's arms as written, value types included), at one offsetMs; an F2 or coin arm needs its
 *  config's F1 arm, a coinwindow arm its config's window arm (the report pairs them as their controls). Stress
 *  adversaries and measuring settings (STICK_KEYS) are never hypotheses: only a stick moves one, and a stick runs
 *  production plus those settings (and HARNESS_LOSER_STOP, and offsetMs) only, so no threshold trial runs unscreened
 *  and uncounted as a stick. Overrides are env-style TENNIS_* / PACER_* / HARNESS_* keys with string, number or boolean
 *  values. Every TENNIS_* / PACER_* key must be one production's loadConfig reads (a misspelt key would run as the
 *  production default and still count) with a value loadConfig accepts, and each must change the simulated config
 *  (tennis and pacer) given the spec's other keys (a default value, or a key landing in a part of the config the sim
 *  does not run, is refused); every HARNESS_* key must be one the sim reads (HARNESS_RULES) with a valid value. Two arms
 *  that would run identically (same simulated config, harness rules, fill, window flag and clock phase; coin-placebo
 *  arms excepted, their streams are seeded by id) are refused, and so are two non-stick arms that differ only in the
 *  clock phase (a noise-floor adversary, section 7: a stick at production). On H every spec runs with
 *  TENNIS_TRAIL_RATCHET=false (section 4): it is written as the boolean false when unset or off ('false', '0'), and a
 *  spec that turns it on is refused. Every list this accepts passes the report's check_runs (the tests pipe accepted
 *  lists through it). Throws with every problem listed. */
export function validateStage2Specs(raw: unknown, stratum: 'H' | 'R' = 'H'): SweepSpec[] {
  const P = S2_PREFIX, label = 'stage 2 specs';
  const p: string[] = [];
  if (!Array.isArray(raw)) throw new Error(`${label}: expected a JSON array of {id, overrides, fill, placebo?, window?}`);
  if (!raw.length) throw new Error(`${label}: the list is empty`);
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
    if (s.window !== undefined && s.window !== true) p.push(`${at}: window must be true when set`);
    if (s.window === true && s.fill !== 'F1' && (s.fill === 'F0' || s.fill === 'F2')) p.push(`${at}: a window arm runs fill F1 (the fill models play no part in the one test: an instance is a taker buy at the ask, no order rests)`);
    if (s.offsetMs !== undefined && !(Number.isInteger(s.offsetMs) && (s.offsetMs as number) >= 0 && (s.offsetMs as number) < 5000)) p.push(`${at}: offsetMs must be an integer in [0, 5000)`);
    // The arm in the id (the report and the registry read the arm and the config from it).
    if (typeof s.id === 'string' && s.id.startsWith(P)) {
      const want = s.window === true ? (s.placebo === 'coin' ? 'coinwindow' : 'window') : s.placebo === 'coin' ? 'coin' : typeof s.fill === 'string' ? s.fill : undefined;
      const m = S2_ID.exec(s.id);
      if (!m) p.push(`${at}: id must be '${P}<config>|<arm>' with the arm ${want ? `|${want}` : ARMS.map((a) => `|${a}`).join(', ')} at its end`);
      else if (want && m[2] !== want) {
        const is = want === 'coinwindow' ? "the window arm's coin placebo (|coinwindow)" : want === 'window' ? 'a window arm (|window)' : want === 'coin' ? 'the coin placebo (|coin)' : `fill ${s.fill} (|${s.fill})`;
        p.push(`${at}: id ends |${m[2]} but the spec is ${is}`);
      }
      const stickId = S2_STICK.test(s.id);
      if (s.stick === true && !stickId) p.push(`${at}: a measuring stick's id is '${P}prod|<name>|<arm>'`);
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
        p.push(`${at}: override ${k}=${JSON.stringify(v)} is a stress adversary or measuring setting (section 7), never a hypothesis: only a measuring stick moves it (stick: true, id '${P}prod|<name>|<arm>')`);
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
        const h = (k: string, d: OverrideValue) => String(o[k] ?? d);
        // The window flag is part of what runs: a config's |F1 and |window arms are two arms, not twins.
        const key = JSON.stringify([r.sim, h('HARNESS_PACER', 'tennis'), Number(h('HARNESS_LOSER_STOP', 0)), Number(h('HARNESS_BANKROLL', 200)),
          Number(h('HARNESS_FEE_MULT', 1)), Number(h('HARNESS_LATENCY_MS', 0)), s.fill, s.window === true]);
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
      ...(s.offsetMs !== undefined ? { offsetMs: s.offsetMs as number } : {}), ...(s.stick ? { stick: true as const } : {}), ...(s.window ? { window: true as const } : {}) });
  });
  // A config's arms (every non-stick id 'A|s2|<config>|<arm>') run the same overrides, written alike: the report's
  // check_runs compares them as written (JSON, value types included: 0.4 and "0.4" differ there), at one clock phase. F2
  // and coin arms are the config's neighbour and placebo (paired with the config's F1 row); the coinwindow arm is the
  // window arm's placebo (paired with the config's window row).
  const configs = new Map<string, SweepSpec[]>();
  for (const x of out) {
    const m = S2_ID.exec(x.id ?? '');
    if (!m || x.stick) continue;
    configs.set(m[1], [...(configs.get(m[1]) ?? []), x]);
  }
  const asWritten = (v: unknown) => (v === undefined ? 'unset' : JSON.stringify(v));
  for (const [cfg, list] of configs) {
    const f1 = list.find((x) => x.id === `${P}${cfg}|F1`);
    const win = list.find((x) => x.id === `${P}${cfg}|window`);
    for (const x of list) {
      const arm = x.id.slice(x.id.lastIndexOf('|') + 1);
      if (!f1 && (arm === 'F2' || arm === 'coin')) p.push(`${x.id}: its config has no F1 arm (${P}${cfg}|F1): the report pairs the ${arm === 'coin' ? 'coin placebo' : 'F2 neighbour'} with the config's F1 row`);
      if (!win && arm === 'coinwindow') p.push(`${x.id}: its config has no window arm (${P}${cfg}|window): the report pairs the window arm's coin placebo with the config's window row`);
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
  if (p.length) throw new Error(`${label}: ${p.length} problem(s):\n  ${p.join('\n  ')}`);
  return out;
}

const canonValue = (v: OverrideValue): string => {
  if (typeof v !== 'string') return String(v);
  const t = v.trim();
  return /^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(t) ? String(Number(t)) : t;
};

/** The canonical form of a spec list (its identity: the shard metas' specsHash, C10): the specs sorted by id, each as
 *  [id, fill, placebo or null, stick, offsetMs (0 when unset), window, its overrides sorted by key with each value as the
 *  string the sim and loadConfig read (numbers by value: 0.4, "0.4" and "0.40" are one value)]. Re-ordering the file,
 *  re-spacing it or re-spelling a number leaves it unchanged; any change to what runs or to an id changes it. */
export function canonicalSpecs(specs: SweepSpec[]): string {
  return JSON.stringify([...specs].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)).map((s) => [s.id, s.fill, s.placebo ?? null, s.stick === true, s.offsetMs ?? 0, s.window === true,
    Object.keys(s.overrides).sort().map((k) => [k, canonValue(s.overrides[k])])]));
}

/** sha256 (hex) of canonicalSpecs: the spec list's identity in every shard meta (specsHash). */
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

// ---------------------------------------------------------------------------------------------------------------------
// Stage hold: the batch of the one read (Amendment 4 item 7)

export const HOLD_LEGS = ['underdog', 'fav', 'both'] as const;
export type HoldLeg = typeof HOLD_LEGS[number];
/** One hot spot of the batch: a config (a stage 1 grid config or stick, 'A|s1|...', or a stage 2 spec, 'A|s2|<config>',
 *  without its arm) and its leg ('both' pools the two). */
export interface HoldBatchMember { id: string; leg: HoldLeg }
export interface HoldBatch {
  /** The GitHub run id of the league the batch was read off (research/tennis-ta/hold-batch.json "league_run"). */
  leagueRun: string;
  batch: HoldBatchMember[];
  /** What the read runs: each batch config's |window arm and |F1 arm (and nothing else), in batch order. */
  specs: SweepSpec[];
}
const BATCH_KEYS = new Set(['league_run', 'batch']);
const MEMBER_KEYS = new Set(['id', 'leg']);

/** Validate a hold batch (research/tennis-ta/hold-batch.json): { league_run: '<GitHub run id>', batch: [{ id, leg }] }
 *  with at most HOLD_BATCH_MAX members, each a config id without an arm ('A|s1|...' resolving to a stage 1 grid config or
 *  measuring stick, or 'A|s2|<config>' resolving to the stage 2 spec list's '<id>|F1' arm) and a leg 'underdog', 'fav'
 *  or 'both', no (id, leg) twice. `stage2` is the validated stage 2 list a stage 2 member resolves against, or the path
 *  of its file (STAGE2_SPECS by default; read only when a member needs it). The specs out are every distinct config's
 *  |window arm and |F1 arm (a stage 2 config's window arm is its own '<id>|window' spec when the file has one, else its
 *  F1 arm with window: true). Throws with every problem listed. */
export function validateHoldBatch(raw: unknown, stage2: SweepSpec[] | string = STAGE2_SPECS): HoldBatch {
  const p: string[] = [];
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('hold batch: expected a JSON object { league_run: "<GitHub run id>", batch: [{ id, leg }] }');
  const r = raw as Record<string, unknown>;
  for (const k of Object.keys(r)) if (!BATCH_KEYS.has(k)) p.push(`unknown key ${k} (allowed: league_run, batch)`);
  const leagueRun = typeof r.league_run === 'string' && /^\S+$/.test(r.league_run) ? r.league_run : undefined;
  if (leagueRun === undefined) p.push(`league_run must be the league run's GitHub run id (a non-empty string without spaces), got ${JSON.stringify(r.league_run)}`);
  if (!Array.isArray(r.batch)) { p.push(`batch must be an array of { id, leg }, got ${JSON.stringify(r.batch)}`); throw new Error(`hold batch: ${p.length} problem(s):\n  ${p.join('\n  ')}`); }
  if (!r.batch.length) p.push('batch is empty: the read needs at least one hot spot');
  if (r.batch.length > HOLD_BATCH_MAX) p.push(`batch names ${r.batch.length} hot spots: at most ${HOLD_BATCH_MAX} (the ${HOLD_BATCH_MAX} hottest family A hot spots by z on the league)`);
  const s1 = new Map(stage1Specs().map((s) => [s.id, s]));
  let s2: Map<string, SweepSpec> | undefined, s2Error: string | undefined;
  const stage2Of = (): Map<string, SweepSpec> | undefined => {
    if (s2 || s2Error) return s2;
    try {
      const list = typeof stage2 === 'string' ? specsFor('2', 'H', stage2) : stage2;
      s2 = new Map(list.map((s) => [s.id, s]));
    } catch (e) { s2Error = (e as Error).message; }
    return s2;
  };
  const seen = new Set<string>();
  const batch: HoldBatchMember[] = [];
  const specs: SweepSpec[] = [];
  const configs = new Set<string>();
  r.batch.forEach((x, i) => {
    const at = `batch[${i}]`;
    if (!x || typeof x !== 'object' || Array.isArray(x)) { p.push(`${at}: not an object { id, leg }`); return; }
    const m = x as Record<string, unknown>;
    for (const k of Object.keys(m)) if (!MEMBER_KEYS.has(k)) p.push(`${at}: unknown key ${k} (allowed: id, leg)`);
    const id = typeof m.id === 'string' ? m.id : undefined;
    const leg = (HOLD_LEGS as readonly unknown[]).includes(m.leg) ? (m.leg as HoldLeg) : undefined;
    if (id === undefined) p.push(`${at}: id must be a string: a config id without its arm (A|s1|m0.01|f0.2|o0.01|w60, A|s1|prod|settlehold, A|s2|<config>)`);
    if (leg === undefined) p.push(`${at}: leg must be 'underdog', 'fav' or 'both', got ${JSON.stringify(m.leg)}`);
    if (id === undefined || leg === undefined) return;
    if (ARM_SUFFIX.test(id)) { p.push(`${at}: ${id} ends with an arm: a hot spot is a config (${configOf(id)}) and a leg; the read runs the config's |window and |F1 arms`); return; }
    const key = `${id}|${leg}`;
    if (seen.has(key)) { p.push(`${at}: ${id} / ${leg} is listed twice`); return; }
    seen.add(key);
    let f1: SweepSpec | undefined, win: SweepSpec | undefined;
    if (id.startsWith('A|s1|')) {
      f1 = s1.get(`${id}|F1`); win = s1.get(`${id}|window`);
      if (!f1 || !win) { p.push(`${at}: ${id} is not a stage 1 grid config or measuring stick (stage1Specs has no ${id}|window)`); return; }
    } else if (id.startsWith(S2_PREFIX)) {
      const list = stage2Of();
      if (!list) { p.push(`${at}: ${id} names a stage 2 config but the stage 2 spec list cannot be read: ${s2Error}`); return; }
      f1 = list.get(`${id}|F1`);
      if (!f1) { p.push(`${at}: ${id} is not a stage 2 config (the stage 2 spec list has no ${id}|F1)`); return; }
      win = list.get(`${id}|window`) ?? { ...f1, id: `${id}|window`, window: true };
    } else { p.push(`${at}: ${id} must start 'A|s1|' (a stage 1 grid config or stick) or 'A|s2|' (a stage 2 spec)`); return; }
    // A measuring stick is reported beside the league, never a hot spot (C4; Amendment 4 item 1: a hot spot is a config of the
    // gradient matrix or a stage 2 spec): refused here, at prep, so no read is spent on it (the report refuses it too).
    if (f1.stick || win.stick) { p.push(`${at}: ${id} is a measuring stick (C4: reported beside the league, never a hot spot; Amendment 4 item 1 names a config of the gradient matrix or a stage 2 spec): it cannot be read on H-HOLD`); return; }
    batch.push({ id, leg });
    if (!configs.has(id)) { configs.add(id); specs.push(win, f1); }
  });
  if (p.length) throw new Error(`hold batch: ${p.length} problem(s):\n  ${p.join('\n  ')}`);
  return { leagueRun: leagueRun!, batch, specs };
}

/** The batch file of a hold run: validated (validateHoldBatch), with the file's sha256 (batchHash: the openings ledger's
 *  key; any change to the file is a new batch) and its text. */
export function holdBatchFile(file = HOLD_BATCH, stage2Path = STAGE2_SPECS): HoldBatch & { hash: string; text: string } {
  if (!fs.existsSync(file)) throw new Error(`stage hold reads its batch from ${file}, which does not exist: write it from the league (the ${HOLD_BATCH_MAX} hottest family A hot spots by z, { league_run, batch: [{ id, leg }] }), list it in the registry and the project calendar, then request stage hold`);
  const buf = fs.readFileSync(file);
  let raw: unknown;
  try { raw = JSON.parse(buf.toString('utf8')); } catch (e) { throw new Error(`${file}: not valid JSON (${(e as Error).message})`); }
  return { ...validateHoldBatch(raw, stage2Path), hash: sha256(buf), text: buf.toString('utf8') };
}

/** The file a stage reads its specs from by default: stage 2's spec list, or stage hold's batch. */
export const specsPathOf = (stage: string): string => (stage === 'hold' ? HOLD_BATCH : STAGE2_SPECS);

/** The spec list of a stage: stage 1 from stage1Specs() (H only), stage 2 from its spec file (validateStage2Specs), stage
 *  hold from its batch file (holdBatchFile: the batch configs' |window and |F1 arms; `stage2Path` is the stage 2 list a
 *  stage 2 batch member resolves against). */
export function specsFor(stage: string, stratum: 'H' | 'R', specsPath = specsPathOf(stage), stage2Path = STAGE2_SPECS): SweepSpec[] {
  if (stage === '1') {
    if (stratum !== 'H') throw new Error('stage 1 is the H design (ratchet off, windows >= 60 s); an R sweep needs its own stage 2 spec list');
    return stage1Specs();
  }
  if (stage === '2') {
    if (!fs.existsSync(specsPath)) throw new Error(`stage 2 reads its spec list from ${specsPath}, which does not exist: commit it (array of {id, overrides, fill, placebo?, window?}, ids 'A|s2|...') before requesting stage 2`);
    let raw: unknown;
    try { raw = JSON.parse(fs.readFileSync(specsPath, 'utf8')); } catch (e) { throw new Error(`${specsPath}: not valid JSON (${(e as Error).message})`); }
    return validateStage2Specs(raw, stratum);
  }
  if (stage === 'hold') return holdBatchFile(specsPath, stage2Path).specs;
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
  if (pool === 'practice') return `pool 'practice' is never scored (Amendment 4 item 9: the bot's recordings before ${new Date(FULL_BOOK_FROM).toISOString().slice(0, 16)} UTC sat on empty order-book reads and are practice data, never pooled with later days): request 'disc', 'old' at stage 2, or 'hold' at stage hold`;
  if (pool === 'nostart' || pool === 'embargo' || pool === 'out') return `pool '${pool}' is never scored (C9: 'nostart' matches are excluded and counted in every run's coverage; embargoed and out matches are streamed past): request 'disc', 'old' at stage 2, or 'hold' at stage hold`;
  if (typeof pool !== 'string' || !REQUESTABLE_POOLS.includes(pool as Pool)) return `pool must be 'disc', 'old' (stage 2) or 'hold' (stage hold), one pool per run, got ${JSON.stringify(pool)}`;
  if (stage === 'hold' && pool !== 'hold') return `stage 'hold' scores pool 'hold' (H-HOLD) only, got pool ${JSON.stringify(pool)}`;
  if (pool === 'old' && stage !== undefined && stage !== '2') return `pool 'old' (stratum H0: units before the start era ${dayOf(START_ERA_FROM)}, no published start, the older settlement rule) is a stress test for stage 2 finalists only, got stage ${JSON.stringify(stage)}`;
  if (pool === 'hold' && stage !== undefined && stage !== 'hold') return `pool 'hold' (H-HOLD, ${H_HOLD[0]} to ${H_HOLD[1]}) is scored only by stage 'hold', once per batch (${HOLD_BATCH}, the one read of Amendment 4), got stage ${JSON.stringify(stage)}: choose hot spots on the league, 'disc' (H-DEV)`;
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
  if (stage === 'hold' && r.familyB === true) p.push('familyB is a discovery design (every cell is a hypothesis), never scored on H-HOLD: a hold run is family A\'s batch only (Amendment 4 item 7: family B hot spots are not read there)');
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
  /** sha256 of the stage's canonical spec list (canonicalSpecs) and its ids (stage hold: the batch configs' |window and
   *  |F1 arms). */
  specsHash: string;
  specIds: string[];
  /** The one test's row version every shard must carry (research/tennisTaWindow.ts WINDOW_VERSION). */
  windowVersion: string;
  /** Stage hold (Amendment 4 item 7): the batch file's sha256 (the openings ledger's key: a changed file is a new batch),
   *  the league run it was read off and its hot spots. */
  batchHash?: string;
  leagueRun?: string;
  batch?: HoldBatchMember[];
  /** Stage hold: the openings-ledger rows read (none of them holds batchHash). */
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
 *  to the stage's spec file (specsPathOf: stage 2's list, stage hold's batch; opts.stage2Path is the stage 2 list a
 *  stage 2 batch member resolves against). Stage hold also needs the openings ledger's text (opts.openings: the ledger
 *  as read from Drive, '' when it does not exist yet) and refuses a batch whose file hash (batchHash) is in it (Amendment
 *  4 item 7: the one read is one run per batch). */
export function prepare(requestText: string, unitsText: string, specsPath?: string, opts: { openings?: string; stage2Path?: string } = {}): Prep {
  let raw: unknown;
  try { raw = JSON.parse(requestText); } catch (e) { throw new Error(`sweep request: not valid JSON (${(e as Error).message})`); }
  const units = JSON.parse(unitsText) as Unit[];
  const bad = verifyUnits(units);
  if (bad.length) throw new Error(`unit table: ${bad.length} problem(s):\n  ${bad.slice(0, 20).join('\n  ')}`);
  const req = parseRequest(raw, units);
  const batchFile = specsPath ?? specsPathOf(req.stage);
  const batch = req.stage === 'hold' ? holdBatchFile(batchFile, opts.stage2Path) : undefined;
  const specs = batch ? batch.specs : specsFor(req.stage, 'H', batchFile, opts.stage2Path);
  const hash = specsHash(specs);
  let openingsRead: number | undefined;
  if (batch) {
    if (opts.openings === undefined) throw new Error(`stage hold needs the openings ledger (--openings F: ${OPENINGS_LEDGER} as read from Drive, an empty file when it does not exist yet): H-HOLD is read once per batch`);
    const rows = parseOpenings(opts.openings);
    const hit = rows.find((x) => x.hash === batch.hash);
    if (hit) throw new Error(`the batch ${batchFile} (sha256 ${batch.hash}) was already read on H-HOLD (run ${String(hit.run ?? '?')}, ${String(hit.ts ?? '?')}): the one read is one run per batch (Amendment 4 item 7). A new read needs a new batch, chosen on the league (H-DEV) and listed in the registry and the project calendar first`);
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
    specsHash: hash, specIds: specs.map((x) => x.id), windowVersion: WINDOW_VERSION,
    ...(batch ? { batchHash: batch.hash, leagueRun: batch.leagueRun, batch: batch.batch } : {}), ...(openingsRead !== undefined ? { openingsRead } : {}), plan, subPlans,
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
   *  the cross-match state stays production's), and is labelled 'nostart': the report leaves it out and counts it. On R
   *  'practice' counts the recorded matches starting before FULL_BOOK_FROM that the requested pool would otherwise have
   *  held (Amendment 4 item 9): never owned, streamed past, so nothing of theirs is in the file. */
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
   *  data.replay_version), and sha256 of the canonical spec list the slice ran (stage hold: the batch's arms). */
  replayVersion: number; specsHash: string;
  /** The one test's row version of the file's 'window' block (research/tennisTaWindow.ts WINDOW_VERSION, contract C12);
   *  every shard of a run carries the same one (checkShards). */
  windowVersion: string;
  [extra: string]: unknown;
}

/** One event of the slice as the 'window' block lists it (contract C12): the row arrays index into this list, in
 *  matchList order. endRule = the end-rule time of Amendment 4 item 4 from the production-default clock's grid (the
 *  first sample at which its latched progress reaches 1 - SETTLE_FRAC), the close when it never does or the match has no
 *  grid (one-legged, unresolved or delivered late). */
export interface WindowEvent { event: string; series: string; tour: 'ATP' | 'WTA'; unit?: string; day: string; start: number; close: number; endRule: number }
/** The shard file's 'window' block (contract C12): one row per window arm and leg (family A, from the sim's
 *  SimRun.instances through WindowAgg); the report pools a config's two legs into its 'both' row itself. */
export interface WindowBlock {
  version: string; settleFrac: number; orderUsd: number; twins: number; seed: number;
  events: WindowEvent[];
  rows: WindowRow[];
}
/** Family B's rows of the same shape (SignalStudy.exportWindow, the signals' own event sample as the instance), id
 *  '<reading>|<bar>|<dir>', leg omitted; its arrays index into the 'window' block's events (re-mapped from the study's
 *  own event list by the sweep). */
export interface FamilyBWindowBlock { version: string; rows: WindowRow[] }

export interface ShardOut {
  meta: ShardMeta;
  /** fold: the HO-1 fold (1..6) of a hold match's UTC day (holdFold), else null. */
  matchList: Array<MatchInfo & { pool: Pool; unit?: string; fold: number | null }>;
  /** The sim's runs without their episodes (compact rows, EPISODE_COLS) and without their window instances (the 'window'
   *  block holds those, aggregated). */
  runs: Array<Omit<SimRun, 'episodes' | 'instances'> & { episodes: unknown[][]; stick?: true; window?: true; offsetMs?: number }>;
  familyB?: FamilyBExport;
  window: WindowBlock;
  familyBWindow?: FamilyBWindowBlock;
}

/** The tour of a series (the registry's by_tercile: ATP / WTA). */
export const tourOf = (series: string): 'ATP' | 'WTA' => (/WTA/i.test(series) ? 'WTA' : 'ATP');

/** The minute-candle index of a slice (Amendment 4 item 4, the window rule's view): every stored market line of the
 *  series directories closing in the span the slice reads (seriesCoverage's `need`: [from - lookback, to + CLOSE_TAIL_DAYS)
 *  cut at the cutoff) parsed once, its candles kept as research/tennisTaWindow.ts MinuteCandles only (the first stored
 *  candle dropped, sorted, ending at or before the market's close). The sim asks for them by ticker (SweepOpts.candlesOf)
 *  when a window arm takes an instance or draws its twins. */
export function candleIndex(dirs: string[], from: string, to: string, lookbackDays = 1, stats?: MinuteCandleStats): Map<string, MinuteCandles> {
  const index = new Map<string, MinuteCandles>();
  const needFrom = Date.parse(from) - lookbackDays * DAY, needTo = Math.min(Date.parse(to) + CLOSE_TAIL_DAYS * DAY, HARD_CUTOFF);
  for (const dir of dirs) for (let t = needFrom; t < needTo; t += DAY) {
    eachLine(path.join(dir, `${dayOf(t)}.jsonl`), (line) => {
      let m: { ticker?: unknown; closeTime?: unknown; candles?: unknown };
      try { m = JSON.parse(line); } catch { return; }
      if (typeof m.ticker !== 'string' || !m.ticker || typeof m.closeTime !== 'number' || !Array.isArray(m.candles) || index.has(m.ticker)) return;
      index.set(m.ticker, minuteCandles(m.candles as KalshiCandle[], m.closeTime, stats));
    });
  }
  return index;
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
  const specsPath = a.specs ?? specsPathOf(stage);
  // Stage hold runs the batch's configs' |window and |F1 arms only (Amendment 4 item 7); the batch file's hash is recorded.
  const batch = stage === 'hold' ? holdBatchFile(specsPath, a['stage2-specs']) : undefined;
  const specs = batch ? batch.specs : specsFor(stage, stratum, specsPath, a['stage2-specs']);
  const sticks = new Set(specs.filter((s) => s.stick).map((s) => s.id));
  const windowArms = specs.filter((s) => s.window).map((s) => s.id);
  // stick: true, window: true and the spec's offsetMs on each runs[] entry (the sim's run carries none of them).
  const tags = runTags(specs);
  const byId = new Map(units.map((u) => [u.id, u]));
  const unitIds = a['units-list'] ? a['units-list'].split(',').filter(Boolean)
    : units.filter((u) => u.start >= Date.parse(a.from) && u.start < Date.parse(a.to)).map((u) => u.id);
  for (const id of unitIds) if (!byId.has(id)) throw new Error(`--units-list: unit ${id} is not in ${a.units}`);
  if (!unitIds.length) throw new Error(`no unit to sweep in [${a.from}, ${a.to})`);
  const unitSet = new Set(unitIds);
  const feeAt = a.fees ? feeLookup(JSON.parse(fs.readFileSync(a.fees, 'utf8'))) : undefined;
  const familyB = a['family-b'] === 'true';
  if (familyB && stage === 'hold') throw new Error('family B is a discovery design, never run on H-HOLD (stage hold reads family A\'s batch only, Amendment 4 item 7)');
  // The stratum is given up front: a slice with no owned two-market match has no grid to take it from, and exportCells
  // refuses a study without one.
  const study = familyB ? new SignalStudy({ ...FAMILY_B, stratum, ...(stratum === 'H' ? { bars: H_BARS } : {}) }) : undefined;
  // The start the sim used for ownership (published, else the earliest market-line time): a grid's unit comes from it,
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
  // The minute-candle index (the window rule's view of every market the slice reads, Amendment 4 item 4), parsed once
  // from the same day files and kept as MinuteCandles only; the sim reads it through candlesOf.
  // candleStats counts the minutes kept and those whose stored low was missing, so the close stood in for it (the window rule
  // reads the LOW; a substitution overstates it: 0 on Kalshi's history, which always stores the low; information in the meta).
  const candleStats = newMinuteCandleStats();
  const candles = a.hist ? candleIndex(series.map((s) => path.join(a.hist!, s)), a.from, a.to, lookback, candleStats) : new Map<string, MinuteCandles>();
  // Per event, from its grid: the production-default clock's end-rule time (the first sample at which its latched
  // progress reaches 1 - SETTLE_FRAC; absent when it never does) and the grid's own bookkeeping, for the events list.
  const endRuleOf = new Map<string, number>();
  const gridSeen = new Map<string, { series: string; day: string; start: number; unit?: string; close: number }>();
  // R only: the practice matches admit() streamed past (event -> unit), for Coverage.pools.practice.
  const practice = new Map<string, string>();
  const t0 = Date.now();
  const sweepOpts: SweepOpts & { candlesOf?: (ticker: string) => MinuteCandles | undefined } = {
    dir: a.replay, fromDay: a.from, toDay: a.to, lookbackDays: lookback, stratum, specs, feeAt,
    candlesOf: (ticker) => candles.get(ticker),
    admit: (m) => {
      const u = unitOf(m.start, units);
      const inSlice = u !== undefined && unitSet.has(u);
      // admit() is not told whether the start was published: a start-era match without one is admitted as its times
      // would place it with one and labelled 'nostart' in matchList below (Coverage.pools says why it still runs).
      const pm = { start: m.start, close: m.closeTime, startPublished: true };
      // On R the label is recordedPoolOf's (Amendment 4 item 9): a match of the bot's recordings starting before
      // FULL_BOOK_FROM is 'practice' whatever the H rules would make of its times, and is never owned, so none of its
      // episodes, days, window instances or grids reaches the shard file: it is streamed past like an out-of-pool
      // match and counted (Coverage.pools.practice) when the requested pool would otherwise have held it.
      const mp = stratum === 'R' ? recordedPoolOf(pm, units, opened) : poolOf(pm, units, opened);
      if (inSlice && mp === 'practice' && poolOf(pm, units, opened) === pool) practice.set(m.event, u ?? '');
      const ok = inSlice && mp === pool;
      if (ok) startOf.set(m.event, m.start);
      return ok;
    },
    // Every owned match's grid: its end rule and bookkeeping for the 'window' block, and family B's input when it runs.
    onGrid: (g: MatchGrid) => {
      const s = startOf.get(g.event) ?? g.start;
      g.unit = unitOf(s, units);
      // The sim sets startPublished on every grid (start = the published start, else the earliest market-line time); the
      // comparison below is only a fallback for a grid that lacks it.
      g.startPublished ??= g.start === s;
      gridPublished.set(g.event, g.startPublished);
      startOf.delete(g.event);
      if (g.progressHigh) { const e = endRuleTs(g.progressHigh, g.t0, 1000, Infinity); if (Number.isFinite(e)) endRuleOf.set(g.event, e); }
      gridSeen.set(g.event, { series: g.series, day: g.day, start: g.start, ...(g.unit !== undefined ? { unit: g.unit } : {}), close: g.t0 + g.closeIdx * 1000 });
      if (!study) return;
      // A start-era match without a published start is 'nostart' (excluded and counted): family B leaves it out too.
      const gu = g.unit !== undefined ? byId.get(g.unit) : undefined;
      if (!g.startPublished && gu && startEra(gu)) { familyBNoStart++; return; }
      study.addMatch(g);
    },
    log: (m) => console.log(`[tennis-ta] ${m}`),
  };
  const r = await runSweep(sweepOpts);
  // fold: a hold match's HO-1 fold by its UTC day (MatchInfo.day, the day of its start, which the report files its by_day
  // under), with exactly registry.py's edges. The label is the rule admit() owned the match by (on R recordedPoolOf: a
  // 'practice' match, item 9, is never owned, so none is listed here).
  const matchList = r.matchList.map((m) => {
    const pm = { start: m.start, close: m.close, startPublished: m.startPublished };
    const mp = stratum === 'R' ? recordedPoolOf(pm, units, opened) : poolOf(pm, units, opened);
    return { ...m, pool: mp, unit: unitOf(m.start, units), fold: mp === 'hold' ? holdFold(m.day) : null };
  });
  const noStart = matchList.filter((m) => !m.startPublished);
  const pools = poolCounts(matchList, pool);
  // R: the practice matches streamed past (never owned; admit() above), information beside the owned pools.
  if (stratum === 'R') pools.practice = { matches: practice.size, units: new Set(practice.values()).size };
  const coverage: Coverage = {
    span: [a.from, a.to],
    series: seriesCov,
    matches: matchList.length, noPublishedStart: noStart.length, noPublishedStartEvents: noStart.slice(0, 50).map((m) => m.event), pools, lostTickers: r.lost,
    feed: { gaps: r.gaps, gapMs: r.gapMs, blindGaps: r.blindGaps, liveDays: r.liveDays, blindDays: r.blindDays, lateGrids: r.lateGrids },
  };
  let gridStartMismatch = 0;
  for (const m of matchList) { const g = gridPublished.get(m.event); if (g !== undefined && g !== m.startPublished) gridStartMismatch++; }
  const exportB = study?.exportCells();
  // The 'window' block (contract C12): the slice's events in matchList order, then one row per window arm and leg from
  // the sim's instances (WindowAgg). Family B's rows (SignalStudy.exportWindow, when the study has it) are re-mapped
  // from the study's event list onto the same index before the rows are sized, so every row spans every event.
  const eventIndex = new Map<string, number>(matchList.map((m, i) => [m.event, i]));
  const events: WindowEvent[] = matchList.map((m) => ({
    event: m.event, series: m.series, tour: tourOf(m.series), ...(m.unit !== undefined ? { unit: m.unit } : {}), day: m.day, start: m.start, close: m.close,
    endRule: Math.min(endRuleOf.get(m.event) ?? Infinity, m.close),
  }));
  const bw = (study as (SignalStudy & { exportWindow?: () => { events: string[]; rows: WindowRow[] } }) | undefined)?.exportWindow?.();
  const bwIdx = (bw?.events ?? []).map((e) => {
    let i = eventIndex.get(e);
    if (i === undefined) {
      // A grid the slice does not own cannot reach the study; this is a guard, not a path.
      const gi = gridSeen.get(e);
      i = events.length;
      eventIndex.set(e, i);
      events.push({ event: e, series: gi?.series ?? '', tour: tourOf(gi?.series ?? ''), ...(gi?.unit !== undefined ? { unit: gi.unit } : {}), day: gi?.day ?? '', start: gi?.start ?? 0, close: gi?.close ?? 0, endRule: Math.min(endRuleOf.get(e) ?? Infinity, gi?.close ?? 0) });
    }
    return i;
  });
  const aggs = new Map<string, WindowAgg>();
  const aggOf = (id: string, leg: string) => { const k = `${id}\u0000${leg}`; let g = aggs.get(k); if (!g) { g = new WindowAgg(id, leg, eventIndex); aggs.set(k, g); } return g; };
  let windowInstances = 0;
  for (const x of r.runs as Array<SimRun & { instances?: WindowInstance[] }>) {
    if (!tags.get(x.id)?.window) continue;
    // Both legs' rows exist for every window arm, instances or none (the report pools them into the 'both' row).
    for (const leg of ['underdog', 'fav']) aggOf(x.id, leg);
    for (const inst of x.instances ?? []) { aggOf(x.id, inst.leg).add(inst); windowInstances++; }
  }
  const window: WindowBlock = { version: WINDOW_VERSION, settleFrac: SETTLE_FRAC, orderUsd: ORDER_USD, twins: TWINS, seed: PLACEBO_SEED, events, rows: [...aggs.values()].map((g) => g.row()) };
  const remap = (arr: number[]) => { const out = new Array<number>(events.length).fill(0); arr.forEach((v, j) => { if (bwIdx[j] !== undefined) out[bwIdx[j]] += v; }); return out; };
  const familyBWindow: FamilyBWindowBlock | undefined = bw ? { version: WINDOW_VERSION, rows: bw.rows.map((row) => ({ ...row, n: remap(row.n), w: remap(row.w), tn: remap(row.tn), tw: remap(row.tw) })) } : undefined;
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
        : pool === 'hold' ? 'history, H-HOLD (the one read: a batch read once), synthetic depth' : 'history, H-DEV, synthetic depth',
      doge_excluded: true, configs: specs.length, specsHash: specsHash(specs),
      sticks: [...sticks], poolSpans: poolSpans(units, pool, HARD_CUTOFF, unitSet),
      // The one test (Amendment 4, contract C12): the 'window' block's version, its arms, instances and rows; the
      // candle index the instances were judged on; stage hold's batch.
      windowVersion: WINDOW_VERSION, windowArms: windowArms.length, windowInstances, windowRows: window.rows.length, candleMarkets: candles.size,
      candleMinutes: candleStats.candles, candlesNoLow: candleStats.noLow,
      ...(familyBWindow ? { familyBWindowRows: familyBWindow.rows.length } : {}),
      ...(batch ? { batchHash: batch.hash, leagueRun: batch.leagueRun, batch: batch.batch } : {}),
      stateRestarts: 'cross-match state (pacer, caps, placebo streams) restarts at this slice\'s first unit edge',
      matches: r.matches, oneLegged: r.oneLegged, unresolved: r.unresolved, decisions: r.decisions, ms: Date.now() - t0,
      ...(study ? { familyBGrids: gridPublished.size, familyBStartMismatch: gridStartMismatch, familyBNoStart } : {}),
      written_utc: new Date().toISOString(), written_eastern: eastern(Date.now()), episodeCols: EPISODE_COLS,
    },
    matchList,
    runs: r.runs.map((x) => {
      const { instances: _instances, ...rest } = x as SimRun & { instances?: unknown };
      return { ...rest, ...tags.get(x.id), episodes: x.episodes.map((e) => EPISODE_COLS.map((c) => (e as unknown as Record<string, unknown>)[c] ?? 0)) };
    }),
    ...(exportB ? { familyB: exportB } : {}),
    window,
    ...(familyBWindow ? { familyBWindow } : {}),
  };
  fs.mkdirSync(path.dirname(path.resolve(a.out)), { recursive: true });
  fs.writeFileSync(a.out, zlib.gzipSync(JSON.stringify(out)));
  console.log(`[tennis-ta] wrote ${a.out}: ${r.matches} matches (${noStart.length} without a published start; pools ${Object.entries(pools).map(([k, c]) => `${k} ${c!.matches}`).join(', ')}), ${unitIds.length} unit(s), ${specs.length} configs${exportB ? `, family B ${exportB.cells.length} cells` : ''}, ${r.decisions} decisions, window ${windowArms.length} arm(s) / ${windowInstances} instance(s) / ${window.rows.length} row(s) over ${candles.size} candle market(s) (${candleStats.candles} minute(s), ${candleStats.noLow} without a stored low), ${((Date.now() - t0) / 60_000).toFixed(1)} min`);
}

// ---------------------------------------------------------------------------------------------------------------------
// The report job's gate: every planned shard file present exactly once, from one run, one request, one data version

const ws = (b: number): boolean => b === 0x20 || b === 0x0a || b === 0x0d || b === 0x09;

/** The top-level members of a shard file named in `keys`, read by streaming the gzip once: a wanted member's bytes are
 *  kept and parsed, every other member's (runs, the bulk of a file) pass by unbuffered, and the read stops as soon as
 *  the last wanted member has closed (JSON.stringify wrote meta first, so ['meta'] reads the head alone). A member the
 *  file lacks is left out of the result; `maxBytes` bounds the bytes kept. */
export async function readShardParts(file: string, keys: readonly string[], maxBytes = 64 << 20): Promise<Partial<Record<string, unknown>>> {
  const want = new Set(keys);
  const src = fs.createReadStream(file);
  const gz = src.pipe(zlib.createGunzip());
  const head = Buffer.from('{"meta":');
  const found = new Map<string, Buffer[]>();
  // After the head the reader is in meta's value; then 'next' (',' or the closing '}'), 'key', 'keystr', 'colon', 'value'.
  let state: 'value' | 'next' | 'key' | 'keystr' | 'colon' = 'value';
  let key = 'meta', keyBytes: number[] = [], keep: Buffer[] | null = want.has('meta') ? [] : null, kept = 0;
  let pos = 0, depth = 0, inStr = false, esc = false, closed = false, done = false;
  const bad = (what: string) => new Error(`${file}: not a shard file (${what})`);
  try {
    for await (const c of gz as AsyncIterable<Buffer>) {
      let from = 0;
      const endValue = (end: number) => {
        if (keep) { keep.push(c.subarray(from, end)); kept += end - from; found.set(key, keep); keep = null; if (found.size === want.size) done = true; }
      };
      for (let i = 0; i < c.length && !done && !closed; i++, pos++) {
        const b = c[i];
        if (pos < head.length) { if (b !== head[pos]) throw bad('it does not start with {"meta":'); from = i + 1; continue; }
        if (state === 'value') {
          if (inStr) { if (esc) esc = false; else if (b === 0x5c) esc = true; else if (b === 0x22) { inStr = false; if (depth === 0) { endValue(i + 1); state = 'next'; } } continue; }
          if (b === 0x22) { inStr = true; continue; }
          if (b === 0x7b || b === 0x5b) { depth++; continue; }
          if ((b === 0x7d || b === 0x5d) && depth > 0) { depth--; if (depth === 0) { endValue(i + 1); state = 'next'; } continue; }
          if (depth === 0 && (b === 0x2c || b === 0x7d)) { endValue(i); state = 'next'; } // a scalar ends at its delimiter, read below as 'next'
          else continue;
        }
        if (state === 'next') {
          if (b === 0x2c) state = 'key';
          else if (b === 0x7d) closed = true;
          else if (!ws(b)) throw bad(`byte ${b} after ${key}`);
          continue;
        }
        if (state === 'key') {
          if (b === 0x22) { state = 'keystr'; keyBytes = []; }
          else if (!ws(b)) throw bad(`byte ${b} where a key should start`);
          continue;
        }
        if (state === 'keystr') {
          if (esc) { esc = false; keyBytes.push(b); }
          else if (b === 0x5c) { esc = true; keyBytes.push(b); }
          else if (b === 0x22) { key = JSON.parse(`"${Buffer.from(keyBytes).toString('utf8')}"`) as string; state = 'colon'; }
          else keyBytes.push(b);
          continue;
        }
        if (b === 0x3a) { state = 'value'; depth = 0; inStr = false; esc = false; keep = want.has(key) && !found.has(key) ? [] : null; from = i + 1; }
        else if (!ws(b)) throw bad(`byte ${b} after the key ${key}`);
      }
      if (done || closed) break;
      if (keep) { keep.push(c.subarray(from)); kept += c.length - from; }
      if (kept > maxBytes) throw new Error(`${file}: the ${[...want].join(', ')} member(s) are longer than ${maxBytes} bytes`);
    }
  } finally { gz.destroy(); src.destroy(); }
  if (!done && !closed) throw new Error(state === 'value' ? `${file}: the ${key} object never closes` : `${file}: the file ends before its members close`);
  const out: Partial<Record<string, unknown>> = {};
  for (const [k, bufs] of found) out[k] = JSON.parse(Buffer.concat(bufs).toString('utf8'));
  return out;
}

/** The meta object at the head of a shard file, read without inflating the rest (JSON.stringify wrote meta first). */
export async function readShardMeta(file: string, maxBytes = 64 << 20): Promise<ShardMeta> {
  return (await readShardParts(file, ['meta'], maxBytes)).meta as ShardMeta;
}

/** What the check reads of a shard file beyond its meta for the window gate: the matchList's events (the window block's
 *  order) and the 'window' and 'familyBWindow' members as parsed (unknown: windowBlockProblems types them). */
export interface ShardBlocks { events: string[]; window?: unknown; familyBWindow?: unknown }

/** The window arms of a spec list: the ids running as |window or |coinwindow (each writes an underdog and a fav row). */
export const windowArmsOf = (specIds: readonly string[]): string[] => specIds.filter((id) => /\|(window|coinwindow)$/.test(id));

const WINDOW_PHASES = ['pre', 'e20', 'p1', 'p2', 'p3'] as const;
const isCount = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0;
const isCounts = (v: unknown, n?: number): v is number[] => Array.isArray(v) && (n === undefined || v.length === n) && v.every(isCount);

/** Every problem with one shard file's one-test blocks (contract C12): the gate the report's read_shard applies, run
 *  here BEFORE a hold run's opening is appended to the ledger, so a run whose files carry a broken or incomplete window
 *  block fails without spending the batch's one read. The 'window' block must be there at the plan's version with the
 *  one test's constants; its events the matchList's, in order, each with a tour, a day and an end rule at or before its
 *  close; its rows exactly the plan's window arms x the two legs (at stage hold: every batch member's |window arm),
 *  each row's per-event arrays no longer than the events with windows never above instances, its hist over
 *  HIST_EDGES' bins, byPhase over the five phases, endNoWin and asks counts; and meta's window bookkeeping agreeing. A
 *  'familyBWindow' block, when the file has one, holds rows of the same shape indexing into the same events. */
export function windowBlockProblems(file: string, prep: Pick<Prep, 'specIds' | 'windowVersion' | 'stage'>, meta: ShardMeta, blocks: ShardBlocks): string[] {
  const p: string[] = [];
  const at = `${file}: window block`;
  if (blocks.events.length !== meta.coverage?.matches) p.push(`${file}: matchList has ${blocks.events.length} match(es), meta.coverage.matches says ${JSON.stringify(meta.coverage?.matches)}`);
  const arms = windowArmsOf(prep.specIds);
  const w = blocks.window as Partial<WindowBlock> | null | undefined;
  if (!w || typeof w !== 'object' || !Array.isArray(w.rows) || !Array.isArray(w.events)) {
    p.push(`${file}: no window block with events and rows (C12)${arms.length ? `: the plan's ${arms.length} window arm(s) have no rows` : ''}`);
    return p;
  }
  const version = prep.windowVersion ?? WINDOW_VERSION;
  if (w.version !== version) p.push(`${at} version ${JSON.stringify(w.version)}, expected ${JSON.stringify(version)}`);
  for (const [k, v] of [['settleFrac', SETTLE_FRAC], ['orderUsd', ORDER_USD], ['twins', TWINS], ['seed', PLACEBO_SEED]] as const) {
    if (w[k] !== v) p.push(`${at} ${k} ${JSON.stringify(w[k])}, the one test's is ${v}`);
  }
  // events: the matchList's in order (family B's own, when any, appended after them).
  const ev = w.events as Array<Partial<WindowEvent> | null>;
  if (ev.length < blocks.events.length) p.push(`${at} lists ${ev.length} event(s) for a matchList of ${blocks.events.length}`);
  else {
    const i = blocks.events.findIndex((e, j) => ev[j]?.event !== e);
    if (i >= 0) p.push(`${at} events are not in matchList order (first at index ${i})`);
  }
  const badEv = ev.findIndex((e) => !e || typeof e !== 'object' || typeof e.event !== 'string' || !e.event || (e.tour !== 'ATP' && e.tour !== 'WTA') || typeof e.day !== 'string'
    || !Number.isFinite(e.start) || !Number.isFinite(e.close) || !Number.isFinite(e.endRule) || (e.endRule as number) > (e.close as number));
  if (badEv >= 0) p.push(`${at} event ${badEv} (${JSON.stringify(ev[badEv]?.event)}) lacks an event, tour, day, start, close or an end rule at or before its close`);
  // rows: exactly the plan's window arms x legs, each once.
  const expect = new Map(arms.flatMap((id) => [[`${id}\u0000underdog`, [id, 'underdog']], [`${id}\u0000fav`, [id, 'fav']]] as Array<[string, [string, string]]>));
  const seen = new Set<string>();
  const rows = w.rows as Array<Partial<WindowRow> | null>;
  for (const r of rows) {
    const name = `${at} row ${JSON.stringify(r?.id)} / ${r?.leg}`;
    if (!r || typeof r !== 'object' || typeof r.id !== 'string' || (r.leg !== 'underdog' && r.leg !== 'fav')) { p.push(`${name}: no id, or a leg that is not underdog or fav`); continue; }
    const key = `${r.id}\u0000${r.leg}`;
    if (!expect.has(key)) p.push(`${name}: not a window arm of the plan`);
    else if (seen.has(key)) p.push(`${name}: appears twice`);
    seen.add(key);
    p.push(...rowProblems(name, r, ev.length));
  }
  for (const [key, [id, leg]] of expect) {
    if (!seen.has(key)) p.push(`${at} row ${id} / ${leg} missing${prep.stage === 'hold' ? ' (a batch member\'s read: every member\'s |window rows must be in every file before the opening is recorded)' : ''}`);
  }
  if (meta.windowRows !== rows.length) p.push(`${file}: meta.windowRows ${JSON.stringify(meta.windowRows)}, the block has ${rows.length} row(s)`);
  if (meta.windowArms !== arms.length) p.push(`${file}: meta.windowArms ${JSON.stringify(meta.windowArms)}, the plan has ${arms.length} window arm(s)`);
  // Family B's rows, when the file has them.
  const fb = blocks.familyBWindow as Partial<FamilyBWindowBlock> | null | undefined;
  if (fb !== undefined) {
    const atB = `${file}: familyBWindow block`;
    if (!fb || typeof fb !== 'object' || !Array.isArray(fb.rows)) p.push(`${atB} is not an object with rows`);
    else {
      if (fb.version !== w.version) p.push(`${atB} version ${JSON.stringify(fb.version)} differs from the window block's`);
      const seenB = new Set<string>();
      for (const r of fb.rows as Array<Partial<WindowRow> | null>) {
        const name = `${atB} row ${JSON.stringify(r?.id)}`;
        if (!r || typeof r !== 'object' || typeof r.id !== 'string' || !r.id) { p.push(`${name}: no id`); continue; }
        if (seenB.has(r.id)) p.push(`${name}: appears twice`);
        seenB.add(r.id);
        p.push(...rowProblems(name, r, ev.length));
      }
      if (meta.familyBWindowRows !== undefined && meta.familyBWindowRows !== fb.rows.length) p.push(`${file}: meta.familyBWindowRows ${JSON.stringify(meta.familyBWindowRows)}, the block has ${fb.rows.length} row(s)`);
    }
  } else if (meta.familyBWindowRows !== undefined) p.push(`${file}: meta.familyBWindowRows is set but the file has no familyBWindow block`);
  return p;
}

/** One C12 row's shape (window or familyBWindow): the per-event arrays, hist, byPhase, endNoWin and asks. */
function rowProblems(name: string, r: Partial<WindowRow>, nEv: number): string[] {
  const p: string[] = [];
  for (const k of ['n', 'w', 'tn', 'tw'] as const) if (!isCounts(r[k]) || r[k].length > nEv) p.push(`${name}: ${k} is not a list of counts over the ${nEv} event(s)`);
  if (isCounts(r.n) && isCounts(r.w) && r.w.some((x, i) => x > ((r.n as number[])[i] ?? 0))) p.push(`${name}: more windows than instances on an event`);
  if (isCounts(r.tn) && isCounts(r.tw) && r.tw.some((x, i) => x > ((r.tn as number[])[i] ?? 0))) p.push(`${name}: more twin windows than twin entries on an event`);
  const h = r.hist as Partial<Record<keyof typeof HIST_EDGES, unknown>> | null | undefined;
  if (!h || typeof h !== 'object' || (Object.keys(HIST_EDGES) as Array<keyof typeof HIST_EDGES>).some((k) => !isCounts(h[k], HIST_EDGES[k].length + 1))) p.push(`${name}: hist is not {tWin, lenWin, dip, held} counts over the HIST_EDGES bins`);
  const bp = r.byPhase as Record<string, unknown> | null | undefined;
  if (!bp || typeof bp !== 'object' || WINDOW_PHASES.some((ph) => !isCounts(bp[ph], 2))) p.push(`${name}: byPhase is not {pre, e20, p1, p2, p3: [n, w]}`);
  if (!isCount(r.endNoWin)) p.push(`${name}: endNoWin is not a count`);
  if (!Array.isArray(r.asks) || r.asks.length !== 2 || !isCount(r.asks[0]) || typeof r.asks[1] !== 'number' || !Number.isFinite(r.asks[1])) p.push(`${name}: asks is not [n, sum of asks]`);
  return p;
}

export interface CheckSummary {
  run: string; files: number; dataVersion: string; simVersion: string; replayVersion?: number; specsHash: string; windowVersion: string; batchHash?: string; requestSha: string; stage: string; pool: string;
  families: string[]; shards: number; subSlices: number; units: number; matches: number; noPublishedStart: number;
  /** The one test's blocks (C12): the plan's window arms, the files whose window block the gate read (windowBlockProblems)
   *  and the instances they hold (meta.windowInstances summed). */
  windowArms: number; windowBlocks: number; windowInstances: number;
  /** Owned matches and their units per pool, summed over the slices (Coverage.pools; units never repeat across slices). */
  pools: Partial<Record<Pool, { matches: number; units: number }>>;
  /** Per series over every slice: history day files, the download's complete listing (one tarball, so one value) and
   *  traded markets without a tape (summed over slices; neighbouring slices read a few of the same days). */
  series: Record<string, { first?: string; last?: string; spanDays: number; missing: string[]; listed?: { from: string; to: string }; tapesMissing: number }>;
}

/** Every problem with a run's shard set: `listing` = the names in the run's Drive shard folder (one line each, as
 *  rclone lsf prints them, duplicates included), `metas` = the metas of the files copied down, each with its one-test
 *  blocks (`blocks`, readShardParts) when the caller read them: the check command always does, so the C12 gate runs
 *  here, before a hold run's opening is recorded, and never first in the report. */
export function checkShards(prep: Prep, listing: string[], metas: Array<{ file: string; meta: ShardMeta; blocks?: ShardBlocks }>, run: string): { problems: string[]; summary: CheckSummary } {
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
  // Every shard carries the one test's 'window' block at one version (contract C12).
  one('windowVersion', ms.map((m) => m.windowVersion));
  if (prep.batchHash !== undefined) one('batchHash', ms.map((m) => m.batchHash));
  one('coverage.series first/last', ms.map((m) => m.coverage?.series && Object.fromEntries(Object.entries(m.coverage.series).map(([s, c]) => [s, [c.first, c.last, c.files]]))));
  const unitSeen = new Map<string, string>();
  let windowBlocks = 0;
  for (const { file, meta, blocks } of metas) {
    const want = (key: string, got: unknown, exp: unknown) => { if (JSON.stringify(got) !== JSON.stringify(exp)) p.push(`${file}: ${key} ${JSON.stringify(got)}, expected ${JSON.stringify(exp)}`); };
    // The one test's blocks (C12), whenever the caller read them: the window gate before anything is recorded or scored.
    if (blocks) { windowBlocks++; p.push(...windowBlockProblems(file, prep, meta, blocks)); }
    want('simVersion', meta.simVersion, SIM_VERSION);
    // The replay version the shard built its days with, the spec list it ran and, at stage hold, the batch file prep
    // checked against the openings ledger.
    want('replayVersion', meta.replayVersion, prep.replayVersion);
    want('specsHash', meta.specsHash, prep.specsHash);
    want('windowVersion', meta.windowVersion, prep.windowVersion ?? WINDOW_VERSION);
    if (prep.batchHash !== undefined) want('batchHash', meta.batchHash, prep.batchHash);
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
      windowVersion: prep.windowVersion ?? WINDOW_VERSION, ...(prep.batchHash !== undefined ? { batchHash: prep.batchHash } : {}), requestSha: prep.requestSha, stage: prep.stage, pool: prep.pool,
      families: prep.familyB ? ['A', 'B'] : ['A'], shards: prep.plan.length, subSlices: prep.expected.length, units: unitSeen.size,
      matches: ms.reduce((s, m) => s + (m.coverage?.matches ?? 0), 0), noPublishedStart: ms.reduce((s, m) => s + (m.coverage?.noPublishedStart ?? 0), 0), pools, series,
      windowArms: windowArmsOf(prep.specIds ?? []).length, windowBlocks, windowInstances: ms.reduce((s, m) => s + (isCount(m.windowInstances) ? m.windowInstances : 0), 0),
    },
  };
}

async function cmdCheck(a: Args): Promise<void> {
  const prep = JSON.parse(fs.readFileSync(a.prep!, 'utf8')) as Prep;
  const listing = fs.readFileSync(a.listing!, 'utf8').split('\n');
  const names = fs.readdirSync(a.dir!).filter((f) => f.endsWith('.json.gz')).sort();
  const metas: Array<{ file: string; meta: ShardMeta; blocks?: ShardBlocks }> = [];
  const p: string[] = [];
  for (const f of names) {
    // The meta and the one test's blocks (C12), the runs streamed past: the window gate runs here, before the ledger step.
    try {
      const parts = await readShardParts(path.join(a.dir!, f), ['meta', 'matchList', 'window', 'familyBWindow']);
      const ml = parts.matchList;
      if (!Array.isArray(ml)) throw new Error(`${f}: not a shard file (no matchList)`);
      const events = ml.map((m) => (m && typeof m === 'object' && typeof (m as { event?: unknown }).event === 'string' ? (m as { event: string }).event : ''));
      metas.push({ file: f, meta: parts.meta as ShardMeta, blocks: { events, window: parts.window, familyBWindow: parts.familyBWindow } });
    } catch (e) { p.push((e as Error).message); }
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
  console.log(`[tennis-ta] window block (C12): ${s.windowArms} arm(s) x 2 legs in the plan, read in ${s.windowBlocks} of ${s.files} file(s), ${s.windowInstances} instance(s)`);
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
      const p = prepare(fs.readFileSync(a.request!, 'utf8'), fs.readFileSync(a.units, 'utf8'), a.specs, { openings: a.openings !== undefined ? fs.readFileSync(a.openings, 'utf8') : undefined, stage2Path: a['stage2-specs'] });
      if (a.out) fs.writeFileSync(a.out, JSON.stringify(p, null, 1) + '\n'); else console.log(JSON.stringify(p));
      console.error(`[tennis-ta] stage ${p.stage}, pool ${p.pool}, ${p.configs} configs${p.familyB ? ' + family B' : ''}, ${p.units.length} unit(s) from ${p.plan[0].from} to ${p.plan[p.plan.length - 1].to}, ${p.plan.length} shard(s) x up to ${SUB_SHARDS} sub-slices = ${p.expected.length} file(s); specs ${p.specsHash.slice(0, 16)}`
        + (p.stage === 'hold' ? `; batch ${p.batchHash} (${p.batch!.length} hot spot(s) off league run ${p.leagueRun}: ${p.batch!.map((m) => `${m.id}/${m.leg}`).join(', ')}), not in the openings ledger (${p.openingsRead} row(s) read)` : ''));
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
