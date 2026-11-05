// Tennis TA rulebook trial: the sweep CLI the GitHub workflow runs (pre-registration and its amendments:
// /mnt/project-files/tennis-ta/preregistration.md; thread "Build a profitable tennis TA rulebook", Nov 5 2026).
//
//   units  --from D --to D [--out F]           the tournament-week unit table with the hashed seal (A3), calendar only
//   fees   --series S,S --out F                Kalshi fee changes per series (GET /series/fee_changes, show_historical)
//   days   --hist DIR --out DIR --from D --to D --series S,S   build history replay days (research/history/historyReplay.ts)
//   run    --replay DIR --from D --to D --stage 1 --pool disc --units F [--fees F] [--stratum H] --out F.json.gz
//   plan   --from D --to D --shards N          equal date slices for the shard matrix (JSON)
//
// Pools (Amendment 1, A3): history stops at Nov 5 02:00 UTC (Nov 4 9:00 PM EST); a match closing at or after Nov 6
// 05:00 UTC (L1 and later lockboxes) is out unless its week is opened; units are Monday 05:00 UTC weeks with each Grand
// Slam as one unit; a unit is sealed when sha256("tennis-ta-seal|" + its start date) begins with a number = 0 mod 3;
// matches within 24 h of a sealed unit are embargoed; dev-discovery = unsealed units starting before 2026-04-01, dev-check
// = the unsealed rest. A run scores one pool; sealed matches are streamed past, never simulated.

import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import { execSync } from 'child_process';
import type { FeeSchedule } from '../bot/fees';
import { buildHistoryReplay } from './history/historyReplay';
import { FEES, runSweep, type MatchInfo, type SimRun, type SimSpec } from './tennisTaSim';

export const SIM_VERSION = 'tennis-ta-sim/1';
const DAY = 86_400_000;
const WEEK = 7 * DAY;
/** History and inventory stop here (Nov 4 9:00 PM EST). */
export const HARD_CUTOFF = Date.parse('2026-11-05T02:00:00Z');
/** L1 opens Nov 6 05:00 UTC (00:00 EST): a match closing at or after this is out of every pool unless opened. */
export const LOCKBOX_FROM = Date.parse('2026-11-06T05:00:00Z');
/** Dev-check starts with the units starting on or after this date. */
export const CHECK_FROM = Date.parse('2026-04-01T00:00:00Z');
const EMBARGO = DAY;

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
  return parseInt(crypto.createHash('sha256').update(`tennis-ta-seal|${startDay}`).digest('hex').slice(0, 8), 16) % 3 === 0;
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
    const startDay = new Date(start).toISOString().slice(0, 10);
    units.push({ id: s ? `${s.name}-${startDay}` : `W-${startDay}`, start, end, startDay, ...(s ? { slam: s.name } : {}), sealed: sealedByHash(startDay) });
    t = end;
  }
  return units;
}

export type Pool = 'disc' | 'check' | 'sealed' | 'embargo' | 'out';

/** The pool a match belongs to, by its start (and close for the lockbox exclusion). `opened` = sealed unit ids already
 *  opened (they joined dev for good) and lockbox weeks marked opened. */
export function poolOf(start: number, close: number, units: Unit[], opened: Set<string> = new Set(), cutoff = HARD_CUTOFF): Pool {
  if (start >= cutoff) return 'out';
  if (close >= LOCKBOX_FROM && !opened.has(`lockbox-${mondayEdge(close)}`)) return 'out';
  const u = units.find((x) => start >= x.start && start < x.end);
  if (!u) return 'out';
  if (u.sealed && !opened.has(u.id)) return 'sealed';
  for (const s of units) if (s.sealed && !opened.has(s.id) && ((start >= s.start - EMBARGO && start < s.start) || (start >= s.end && start < s.end + EMBARGO))) return 'embargo';
  return u.start < CHECK_FROM ? 'disc' : 'check';
}

export const unitOf = (start: number, units: Unit[]): string | undefined => units.find((x) => start >= x.start && start < x.end)?.id;

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

const PROD = { TENNIS_CONF_MOMENTUM_CENTS: 0.01, TENNIS_CONF_FLOW: 0.2, TENNIS_CONF_OPPONENT_CENTS: 0.01, TENNIS_CONF_WINDOW_SEC: 60 };

/** Stage 1: momentum x flow x opponent x window (3 x 3 x 3 x 3 = 81 configs; production's point is in the grid), each
 *  under F1, F2 and its coin-flip placebo (F1), plus two measuring sticks at production: the settle-hold arm (no loser
 *  cut: production today, audit I117) and the pacer-off arm. History windows are at least 60 s. */
export function stage1Specs(): SimSpec[] {
  const specs: SimSpec[] = [];
  for (const m of [0.005, 0.01, 0.02]) for (const f of [0.05, 0.2, 0.4]) for (const o of [0.005, 0.01, 0.02]) for (const w of [60, 120, 300]) {
    const overrides = { TENNIS_CONF_MOMENTUM_CENTS: m, TENNIS_CONF_FLOW: f, TENNIS_CONF_OPPONENT_CENTS: o, TENNIS_CONF_WINDOW_SEC: w };
    const id = `A|s1|m${m}|f${f}|o${o}|w${w}`;
    specs.push({ id: `${id}|F1`, overrides, fill: 'F1' }, { id: `${id}|F2`, overrides, fill: 'F2' }, { id: `${id}|coin`, overrides, fill: 'F1', placebo: 'coin' });
  }
  specs.push({ id: 'A|s1|prod|settlehold|F1', overrides: { ...PROD, HARNESS_LOSER_CUT: false }, fill: 'F1' });
  specs.push({ id: 'A|s1|prod|nopacer|F1', overrides: { ...PROD, HARNESS_PACER: 'off' }, fill: 'F1' });
  return specs;
}

/** Equal date slices of [from, to] for the shard matrix. */
export function plan(from: string, to: string, shards: number): Array<{ k: number; from: string; to: string }> {
  const a = Date.parse(from), b = Date.parse(to);
  const days = Math.round((b - a) / DAY) + 1;
  const per = Math.ceil(days / shards);
  const out: Array<{ k: number; from: string; to: string }> = [];
  for (let k = 0; k < shards; k++) {
    const s = a + k * per * DAY;
    if (s > b) break;
    out.push({ k, from: new Date(s).toISOString().slice(0, 10), to: new Date(Math.min(b, s + (per - 1) * DAY)).toISOString().slice(0, 10) });
  }
  return out;
}

// ---------------------------------------------------------------------------------------------------------------------
// Output (one gzip JSON per shard; episodes as compact rows)

export const EPISODE_COLS = ['m', 'k', 't', 'leg', 'px', 'n', 'ph', 'sig', 'x', 'hold', 'pnl', 'br'] as const;

export interface ShardOut {
  meta: Record<string, unknown>;
  matchList: Array<MatchInfo & { pool: Pool; unit?: string }>;
  runs: Array<Omit<SimRun, 'episodes'> & { episodes: unknown[][] }>;
}

function sha(): string {
  try { return execSync('git rev-parse HEAD', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim(); } catch { return process.env.GITHUB_SHA ?? 'unknown'; }
}

const eastern = (t: number) => new Date(t).toLocaleString('en-US', { timeZone: 'America/New_York', hour12: false });

async function cmdRun(a: Args): Promise<void> {
  const units: Unit[] = JSON.parse(fs.readFileSync(a.units, 'utf8'));
  const opened = new Set<string>(a.opened ? (JSON.parse(fs.readFileSync(a.opened, 'utf8')) as string[]) : []);
  const pools = new Set((a.pool ?? 'disc').split(',') as Pool[]);
  const feeAt = a.fees ? feeLookup(JSON.parse(fs.readFileSync(a.fees, 'utf8'))) : undefined;
  const specs = a.stage === '1' ? stage1Specs() : (JSON.parse(fs.readFileSync(a.specs!, 'utf8')) as SimSpec[]);
  const stratum = (a.stratum ?? 'H') as 'H' | 'R';
  const t0 = Date.now();
  const r = await runSweep({ dir: a.replay, fromDay: a.from, toDay: a.to, stratum, specs, feeAt,
    admit: (m) => pools.has(poolOf(m.start, m.closeTime, units, opened)), log: (m) => console.log(`[tennis-ta] ${m}`) });
  const out: ShardOut = {
    meta: { sha: sha(), sim_version: SIM_VERSION, stage: a.stage, pools: [...pools], from: a.from, to: a.to, stratum,
      evidence: stratum === 'H' ? 'history, synthetic depth' : 'recorded books', doge_excluded: true, configs: specs.length,
      matches: r.matches, oneLegged: r.oneLegged, unresolved: r.unresolved, decisions: r.decisions, ms: Date.now() - t0,
      written_utc: new Date().toISOString(), written_eastern: eastern(Date.now()), episodeCols: EPISODE_COLS },
    matchList: r.matchList.map((m) => ({ ...m, pool: poolOf(m.start, m.close, units, opened), unit: unitOf(m.start, units) })),
    runs: r.runs.map((x) => ({ ...x, episodes: x.episodes.map((e) => EPISODE_COLS.map((c) => (e as unknown as Record<string, unknown>)[c] ?? 0)) })),
  };
  fs.mkdirSync(path.dirname(path.resolve(a.out)), { recursive: true });
  fs.writeFileSync(a.out, zlib.gzipSync(JSON.stringify(out)));
  console.log(`[tennis-ta] wrote ${a.out}: ${r.matches} matches, ${specs.length} configs, ${r.decisions} decisions, ${((Date.now() - t0) / 60_000).toFixed(1)} min`);
}

interface Args { [k: string]: string | undefined; from: string; to: string; out: string; replay: string; units: string }

function parseArgs(argv: string[]): Args {
  const a: Record<string, string> = {};
  for (let i = 0; i < argv.length; i++) if (argv[i].startsWith('--')) a[argv[i].slice(2)] = argv[i + 1]?.startsWith('--') || argv[i + 1] === undefined ? 'true' : argv[++i];
  return a as Args;
}

async function main(): Promise<void> {
  const [cmd, ...rest] = process.argv.slice(2);
  const a = parseArgs(rest);
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
    case 'run':
      await cmdRun(a);
      break;
    case 'plan':
      console.log(JSON.stringify(plan(a.from, a.to, Number(a.shards ?? 8))));
      break;
    default:
      throw new Error(`unknown command ${cmd}: units | fees | days | run | plan`);
  }
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) void main().catch((e) => { console.error(e); process.exitCode = 1; });
