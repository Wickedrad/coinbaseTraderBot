// Tennis TA rulebook trial, family B: TA-Lib readings of the match price path and the production confluence signals as
// a sterile, entry-locked event study (pre-registration /mnt/project-files/tennis-ta/preregistration.md, section 5
// "Family B" as changed by Amendment 1: A1 staged design, A5 controls, A7 cells). Every trigger series is evaluated per
// match on the 1-second MatchGrid; entries are taker buys of YES on one player, exits are the fixed exit set under
// Steven's settlement rule, and every cell gets a circular-shift placebo, a one-tick exit stress and day-clustered
// accumulators (research/tennisTaTypes.ts ClusterAcc). Realized net $ after fees is the only score.
//
// Price and bars
//   pA[i] = MatchTracker.probability: (midA + 1 - midB) / 2 when both books have bid and ask (ask >= bid), else the one
//   that exists (1 - midB for B), NaN when neither. Bars (A7: logit(mid) bars built from 5 s mids, as the bot would):
//   bar k covers samples [kL, (k+1)L) and reads pA only at the 5 s marks (samples 4, 9, 14, ...; the bar's last sample
//   is one); close = last non-NaN value at or before the bar end (carried forward across bars and gaps), high/low over
//   the bar's marks including the carried open; volume = all taker contracts of both markets in the bar; signed flow
//   toward A = (yesVolA - noVolA) - (yesVolB - noVolB). A bar is acted on at the sample right after its end (decision
//   d = (k+1)L), the fill one latency later. Bars start at the first bar with a close (a leading NaN would poison
//   TA-Lib's recursive smoothers); only whole bars are built. pA is clipped to [0.01, 0.99] before every logit.
//   Bar lengths: 1 m and 5 m on H; 10 s and 30 s too on R (A1: one-level minute books make shorter bars near copies).
//
// Readings (TA-Lib through bot/ta/talib.ts tl(), once per match per bar length on the full causal series, on logit bars)
//   RSI14, STOCH14_3_3 (slowK), WILLR14, CCI14, BBP20_2 (%B of BBANDS 20/2): trigger exitExt (BBP: reenter) = leaving an
//     extreme: crossing up through the low level -> long A, down through the high level -> long B (RSI 30/70, STOCH
//     20/80, WILLR -80/-20, CCI -100/+100, %B 0/1).
//   MFI14: same trigger (20/80), from bar H/L/C of pA itself, not logit: MFI weighs typical price x volume, which turns
//     meaningless when the logit typical price is negative.
//   MACDH12_26_9L (MACD histogram), SLOPE14L (LINEARREG_SLOPE 14), MOM10L (MOM 10: ROC = x / x_prev - 1 is meaningless
//     on a logit that changes sign), OBVS14 (LINEARREG_SLOPE 14 of OBV = cumulative signed taker flow toward A; the tape
//     gives the true sign, so TA-Lib's price-signed OBV is not used): trigger zeroX = sign change (up -> long A).
//   ADX14L: section 5 used ADX >= 25 as a trend/chop context; A1 defines a cell as series x phase x price bucket (x
//     TA-Lib column) and A7 lists ADX among the TA-Lib columns, so ADX is a column here: trigger thrX = ADX crosses up
//     through 25, long the side PLUS_DI vs MINUS_DI favours (A on a tie). NATR (A7) has no direction and KAMA efficiency
//     ratio / ATR (section 5 conditions) have no place in the A1 cell, so they are not computed.
//   The two extremes are ONE trigger: market A is just the first ticker in sort order, and RSI(1 - p) = 100 - RSI(p), so
//   "RSI leaves 30 on A" and "RSI leaves 70 on B" are the same hypothesis seen from the two markets (one canonical side
//   per match). The price bucket still separates the cheap side from the dear one.
//   Masks: (1) flat: both bars of a crossing (k-1 and k) need a pA change inside the reading's lookback (14 bars; STOCH
//   16, BBP 20, MOM 10, MACDH 9); MFI also taker volume and OBVS signed flow in its 14 bars (TA-Lib returns 0 for
//   RSI/WILLR/STOCH/MFI on flat input, a false extreme). (2) warm-up: nothing before TA-Lib's begIndex (its NaN).
//   (3) A7 jump mask: no TA entry whose decision falls within 3 minutes after a 1-minute pA move of 10c or more (any
//   60 s window of the carried pA); applied at entry time, so the placebo is masked the same way.
//
// Confluence primitives (bot/tennis/tennisStrategy.ts tennisConfluence semantics, on the 1 s grid, both players)
//   MOM: mid of player X rose >= level over the window (production midChange: first valid mid at or after now - w vs
//   the latest valid mid, span >= w/2); OPP: the other market's mid fell >= level; FLOW: (YES - NO) / total taker
//   contracts on X's market over the window >= level; DEPTH: imbX >= level (R only; it never fires on H, A5).
//   Trigger = the signal toward X turns on (off at i-1, on at i; nothing at i = 0); follow buys X.
//   Variants: MOM and OPP at {0.005, 0.01, 0.02, 0.04} with window 60 s plus windows {120, 300} s at the default 0.01
//   (and {15, 30} s on R only, A1); FLOW at {0.05, 0.2, 0.4, 0.7} with window 60 s; DEPTH at {0.1, 0.2, 0.4, 0.7} (R).
//
// Entries (A1: entry-locked; each entry set computed once, the fixed exits reuse it)
//   A series' triggers are walked in time order. A trigger is an entry when its decision comes after the lock and at
//   least one direction can take it: follow buys the side the trigger names, fade the other side; a direction takes it
//   when that side has a bid and an ask at fill = decision + latencySec (rounded up to whole samples), the spread is
//   <= 5c, the fill is before closeIdx, and, for fade only, the ask is within [0.10, 0.90] (A7: no fades above 90c or
//   below 10c; applied to every family B series). Taker buy of YES at the ask, count = max(1, floor(orderUsd / ask)).
//   Both directions and all five exits are evaluated on that one entry; the lock then runs until the last of those
//   positions has closed (a position that rides or breaches locks the series for the rest of the match). So each cell
//   holds at most one position at a time, follow and fade are the same entry set (the reversed-direction adversary),
//   and every entry goes to its context cell AND to the 'all' cell. A later trigger may re-enter.
// Exits (from the sample after the fill): ts2m / ts10m time stops; tp30sl30 and tp50sl25 brackets on the bid, relative
//   to the entry price, with a 15 min stop; trail3t: armed once the bid >= entry + 2c, exit when the bid <= peak - 3
//   ticks, 15 min stop. A stop that finds no bid sells at the next sample with one. Every exit is a taker sell at the
//   bid; fees are bot/fees.ts orderFee per order (taker, multipliers 1/1, rounded up to the cent).
// Settlement rule (Steven, section 4): applied at the first sample after the fill where one of its conditions TURNS ON
//   while the position is open: decided (pA >= 0.97 or <= 0.03; a flicker off and back on is a new turn-on), progress
//   reaches 0.70, or the sample is closeIdx. There the position rides to settlement only if its net after both fees at
//   the current bid is > 0 (payout count x won, no settlement fee); otherwise it is sold at that bid (with no bid: at the
//   next sample with one; with none up to closeIdx it settles and counts as a breach). A position opened while a
//   condition is already on is not cut at birth (that would make every late and decided-price cell a certain loser of
//   spread plus two fees): it keeps its exit and meets the rule at the next turn-on or at closeIdx. When the rule's
//   sample coincides with a bracket or trail hit, the rule wins.
// Stress (CellResult.stress): the same entries and exit decisions, every sale one tick (0.01) lower, floored at 0.01, its
//   fee recomputed; settlement payouts unchanged.
//
// Contexts (A1/A7 cell = series x match phase x price bucket; section 5's band x phase x trend grid is replaced):
//   tour series (g.series, e.g. KXATPMATCH) x phase at the decision {pre (before liveIdx or never live), first20 (the
//   first 20 min after liveIdx), t1 / t2 / t3 (then progress < 1/3, < 2/3, >= 2/3)} x price bucket of the ask paid
//   {b08-15 [0.08, 0.15), b15-25 [0.15, 0.25), b75-85 [0.75, 0.85), b85-92 [0.85, 0.92], other}, plus 'all'. Best-of-3
//   vs best-of-5 (A7) cannot be told from a MatchGrid (no title or tournament), so it is not a context.
//
// Placebo (CellResult.placebo, pairDiff): each series' trigger list (decision and side) shifted circularly inside
//   [0, closeIdx] by an offset drawn from [600, closeIdx + 1 - 600] (seeded by seed and the event name, one draw per
//   series); no placebo when closeIdx + 1 < 1200 samples. Placebo triggers go through exactly the same entry rule (jump
//   mask and fade band included), lock, exits and context classification (their own context at the shifted time).
//   pairDiff is per day (the cell's day sum minus its placebo's day sum) over days where either had an entry; entries
//   from matches without a placebo stay out of the pairing (they are still in total) so the pairing is like for like.
//
// Universe (A5): an H match with no tape on either market is skipped and counted (diagnostics().noTape).
// Zero-volume minutes (A7: flagged): entries whose decision follows 60 s without a single taker contract on either
//   market are counted in diagnostics().zeroVolEntries; they are not masked.
//
// Design size (the m for Benjamini-Hochberg) = series x 2 directions x contexts x 5 exits, contexts = 1 + 25 x the tour
//   series seen. H: 11 TA columns x 2 bars + 16 primitives = 38 series (KXATPMATCH + KXWTAMATCH: 38 x 2 x 51 x 5 =
//   19,380 cells); R: 11 x 4 + 24 = 68 series (KXATPMATCH only: 68 x 2 x 26 x 5 = 17,680 cells).
//
// Statistics: ClusterAcc per cell, value = net $ per entry, cluster = g.day. cells() flushes the open day clusters, so
// call it once after the last addMatch of the run.

import { orderFee, type FeeSchedule } from '../bot/fees';
import { tl } from '../bot/ta/talib';
import { ClusterAcc, emptyStats, type CellResult, type ClusterStats, type MatchGrid, type PairDiff } from './tennisTaTypes';

/** Tennis pays maker and taker fees (multiplier 1 each); every order rounds up to the cent. */
export const FEES: FeeSchedule = { takerMultiplier: 1, makerMultiplier: 1 };

const BAR_LENS = [10, 30, 60, 300];
const BAR_NAMES = ['10s', '30s', '1m', '5m'];
/** Bar lengths that run on H (A1); the others need recorded books. */
const BAR_ON_H = [false, false, true, true];
const MID_STEP = 5;
const EXITS = ['ts2m', 'ts10m', 'tp30sl30', 'tp50sl25', 'trail3t'];
const N_EXIT = EXITS.length;
const PHASES = ['pre', 'first20', 't1', 't2', 't3'];
const BUCKETS = ['b08-15', 'b15-25', 'b75-85', 'b85-92', 'other'];
const N_PB = PHASES.length * BUCKETS.length; // 25 contexts per tour series
const MAX_TOURS = 64;
const CTX_STRIDE = 1 + N_PB * MAX_TOURS;
const DIRS = ['follow', 'fade'];

const TIME_STOP = [120, 600, 900, 900, 900];
const MAX_SPREAD = 0.05;
const FADE_MIN = 0.1;
const FADE_MAX = 0.9;
const DECIDED_HI = 0.97;
const DECIDED_LO = 0.03;
const LATE = 0.7;
const FIRST_PHASE_SEC = 20 * 60;
const PLACEBO_MIN = 600;
const JUMP = 0.1;
const JUMP_LAG = 60;
const JUMP_MASK = 180;
const EPS = 1e-9;

type TaKind = 'ext' | 'zero' | 'adx';
interface TaReading { name: string; trigger: string; kind: TaKind; lo: number; hi: number; look: number; mask: 'price' | 'flow' | 'priceVol' }
const TA_READINGS: TaReading[] = [
  { name: 'RSI14L', trigger: 'exitExt', kind: 'ext', lo: 30, hi: 70, look: 14, mask: 'price' },
  { name: 'STOCH14_3_3L', trigger: 'exitExt', kind: 'ext', lo: 20, hi: 80, look: 16, mask: 'price' },
  { name: 'WILLR14L', trigger: 'exitExt', kind: 'ext', lo: -80, hi: -20, look: 14, mask: 'price' },
  { name: 'CCI14L', trigger: 'exitExt', kind: 'ext', lo: -100, hi: 100, look: 14, mask: 'price' },
  { name: 'BBP20_2L', trigger: 'reenter', kind: 'ext', lo: 0, hi: 1, look: 20, mask: 'price' },
  { name: 'MACDH12_26_9L', trigger: 'zeroX', kind: 'zero', lo: 0, hi: 0, look: 9, mask: 'price' },
  { name: 'SLOPE14L', trigger: 'zeroX', kind: 'zero', lo: 0, hi: 0, look: 14, mask: 'price' },
  { name: 'MOM10L', trigger: 'zeroX', kind: 'zero', lo: 0, hi: 0, look: 10, mask: 'price' },
  { name: 'OBVS14', trigger: 'zeroX', kind: 'zero', lo: 0, hi: 0, look: 14, mask: 'flow' },
  { name: 'MFI14', trigger: 'exitExt', kind: 'ext', lo: 20, hi: 80, look: 14, mask: 'priceVol' },
  { name: 'ADX14L', trigger: 'thrX', kind: 'adx', lo: 25, hi: 25, look: 14, mask: 'price' },
];
const N_TA = TA_READINGS.length;
const R_ADX = TA_READINGS.findIndex((t) => t.kind === 'adx');

type PrimKind = 'MOM' | 'OPP' | 'FLOW' | 'DEPTH';
const MOM_WINDOWS = [15, 30, 60, 120, 300];

interface SeriesSpec {
  reading: string; bar: string; trigger: string;
  /** TA: reading index and bar index (-1 for primitives). */
  ta: number; b: number;
  prim?: PrimKind; w: number; level: number;
  /** Runs on recorded books only (A1). */
  rOnly: boolean;
}

const SERIES: SeriesSpec[] = [];
for (let r = 0; r < N_TA; r++) {
  for (let b = 0; b < BAR_LENS.length; b++) {
    const t = TA_READINGS[r];
    SERIES.push({ reading: t.name, bar: BAR_NAMES[b], trigger: t.trigger, ta: r, b, w: 0, level: 0, rOnly: !BAR_ON_H[b] });
  }
}
const prim = (kind: PrimKind, w: number, level: number) =>
  SERIES.push({ reading: kind, bar: '1s', trigger: kind === 'DEPTH' ? `on:${level}` : `on:w${w}:${level}`, ta: -1, b: -1, prim: kind, w, level, rOnly: kind === 'DEPTH' || w < 60 });
for (const k of ['MOM', 'OPP'] as const) {
  for (const l of [0.005, 0.01, 0.02, 0.04]) prim(k, 60, l);
  for (const w of [15, 30, 120, 300]) prim(k, w, 0.01);
}
for (const l of [0.05, 0.2, 0.4, 0.7]) prim('FLOW', 60, l);
for (const l of [0.1, 0.2, 0.4, 0.7]) prim('DEPTH', 0, l);
const N_SERIES = SERIES.length; // 68
const N_SERIES_H = SERIES.filter((s) => !s.rOnly).length; // 38
const FIRST_PRIM = N_TA * BAR_LENS.length;

const phaseBucketNames: string[] = [];
for (const p of PHASES) for (const b of BUCKETS) phaseBucketNames.push(`${p}:${b}`);

/** The design, for the report. Contexts are 'all' plus '<tour series>:<phase>:<bucket>' for every tour series seen
 *  (listed here for the two tours of the trial; any other tennis series follows the same pattern). */
export const SIGNAL_SPEC: { readings: string[]; bars: string[]; exits: string[]; contexts: string[] } = {
  readings: [...TA_READINGS.map((t) => t.name), 'MOM', 'OPP', 'FLOW', 'DEPTH'],
  bars: [...BAR_NAMES, '1s'],
  exits: [...EXITS],
  contexts: ['all', ...['KXATPMATCH', 'KXWTAMATCH'].flatMap((t) => phaseBucketNames.map((pb) => `${t}:${pb}`))],
};

/** Every trigger series in design order; rOnly ones are in the design only on recorded books (stratum R). */
export const SIGNAL_SERIES: ReadonlyArray<{ reading: string; bar: string; trigger: string; rOnly: boolean }> =
  SERIES.map((s) => ({ reading: s.reading, bar: s.bar, trigger: s.trigger, rOnly: s.rOnly }));

export type ExitKind = 'time' | 'tp' | 'sl' | 'trail' | 'cut' | 'ride' | 'breach';
const KIND_NAMES: ExitKind[] = ['time', 'tp', 'sl', 'trail', 'cut', 'ride', 'breach'];
const K_TIME = 0, K_TP = 1, K_SL = 2, K_TRAIL = 3, K_CUT = 4, K_RIDE = 5, K_BREACH = 6;

/** One simulated position (tests and diagnostics; only built when a trace callback is given). */
export interface EntryTrace {
  series: string; dir: 'follow' | 'fade'; exit: string; context: string; placebo: boolean;
  decision: number; fill: number; side: 'A' | 'B'; entryPx: number; count: number;
  /** Sample of the sale, or of the settlement-rule decision for ride / breach. */
  exitIdx: number;
  /** Sale price, or the settlement payout per contract (1 / 0) for ride / breach. */
  exitPx: number;
  kind: ExitKind; net: number; gross: number; fees: number; stressNet: number;
}

export interface SignalStudyOpts {
  orderUsd?: number;
  latencySec?: number;
  seed?: number;
  /** Diagnostics: called for every simulated position (real and placebo). */
  trace?: (t: EntryTrace) => void;
}

/** Run counters (not part of the inference). */
export interface SignalDiagnostics {
  matches: number;
  /** H matches skipped for having no tape on either market (A5). */
  noTape: number;
  triggers: number;
  /** Real entries (one per locked entry, both directions and all exits share it). */
  entries: number;
  placeboEntries: number;
  /** Real entries whose decision followed 60 s with no taker contract on either market (A7 flag). */
  zeroVolEntries: number;
  /** Real TA triggers dropped by the 3-minute jump mask. */
  jumpMasked: number;
  /** Real fade positions refused by the 10c / 90c fade band. */
  fadeBand: number;
}

class Cell {
  readonly acc = new ClusterAcc();
  readonly stress = new ClusterAcc();
  readonly plac = new ClusterAcc();
  breaches = 0;
  gross = 0;
  fees = 0;
  readonly pair: PairDiff = { clusters: 0, sum: 0, sumSq: 0 };
  pDay = '';
  pCell = 0;
  pPlac = 0;
  pAny = false;
  pairTo(day: string): void {
    if (day === this.pDay) return;
    this.pairFlush();
    this.pDay = day;
  }
  pairFlush(): void {
    if (this.pAny) { const d = this.pCell - this.pPlac; this.pair.clusters++; this.pair.sum += d; this.pair.sumSq += d * d; }
    this.pCell = 0; this.pPlac = 0; this.pAny = false;
  }
}

function mulberry32(a: number): () => number {
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function hash32(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
const logit = (p: number) => { const q = p < 0.01 ? 0.01 : p > 0.99 ? 0.99 : p; return Math.log(q / (1 - q)); };
const tick = (x: number) => Math.round(x * 1e4) / 1e4;
const nz = (x: number) => (x === x ? x : 0);
const copyStats = (s: ClusterStats): ClusterStats => ({ ...s });

// buffer slots
const F_PA = 0, F_MIDA = 1, F_MIDB = 2, F_CYA = 3, F_CNA = 4, F_CYB = 5, F_CNB = 6, F_CVOL = 7, F_CHG = 8, F_CARRY = 18; // F_CHG: 10 slots
const I_NEXTEV = 0, I_NBA = 1, I_NBB = 2, I_LVA = 3, I_LVB = 4, I_NVA = 5, I_NVB = 6, I_JUMP = 7;
const U_DEC = 0;

export class SignalStudy {
  private readonly orderUsd: number;
  private readonly lat: number;
  private readonly seed: number;
  private readonly trace?: (t: EntryTrace) => void;
  private readonly cellMap = new Map<number, Cell>();
  private readonly tours = new Map<string, number>();
  private sawR = false;
  private readonly diag: SignalDiagnostics = { matches: 0, noTape: 0, triggers: 0, entries: 0, placeboEntries: 0, zeroVolEntries: 0, jumpMasked: 0, fadeBand: 0 };

  // ---- per-match state (buffers reused across matches) ----
  private g!: MatchGrid;
  private n = 0;
  private closeIdx = 0;
  private day = '';
  private tour = 0;
  private placeboOn = false;
  private readonly f64: Float64Array[] = [];
  private readonly i32: Int32Array[] = [];
  private readonly u8: Uint8Array[] = [];
  private trig = new Int32Array(4096);
  private nTrig = 0;
  /** Each series' triggers are trig[seriesStart[s] .. seriesEnd[s]), sorted by decision. */
  private readonly seriesStart = new Int32Array(N_SERIES);
  private readonly seriesEnd = new Int32Array(N_SERIES);
  private plc = new Int32Array(4096);
  // exit scratch
  private xAt = 0;
  private xPx = 0;
  private xKind = 0;

  constructor(opts: SignalStudyOpts = {}) {
    this.orderUsd = opts.orderUsd ?? 10;
    this.lat = Math.max(0, Math.ceil(opts.latencySec ?? 1));
    this.seed = (opts.seed ?? 20261105) >>> 0;
    this.trace = opts.trace;
  }

  /** How many cells exist in the design (BH m), including cells that never fired: series x 2 directions x
   *  (1 + 25 x tour series seen) contexts x 5 exits. */
  designSize(): number {
    return (this.sawR ? N_SERIES : N_SERIES_H) * 2 * (1 + N_PB * this.tours.size) * N_EXIT;
  }

  diagnostics(): SignalDiagnostics { return { ...this.diag }; }

  private bufF(slot: number, n: number): Float64Array {
    let a = this.f64[slot];
    if (!a || a.length < n) { a = new Float64Array(Math.ceil(n * 1.25) + 16); this.f64[slot] = a; }
    return a;
  }
  private bufI(slot: number, n: number): Int32Array {
    let a = this.i32[slot];
    if (!a || a.length < n) { a = new Int32Array(Math.ceil(n * 1.25) + 16); this.i32[slot] = a; }
    return a;
  }
  private bufU(slot: number, n: number): Uint8Array {
    let a = this.u8[slot];
    if (!a || a.length < n) { a = new Uint8Array(Math.ceil(n * 1.25) + 16); this.u8[slot] = a; }
    return a;
  }
  private push(v: number): void {
    if (this.nTrig >= this.trig.length) { const t = new Int32Array(this.trig.length * 2); t.set(this.trig); this.trig = t; }
    this.trig[this.nTrig++] = v;
  }

  /** Evaluate one completed match. Matches arrive in non-decreasing g.day order within a run. */
  addMatch(g: MatchGrid): void {
    const n = g.n;
    if (!(n > 1)) return;
    this.g = g;
    this.n = n;
    this.closeIdx = Math.min(Math.max(0, g.closeIdx), n - 1);
    this.day = g.day;
    this.prepareQuotes();
    if (g.stratum === 'H' && this.f64[F_CVOL][n] <= 0) { this.diag.noTape++; return; }
    if (g.stratum === 'R') this.sawR = true;
    let tour = this.tours.get(g.series);
    if (tour === undefined) {
      if (this.tours.size >= MAX_TOURS) throw new Error(`tennisTaSignals: more than ${MAX_TOURS} tour series`);
      tour = this.tours.size;
      this.tours.set(g.series, tour);
    }
    this.tour = tour;
    this.diag.matches++;
    this.nTrig = 0;
    const onR = g.stratum === 'R';
    this.buildBarSeries(onR);
    this.buildPrimitives(onR);
    this.diag.triggers += this.nTrig;
    this.placeboOn = this.closeIdx + 1 >= 2 * PLACEBO_MIN;
    const rng = mulberry32((hash32(g.event) ^ this.seed) >>> 0);
    for (let s = 0; s < N_SERIES; s++) {
      if (SERIES[s].rOnly && !onR) continue;
      const off = this.placeboOn ? PLACEBO_MIN + Math.floor(rng() * (this.closeIdx + 1 - 2 * PLACEBO_MIN + 1)) : 0;
      const t0 = this.seriesStart[s], t1 = this.seriesEnd[s];
      if (t1 === t0) continue;
      this.pass(s, this.trig, t0, t1, false);
      if (this.placeboOn) this.pass(s, this.plc, 0, this.rotate(t0, t1, off), true);
    }
  }

  /** pA, mids, settlement-rule events, next-bid lookups, valid-mid lookups, cumulative tape, jump marks. */
  private prepareQuotes(): void {
    const g = this.g, n = this.n, C = this.closeIdx;
    const pA = this.bufF(F_PA, n), mA = this.bufF(F_MIDA, n), mB = this.bufF(F_MIDB, n);
    const dec = this.bufU(U_DEC, n);
    for (let i = 0; i < n; i++) {
      const ba = g.bidA[i], aa = g.askA[i], bb = g.bidB[i], ab = g.askB[i];
      const a = ba > 0 && aa > 0 && aa >= ba ? (ba + aa) / 2 : NaN;
      const b = bb > 0 && ab > 0 && ab >= bb ? (bb + ab) / 2 : NaN;
      mA[i] = a; mB[i] = b;
      const p = a === a ? (b === b ? (a + 1 - b) / 2 : a) : b === b ? 1 - b : NaN;
      pA[i] = p;
      dec[i] = p >= DECIDED_HI - EPS || p <= DECIDED_LO + EPS ? 1 : 0;
    }
    // Settlement-rule events: decided turns on, progress reaches 0.70, or closeIdx.
    const nextEv = this.bufI(I_NEXTEV, n + 1);
    const prog = g.progress;
    nextEv[n] = n;
    for (let i = n - 1; i >= 0; i--) {
      let ev = i === C;
      if (!ev && i > 0 && i < C) ev = (dec[i] === 1 && dec[i - 1] === 0) || (prog[i] >= LATE && !(prog[i - 1] >= LATE));
      nextEv[i] = ev ? i : i > C ? n : nextEv[i + 1];
    }
    // Next sample at or after i (up to closeIdx) with a bid on each side; -1 when none.
    const nbA = this.bufI(I_NBA, n + 1), nbB = this.bufI(I_NBB, n + 1);
    nbA[n] = -1; nbB[n] = -1;
    for (let i = n - 1; i >= 0; i--) {
      if (i > C) { nbA[i] = -1; nbB[i] = -1; continue; }
      nbA[i] = g.bidA[i] > 0 ? i : nbA[i + 1];
      nbB[i] = g.bidB[i] > 0 ? i : nbB[i + 1];
    }
    // Latest valid mid at or before i, first valid mid at or after i (n when none).
    const lvA = this.bufI(I_LVA, n), lvB = this.bufI(I_LVB, n);
    const nvA = this.bufI(I_NVA, n + 1), nvB = this.bufI(I_NVB, n + 1);
    let la = -1, lb = -1;
    for (let i = 0; i < n; i++) { if (mA[i] === mA[i]) la = i; if (mB[i] === mB[i]) lb = i; lvA[i] = la; lvB[i] = lb; }
    nvA[n] = n; nvB[n] = n;
    for (let i = n - 1; i >= 0; i--) { nvA[i] = mA[i] === mA[i] ? i : nvA[i + 1]; nvB[i] = mB[i] === mB[i] ? i : nvB[i + 1]; }
    // Cumulative tape (index i + 1 holds samples 0..i).
    const cya = this.bufF(F_CYA, n + 1), cna = this.bufF(F_CNA, n + 1);
    const cyb = this.bufF(F_CYB, n + 1), cnb = this.bufF(F_CNB, n + 1), cv = this.bufF(F_CVOL, n + 1);
    cya[0] = 0; cna[0] = 0; cyb[0] = 0; cnb[0] = 0; cv[0] = 0;
    for (let i = 0; i < n; i++) {
      const ya = nz(g.yesVolA[i]), na = nz(g.noVolA[i]), yb = nz(g.yesVolB[i]), nb = nz(g.noVolB[i]);
      cya[i + 1] = cya[i] + ya; cna[i + 1] = cna[i] + na; cyb[i + 1] = cyb[i] + yb; cnb[i + 1] = cnb[i] + nb;
      cv[i + 1] = cv[i] + ya + na + yb + nb;
    }
    // A7 jumps: latest sample at or before i where the carried pA moved >= 10c over 60 s (-1e9 when none).
    const lj = this.bufI(I_JUMP, n);
    let carried = NaN, last = -1e9;
    const hist = this.bufF(F_CARRY, n); // carried pA
    for (let i = 0; i < n; i++) {
      if (pA[i] === pA[i]) carried = pA[i];
      hist[i] = carried;
      if (i >= JUMP_LAG) { const d = carried - hist[i - JUMP_LAG]; if (d >= JUMP - EPS || d <= -JUMP + EPS) last = i; }
      lj[i] = last;
    }
  }

  /** Bars, TA-Lib readings and their triggers for the TA series of this stratum. */
  private buildBarSeries(onR: boolean): void {
    const g = this.g, n = this.n;
    const pA = this.f64[F_PA];
    for (let b = 0; b < BAR_LENS.length; b++) {
      for (let r = 0; r < N_TA; r++) { this.seriesStart[r * BAR_LENS.length + b] = 0; this.seriesEnd[r * BAR_LENS.length + b] = 0; }
      if (!BAR_ON_H[b] && !onR) continue;
      const L = BAR_LENS[b];
      const K = Math.floor(n / L);
      let last = NaN;
      let k0 = -1;
      const c: number[] = [], h: number[] = [], l: number[] = [], v: number[] = [], f: number[] = [];
      for (let k = 0; k < K; k++) {
        let hi = last, lo = last, vol = 0, fl = 0;
        const start = k * L, end = start + L;
        for (let i = start + ((MID_STEP - 1 - (start % MID_STEP)) % MID_STEP); i < end; i += MID_STEP) {
          const p = pA[i];
          if (p === p) { last = p; if (!(hi >= p)) hi = p; if (!(lo <= p)) lo = p; }
        }
        for (let i = start; i < end; i++) {
          const ya = nz(g.yesVolA[i]), na = nz(g.noVolA[i]), yb = nz(g.yesVolB[i]), nb = nz(g.noVolB[i]);
          vol += ya + na + yb + nb; fl += ya - na - (yb - nb);
        }
        if (k0 < 0) { if (last === last) k0 = k; else continue; }
        c.push(last); h.push(hi); l.push(lo); v.push(vol); f.push(fl);
      }
      const M = k0 < 0 ? 0 : K - k0;
      const res: number[][] = [];
      const mv = new Int32Array(M), vl = new Int32Array(M), fl = new Int32Array(M);
      let plusDi: number[] = [], minusDi: number[] = [];
      if (M >= 3) {
        let lm = -1e9, lv = -1e9, lf = -1e9;
        for (let j = 0; j < M; j++) {
          if (h[j] - l[j] > 1e-12) lm = j;
          if (v[j] > 0) lv = j;
          if (f[j] !== 0) lf = j;
          mv[j] = lm; vl[j] = lv; fl[j] = lf;
        }
        const lc = c.map(logit), lh = h.map(logit), ll = l.map(logit);
        const obv = new Array<number>(M);
        let cum = 0;
        for (let j = 0; j < M; j++) { cum += f[j]; obv[j] = cum; }
        const lhlc = { high: lh, low: ll, close: lc };
        const out = (o: Record<string, number[]>, k: string) => o[k] ?? [];
        const bb = tl('BBANDS', { inReal: lc }, { optInTimePeriod: 20, optInNbDevUp: 2, optInNbDevDn: 2, optInMAType: 0 });
        const up = out(bb, 'outRealUpperBand'), dn = out(bb, 'outRealLowerBand');
        const pctB = new Array<number>(M);
        for (let j = 0; j < M; j++) { const w = up[j] - dn[j]; pctB[j] = w > 1e-12 ? (lc[j] - dn[j]) / w : NaN; }
        res[0] = out(tl('RSI', { inReal: lc }, { optInTimePeriod: 14 }), 'outReal');
        res[1] = out(tl('STOCH', lhlc, { optInFastK_Period: 14, optInSlowK_Period: 3, optInSlowK_MAType: 0, optInSlowD_Period: 3, optInSlowD_MAType: 0 }), 'outSlowK');
        res[2] = out(tl('WILLR', lhlc, { optInTimePeriod: 14 }), 'outReal');
        res[3] = out(tl('CCI', lhlc, { optInTimePeriod: 14 }), 'outReal');
        res[4] = pctB;
        res[5] = out(tl('MACD', { inReal: lc }, { optInFastPeriod: 12, optInSlowPeriod: 26, optInSignalPeriod: 9 }), 'outMACDHist');
        res[6] = out(tl('LINEARREG_SLOPE', { inReal: lc }, { optInTimePeriod: 14 }), 'outReal');
        res[7] = out(tl('MOM', { inReal: lc }, { optInTimePeriod: 10 }), 'outReal');
        res[8] = out(tl('LINEARREG_SLOPE', { inReal: obv }, { optInTimePeriod: 14 }), 'outReal');
        res[9] = out(tl('MFI', { high: h, low: l, close: c, volume: v }, { optInTimePeriod: 14 }), 'outReal');
        res[R_ADX] = out(tl('ADX', lhlc, { optInTimePeriod: 14 }), 'outReal');
        plusDi = out(tl('PLUS_DI', lhlc, { optInTimePeriod: 14 }), 'outReal');
        minusDi = out(tl('MINUS_DI', lhlc, { optInTimePeriod: 14 }), 'outReal');
      }
      for (let r = 0; r < N_TA; r++) {
        const s = r * BAR_LENS.length + b;
        const start = this.nTrig;
        const vals = res[r];
        if (vals && M >= 3) {
          const t = TA_READINGS[r], look = t.look;
          const mk = t.mask === 'flow' ? fl : mv;
          for (let j = 1; j < M; j++) {
            const x = vals[j], u = vals[j - 1];
            if (!(x === x && u === u)) continue;
            if (mk[j] < j - look + 1 || mk[j - 1] < j - look) continue;
            if (t.mask === 'priceVol' && (vl[j] < j - look + 1 || vl[j - 1] < j - look)) continue;
            let side = -1;
            if (t.kind === 'ext') {
              if (u < t.lo && x >= t.lo) side = 0;
              else if (u > t.hi && x <= t.hi) side = 1;
            } else if (t.kind === 'zero') {
              if (u <= 0 && x > 0) side = 0;
              else if (u >= 0 && x < 0) side = 1;
            } else if (u < t.lo && x >= t.lo) {
              side = plusDi[j] >= minusDi[j] || !(minusDi[j] === minusDi[j]) ? 0 : 1;
            }
            if (side < 0) continue;
            const d = (k0 + j + 1) * L;
            if (d < n) this.push(d * 2 + side);
          }
        }
        this.seriesStart[s] = start;
        this.seriesEnd[s] = this.nTrig;
      }
    }
  }

  /** Confluence primitives on the 1 s grid: triggers when the signal toward a player turns on. */
  private buildPrimitives(onR: boolean): void {
    const g = this.g, n = this.n;
    const mA = this.f64[F_MIDA], mB = this.f64[F_MIDB];
    const lvA = this.i32[I_LVA], lvB = this.i32[I_LVB];
    const nvA = this.i32[I_NVA], nvB = this.i32[I_NVB];
    // Mid change of each market over each window in use (NaN when production's midChange is undefined).
    for (let wi = 0; wi < MOM_WINDOWS.length; wi++) {
      const w = MOM_WINDOWS[wi], half = w / 2;
      if (w < 60 && !onR) continue;
      const ca = this.bufF(F_CHG + 2 * wi, n), cb = this.bufF(F_CHG + 2 * wi + 1, n);
      for (let i = 0; i < n; i++) {
        const lo = i - w < 0 ? 0 : i - w;
        let last = lvA[i], past = nvA[lo];
        ca[i] = last >= 0 && past <= last && last - past >= half ? mA[last] - mA[past] : NaN;
        last = lvB[i]; past = nvB[lo];
        cb[i] = last >= 0 && past <= last && last - past >= half ? mB[last] - mB[past] : NaN;
      }
    }
    const cya = this.f64[F_CYA], cna = this.f64[F_CNA];
    const cyb = this.f64[F_CYB], cnb = this.f64[F_CNB];
    for (let s = FIRST_PRIM; s < N_SERIES; s++) {
      const sp = SERIES[s];
      this.seriesStart[s] = this.nTrig;
      this.seriesEnd[s] = this.nTrig;
      if (sp.rOnly && !onR) continue;
      const lev = sp.level;
      let onA = false, onB = false;
      if (sp.prim === 'MOM' || sp.prim === 'OPP') {
        const wi = MOM_WINDOWS.indexOf(sp.w);
        const ca = this.f64[F_CHG + 2 * wi], cb = this.f64[F_CHG + 2 * wi + 1];
        const mom = sp.prim === 'MOM';
        for (let i = 0; i < n; i++) {
          const a = mom ? ca[i] >= lev - EPS : cb[i] <= -lev + EPS;
          const b = mom ? cb[i] >= lev - EPS : ca[i] <= -lev + EPS;
          if (i > 0) { if (a && !onA) this.push(i * 2); if (b && !onB) this.push(i * 2 + 1); }
          onA = a; onB = b;
        }
      } else if (sp.prim === 'FLOW') {
        const w = sp.w;
        for (let i = 0; i < n; i++) {
          const lo = i - w + 1 < 0 ? 0 : i - w + 1;
          const ya = cya[i + 1] - cya[lo], na = cna[i + 1] - cna[lo], yb = cyb[i + 1] - cyb[lo], nb = cnb[i + 1] - cnb[lo];
          const a = ya + na > 0 && (ya - na) / (ya + na) >= lev - EPS;
          const b = yb + nb > 0 && (yb - nb) / (yb + nb) >= lev - EPS;
          if (i > 0) { if (a && !onA) this.push(i * 2); if (b && !onB) this.push(i * 2 + 1); }
          onA = a; onB = b;
        }
      } else {
        const ia = g.imbA, ib = g.imbB;
        for (let i = 0; i < n; i++) {
          const a = ia[i] >= lev - EPS, b = ib[i] >= lev - EPS;
          if (i > 0) { if (a && !onA) this.push(i * 2); if (b && !onB) this.push(i * 2 + 1); }
          onA = a; onB = b;
        }
      }
      this.seriesEnd[s] = this.nTrig;
    }
  }

  /** The series' triggers with decisions <= closeIdx, shifted circularly by off inside [0, closeIdx]; returns the count. */
  private rotate(t0: number, t1: number, off: number): number {
    const N = this.closeIdx + 1;
    if (this.plc.length < t1 - t0) this.plc = new Int32Array(Math.max(t1 - t0, this.plc.length * 2));
    let end = t1;
    while (end > t0 && this.trig[end - 1] >> 1 >= N) end--;
    // Triggers whose shifted decision wraps (d + off >= N) come first, then the rest; both runs stay sorted.
    let split = t0;
    while (split < end && (this.trig[split] >> 1) + off < N) split++;
    let k = 0;
    for (let t = split; t < end; t++) { const v = this.trig[t]; this.plc[k++] = ((v >> 1) + off - N) * 2 + (v & 1); }
    for (let t = t0; t < split; t++) { const v = this.trig[t]; this.plc[k++] = ((v >> 1) + off) * 2 + (v & 1); }
    return k;
  }

  /** One entry-locked pass of series s over a sorted trigger list: both directions and all exits share each entry. */
  private pass(s: number, arr: Int32Array, from: number, to: number, placebo: boolean): void {
    const g = this.g;
    const lastFill = this.closeIdx - 1;
    const prog = g.progress;
    const live = g.liveIdx;
    const sp = SERIES[s];
    const isTa = sp.ta >= 0;
    const lj = this.i32[I_JUMP];
    const cv = this.f64[F_CVOL];
    const tourBase = 1 + this.tour * N_PB;
    let lock = -1;
    for (let t = from; t < to; t++) {
      const v = arr[t];
      const d = v >> 1;
      if (d <= lock) continue;
      const e = d + this.lat;
      if (e > lastFill) break;
      if (isTa && lj[d] >= d - JUMP_MASK) { if (!placebo) this.diag.jumpMasked++; continue; }
      const ts = v & 1;
      // Which directions can take this entry.
      let took = false;
      let lockTo = e;
      for (let dir = 0; dir < 2; dir++) {
        const side = ts ^ dir;
        const ask = side ? g.askB[e] : g.askA[e];
        const bid = side ? g.bidB[e] : g.bidA[e];
        if (!(ask > 0 && ask < 1 && bid > 0) || ask - bid > MAX_SPREAD + EPS) continue;
        if (dir === 1 && (ask < FADE_MIN - EPS || ask > FADE_MAX + EPS)) { if (!placebo) this.diag.fadeBand++; continue; }
        if (!took) {
          took = true;
          if (placebo) this.diag.placeboEntries++;
          else { this.diag.entries++; if (cv[d + 1] - cv[d + 1 - 60 < 0 ? 0 : d + 1 - 60] <= 0) this.diag.zeroVolEntries++; }
        }
        const count = Math.max(1, Math.floor(this.orderUsd / ask + EPS));
        const feeIn = orderFee(count, ask, true, FEES);
        const cost = count * ask + feeIn;
        // Context: tour series, phase at the decision, bucket of the ask paid.
        const phase = live < 0 || d < live ? 0 : d < live + FIRST_PHASE_SEC ? 1 : !(prog[d] >= 1 / 3) ? 2 : prog[d] < 2 / 3 ? 3 : 4;
        const bucket = ask >= 0.08 - EPS && ask < 0.15 - EPS ? 0 : ask >= 0.15 - EPS && ask < 0.25 - EPS ? 1
          : ask >= 0.75 - EPS && ask < 0.85 - EPS ? 2 : ask >= 0.85 - EPS && ask <= 0.92 + EPS ? 3 : 4;
        const ctx = tourBase + phase * BUCKETS.length + bucket;
        const base = (s * 2 + dir) * CTX_STRIDE;
        for (let x = 0; x < N_EXIT; x++) {
          this.exit(e, side, x, ask, count, cost);
          const at = this.xAt, px = this.xPx, kind = this.xKind;
          let gross: number, fees: number, net: number, snet: number;
          if (kind >= K_RIDE) {
            gross = count * px - count * ask; fees = feeIn; net = gross - fees; snet = net;
            lockTo = Infinity;
          } else {
            const feeOut = orderFee(count, px, true, FEES);
            gross = count * (px - ask); fees = feeIn + feeOut; net = gross - fees;
            const ps = tick(px - 0.01 >= 0.01 ? px - 0.01 : 0.01);
            snet = count * (ps - ask) - feeIn - orderFee(count, ps, true, FEES);
            if (at > lockTo) lockTo = at;
          }
          const breach = kind === K_BREACH;
          this.record((base + ctx) * N_EXIT + x, net, snet, gross, fees, breach, placebo);
          this.record(base * N_EXIT + x, net, snet, gross, fees, breach, placebo);
          if (this.trace) {
            this.trace({
              series: `${sp.reading}|${sp.bar}|${sp.trigger}`, dir: dir ? 'fade' : 'follow', exit: EXITS[x], context: this.ctxName(ctx), placebo,
              decision: d, fill: e, side: side ? 'B' : 'A', entryPx: ask, count, exitIdx: at, exitPx: px, kind: KIND_NAMES[kind],
              net, gross, fees, stressNet: snet,
            });
          }
        }
      }
      if (took) lock = lockTo;
    }
  }

  private ctxName(ctx: number): string {
    if (ctx === 0) return 'all';
    const k = ctx - 1, tour = Math.floor(k / N_PB), pb = k % N_PB;
    let name = '';
    for (const [t, i] of this.tours) if (i === tour) { name = t; break; }
    return `${name}:${phaseBucketNames[pb]}`;
  }

  private record(key: number, net: number, snet: number, gross: number, fees: number, breach: boolean, placebo: boolean): void {
    let c = this.cellMap.get(key);
    if (!c) { c = new Cell(); this.cellMap.set(key, c); }
    if (placebo) {
      c.plac.add(net, this.day);
      c.pairTo(this.day); c.pPlac += net; c.pAny = true;
      return;
    }
    c.acc.add(net, this.day);
    c.stress.add(snet, this.day);
    c.gross += gross; c.fees += fees;
    if (breach) c.breaches++;
    if (this.placeboOn) { c.pairTo(this.day); c.pCell += net; c.pAny = true; }
  }

  /** Exit of a position filled at e on side (0 = A, 1 = B): sets xAt, xPx, xKind. cost = count x ask + entry fee. */
  private exit(e: number, side: number, x: number, ask: number, count: number, cost: number): void {
    const g = this.g;
    const bid = side ? g.bidB : g.bidA;
    const nb = side ? this.i32[I_NBB] : this.i32[I_NBA];
    const c = this.i32[I_NEXTEV][e + 1]; // <= closeIdx since e < closeIdx
    let at = -1, px = 0, kind = K_TIME;
    const stop = e + TIME_STOP[x];
    if (x === 2 || x === 3) {
      const tp = ask * (x === 2 ? 1.3 : 1.5) - EPS, sl = ask * (x === 2 ? 0.7 : 0.75) + EPS;
      const lim = stop < c - 1 ? stop : c - 1;
      for (let j = e + 1; j <= lim; j++) {
        const b = bid[j];
        if (b >= tp) { at = j; px = b; kind = K_TP; break; }
        if (b <= sl) { at = j; px = b; kind = K_SL; break; }
      }
    } else if (x === 4) {
      const arm = ask + 0.02 - EPS;
      let armed = false, peak = 0;
      const lim = stop < c - 1 ? stop : c - 1;
      for (let j = e + 1; j <= lim; j++) {
        const b = bid[j];
        if (!(b > 0)) continue;
        if (!armed) { if (b >= arm) { armed = true; peak = b; } }
        else if (b > peak) peak = b;
        else if (b <= peak - 0.03 + EPS) { at = j; px = b; kind = K_TRAIL; break; }
      }
    }
    if (at < 0 && stop < c) {
      const j = nb[stop];
      if (j >= 0 && j < c) { at = j; px = bid[j]; kind = K_TIME; }
    }
    if (at < 0) {
      // Settlement rule at sample c.
      const won = side === 0 ? g.resultA === 1 : g.resultA === 0;
      const b = bid[c];
      if (b > 0) {
        if (count * b - orderFee(count, b, true, FEES) - cost > EPS) { at = c; px = won ? 1 : 0; kind = K_RIDE; }
        else { at = c; px = b; kind = K_CUT; }
      } else {
        const j = nb[c];
        if (j >= 0) { at = j; px = bid[j]; kind = K_CUT; }
        else { at = c; px = won ? 1 : 0; kind = K_BREACH; }
      }
    }
    this.xAt = at; this.xPx = px; this.xKind = kind;
  }

  /** Flush open day clusters and return every cell with entries (real or placebo). Call once after the last match. */
  cells(): CellResult[] {
    const out: CellResult[] = [];
    const keys = [...this.cellMap.keys()].sort((a, b) => a - b);
    for (const key of keys) {
      const c = this.cellMap.get(key)!;
      c.acc.flush(); c.stress.flush(); c.plac.flush(); c.pairFlush();
      const x = key % N_EXIT, rest = (key - x) / N_EXIT;
      const ctx = rest % CTX_STRIDE, sd = (rest - ctx) / CTX_STRIDE;
      const dir = sd % 2, s = (sd - dir) / 2;
      const sp = SERIES[s];
      const group = `B|${sp.reading}|${sp.bar}|${sp.trigger}|${DIRS[dir]}`;
      const folds: Record<string, ClusterStats> = {};
      for (const [k, v] of Object.entries(c.acc.folds)) folds[k] = copyStats(v);
      out.push({
        id: `${group}|${this.ctxName(ctx)}|${EXITS[x]}`,
        family: 'B',
        group,
        total: copyStats(c.acc.total),
        folds,
        stress: copyStats(c.stress.total),
        placebo: c.plac.total.n ? copyStats(c.plac.total) : emptyStats(),
        pairDiff: { ...c.pair },
        breaches: c.breaches,
        gross: c.gross,
        fees: c.fees,
      });
    }
    return out;
  }
}
