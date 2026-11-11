// Tennis TA rulebook trial, family B: TA-Lib readings of the match price path and the production confluence signals as
// a sterile, entry-locked event study (pre-registration /mnt/project-files/tennis-ta/preregistration.md, section 5
// "Family B" as changed by Amendment 1: A1 staged design, A5 controls, A6 the bot's real exit path, A7 cells). Every
// trigger series is evaluated per match on the 1-second MatchGrid; entries are taker buys of YES on one player, exits are
// the fixed exit set under production's end cut (TENNIS_END_LOSER_CUT), and every cell gets a circular-shift placebo, a
// stress figure and per-unit / per-day accumulators (research/tennisTaTypes.ts FamilyBCell). Realized net $ after fees is
// the only score.
//
// One study = one stratum: H (Kalshi history) and R (recordings) are never mixed (addMatch throws). The stratum is given up
// front (opts.stratum; the sweep must pass it) or taken from the first grid; exportCells throws when it is neither, since the
// design (designSize) depends on it and an empty slice cannot tell. Every grid carries its tournament-week unit (g.unit,
// set by the sweep; addMatch throws without it). Matches may arrive in any order: per-unit and per-day rows are keyed by
// unit and day, so nothing depends on it (a grid whose day is before an earlier grid's is only counted, diagnostics
// outOfOrderGrids). The study refuses to run without the real TA-Lib engine (bot/ta/talib.ts taEngine() must be 'talib':
// the constructor throws), and a TA-Lib call that returns nothing throws: it never goes quiet.
//
// Price and bars
//   pA[i] = MatchTracker.probability: (midA + 1 - midB) / 2 when both books have bid and ask (ask >= bid), else the one
//   that exists (1 - midB for B), NaN when neither. Bars (A7: logit(mid) bars built from 5 s mids, as the bot would):
//   bar k covers samples [kL, (k+1)L) and reads pA only at the 5 s marks (samples 4, 9, 14, ...; the bar's last sample
//   is one); close = the last valid mark of the bar; high / low over the bar's valid marks and the previous bar's close
//   (its open); volume = all taker contracts of both markets in the bar; signed flow toward A = (yesVolA - noVolA) -
//   (yesVolB - noVolB). A bar is acted on at the sample right after its end (decision d = (k+1)L), the fill one latency
//   later. pA is clipped to [0.01, 0.99] before every logit.
//   Gaps (section 5: "gaps masked"): a bar with no valid mark is a gap bar. Gaps are never carried: the bar series is cut
//   into segments at gap bars and TA-Lib runs on each segment alone, so every reading warms up again after a gap, and no
//   trigger's window holds a gap or a value from before it.
//   Bar lengths: 1 m and 5 m on H; 10 s and 30 s too on R (A1: one-level minute books make shorter bars near copies). The
//   `bars` option narrows them (the sweep passes 1m, 5m on H); asking for 10 s / 30 s on H throws.
//
// Readings (TA-Lib through bot/ta/talib.ts tl(), once per segment per bar length, on logit bars)
//   RSI14, STOCH14_3_3 (slowK), WILLR14, CCI14, BBP20_2 (%B of BBANDS 20/2): trigger exitExt (BBP: reenter) = leaving an
//     extreme: crossing up through the low level -> long A, down through the high level -> long B (RSI 30/70, STOCH
//     20/80, WILLR -80/-20, CCI -100/+100, %B 0/1).
//   MFI14: same trigger (20/80), from bar H/L/C of pA itself in cents (x100), not logit: MFI weighs typical price x volume,
//     which turns meaningless when the logit typical price is negative, and TA-Lib returns 0 whenever the window's money
//     flow sums under 1.0, which prices on the 0..1 scale hit.
//   MACDH12_26_9L (MACD histogram), SLOPE14L (LINEARREG_SLOPE 14), MOM10L (MOM 10: ROC = x / x_prev - 1 is meaningless
//     on a logit that changes sign), OBVS14 (LINEARREG_SLOPE 14 of OBV = cumulative signed taker flow toward A; the tape
//     gives the true sign, so TA-Lib's price-signed OBV is not used): trigger zeroX = the sign of the reading flips (to +
//     -> long A). Readings within 1e-12 of 0 (OBVS: 1e-9 x |OBV|) are 0 (TA-Lib's float noise on a flat window), and a
//     trigger needs the last NONZERO reading of the same valid run to have the other sign: 0 -> + after + is no cross.
//   ADX14L: section 5 used ADX >= 25 as a trend/chop context; A1 defines a cell as series x phase x price bucket (x
//     TA-Lib column) and A7 lists ADX among the TA-Lib columns, so ADX is a column here: trigger thrX = ADX crosses up
//     through 25, long the side PLUS_DI vs MINUS_DI favours (A on a tie). NATR (A7) has no direction and KAMA efficiency
//     ratio / ATR (section 5 conditions) have no place in the A1 cell, so they are not computed.
//   The two extremes are ONE trigger: market A is just the first ticker in sort order, and RSI(1 - p) = 100 - RSI(p), so
//   "RSI leaves 30 on A" and "RSI leaves 70 on B" are the same hypothesis seen from the two markets (one canonical side
//   per match). The price bucket still separates the cheap side from the dear one.
//   Masks: (1) flat windows (TA-Lib returns a degenerate value there: RSI / WILLR / STOCH / MFI 0, slope +-1e-17): a
//   crossing needs both of its bars (k-1 and k) to read a window that moved. Close-based readings (RSI 15 closes, BBP 20,
//   SLOPE 14, MOM 11, MACDH 10) need a close change inside the closes they read (last change >= k - closes + 2, a range
//   inside a bar does not count); WILLR / CCI / ADX a bar range inside their 14 bars; STOCH a range inside each of the
//   three 14-bar fastK windows its slowK averages (so bars k-3..k for a crossing); MFI a bar with volume whose typical
//   price moved inside its 14 bars; OBVS a nonzero flow inside the 13 flows its 14 OBV values hold. (2) warm-up: nothing
//   before TA-Lib's begIndex in each segment (its NaN). (3) A7 jump mask: no TA entry whose decision falls within 3
//   minutes after a 1-minute pA move of 10c or more (any 60 s window of the carried pA); applied at entry time, so the
//   placebo is masked the same way.
//
// Confluence primitives (bot/tennis/tennisStrategy.ts tennisConfluence semantics, on the 1 s grid, both players)
//   MOM: mid of player X rose >= level over the window (production midChange: first valid mid at or after now - w vs
//   the latest valid mid, span >= w/2); OPP: the other market's mid fell >= level; FLOW: (YES - NO) / total taker
//   contracts on X's market over the window >= level; DEPTH: imbX >= level (R only; it never fires on H, A5).
//   Trigger = the signal toward X turns on (off at i-1, on at i; nothing at i = 0). Gaps: MOM / OPP toward X are read only
//   where the market they measure has a valid mid at i (DEPTH: where X's imbalance exists); elsewhere the signal is
//   unknown, and a turn-on needs a known "off" at i-1, so nothing fires at or right after a gap.
//   Variants: MOM and OPP at {0.005, 0.01, 0.02, 0.04} with window 60 s plus windows {120, 300} s at the default 0.01
//   (and {15, 30} s on R only, A1); FLOW at {0.05, 0.2, 0.4, 0.7} with window 60 s; DEPTH at {0.1, 0.2, 0.4, 0.7} (R).
//
// Entries (A1: entry-locked; each entry set computed once, the fixed exits reuse it)
//   A series' triggers are walked in time order. A trigger is an entry when its decision comes after the lock, before
//   production's end-entry block (TENNIS_END_ENTRY_MARGIN: no entry once the latched progress of the match, see End
//   cut, reaches 1 - settleFrac - margin, 0.65 with the defaults; a later position would start under water in the last
//   share), and at least one direction can take it: follow buys the side the trigger names, fade the other side; a
//   direction takes it when that side has a bid and an ask at fill = decision + latencySec (rounded up to whole samples),
//   the spread is <= 5c, the fill is before closeIdx, and, for fade only, the ask is within [0.10, 0.90] (A7: no fades
//   above 90c or below 10c; applied to every family B series). Taker buy of YES at the ask, count = max(1,
//   floor(orderUsd / ask)), capped at 100 on H (the synthesized book's one level is 100 contracts; R entries over 100 are counted, diagnostics
//   rOver100, since the grid carries no depth).
//   Both directions and all five exits are evaluated on that one entry; the lock then runs until the last of those
//   positions has closed (a position held to settlement locks the series for the rest of the match). So each cell holds
//   at most one position at a time, follow and fade are the same entry set (the reversed-direction adversary), and every
//   entry goes to its context cell AND to the 'all' cell. A later trigger may re-enter.
// Exits: an exit is DECIDED at a sample j >= fill + 1 on the quotes of j and SOLD one latency later, at the bid of the first
//   sample at or after j + latency that has one (the entry waits the same latency); never at the sample that decided it.
//   ts2m / ts10m time stops; tp30sl30 and tp50sl25 brackets on the bid, relative to the entry price, with a 15 min stop;
//   trail3t: armed once the bid >= entry + 2c, exit when the bid <= peak - 3 ticks, 15 min stop. Every sale is a taker
//   sell at the bid; fees are bot/fees.ts orderFee per order (taker, multipliers 1/1, rounded up to the cent).
// End cut (production applyProfitRules with TENNIS_END_LOSER_CUT on; settleFrac = TENNIS_NO_EXIT_BEFORE_END_FRAC 0.30).
//   Production reads two progress values. The ride rule reads the reading of the tick (g.progress). The cut and the entry
//   block read the latched progress (MatchTracker.progressHigh): the furthest progress that every reading of the last
//   PROGRESS_LATCH_MS (2 min) has held, so a reading that does not hold for 2 min never starts the cut. Family B takes the
//   latch from the grid when the grid carries it (research/tennisTaSim.ts grids: g.progressHigh, a production-default
//   tracker's latch over its 5 s decisions; it must not fall, and anything else throws). Otherwise family B runs the same
//   rule over g.progress, one reading a sample (latchedProgress; the tests pin it to MatchTracker.latchProgress). Net after
//   fees at the bid is production's positionNetAtBid on the open contracts' cost a contract (openSidePrice + openEntryFee:
//   the ask paid + the entry fee / count). A family B position is one fill, so this equals count x bid - exit fee - (count x
//   ask + entry fee), as before #290-#292; no outcome changes.
//   A position in profit after fees at a sample with a bid whose reading is in the last share rides: no exit sells it, even
//   before the latch gets there (production's lastShare). Once the latched progress is in the last share, the position is
//   judged at every sample with a bid. Net <= 0 -> cut (sold at the bid one latency later, kind 'cut'). Net > 0 while the
//   reading is in the last share -> it rides. Net > 0 after a comeback took the reading back under the share -> the fixed
//   exit applies again. Before the latch gets there, a position that is not riding keeps its fixed exit: production does
//   not cut it yet. A position still open at closeIdx settles: payout count x 1 or 0 by g.resultA, no settlement fee. It is
//   a 'ride' if its last judgement was "in profit after fees in the last share". Otherwise it is a 'breach', held to
//   settlement not in profit: a cut with no bid to sell into up to closeIdx, or a position the last share never reached.
//   Breaches are counted per cell.
// Stress (FamilyBCell.stressSum): the same entries and exit decisions, every sale stressTicks (1) tick lower, floored at
//   0.01 (F2), and every fee at stressFeeMult (1.25, A7's "fees x1.25") times the multipliers; settlement payouts
//   unchanged. diagnostics.settings records both.
//
// Contexts (A1/A7 cell = series x match phase x price bucket; section 5's band x phase x trend grid is replaced):
//   tour series (g.series, e.g. KXATPMATCH) x phase at the decision {pre (before liveIdx or never live), first20 (the
//   first 20 min after liveIdx), t1 / t2 / t3 (then progress < 1/3, < 2/3, >= 2/3)} x price bucket of the ask paid
//   {b08-15 [0.08, 0.15), b15-25 [0.15, 0.25), b75-85 [0.75, 0.85), b85-92 [0.85, 0.92], other}, plus 'all'. Best-of-3
//   vs best-of-5 (A7) cannot be told from a MatchGrid (no title or tournament), so it is not a context. t3 is always in
//   the design. The end-entry block reads the latched progress, so entries go on at a reading of 2/3 or more until the
//   reading has held 1 - settleFrac - margin (0.65) for 2 min. With the defaults in a 2 h match the reading passes 2/3
//   about 2 min after 0.65, inside the latch's lag; a reading that jumps or comes back can get there at any time.
//
// Placebo (FamilyBCell.units[u][2..3]): each series' trigger list (decision and side) shifted circularly inside
//   [0, closeIdx] by an offset drawn from [1800, closeIdx + 1 - 1800] (seeded by seed and the event name, one draw per
//   series). So every placebo trigger is at least 30 min from the real trigger it came from (its source), in both
//   directions; a shorter shift would replay the real trigger's own move. A placebo whose shift did not wrap lies after its
//   source, so its position never holds across it. A placebo whose shift wrapped lies before its source, and its position
//   must close before the source's decision. A position open across the source holds the move that defined the real
//   trigger: a MOM trigger toward A is an A rise, and a ride to settlement across it is paid by a result that the move made
//   likelier. That biases the placebo even with no edge anywhere: toward the real arm for follow, away from it for fade
//   (anti-conservative there). It is not a neutral leak. A fixed exit is decided by its time stop at the latest (stop =
//   fill + 900 s) and sells at the next bid, inside the 30 min. Only a ride holds a position past its stop, and riding
//   from the stop to the source (898+ s later) needs two things. First, a reading in the last share at the stop, so the
//   first such reading comes at or before the stop. Second, the latch in the last share within 2 min of the stop: a ride
//   needs the reading there at every sample, and 2 min of that latches it. So a wrapped placebo trigger is left out
//   (diagnostics placeboSpanExcluded) when its longest stop (decision + latency + 900 s) is at or after the first reading
//   in the last share and the latched cut share starts no later than that stop + 2 min (+10 s of slack for a grid latch
//   taken at 5 s decisions). Every position that could ride past its source is left out, and only the triggers in the
//   last ~17 min before the latched cut share can be; with the defaults the end-entry block (latched 0.65) shortens that.
//   The rule reads the trigger's time and the match clock, never the position's outcome. Dropping only the positions
//   that did outlast their source would drop rides, which are positions in profit, and bias the arm down. The clock's
//   info part moves with the price, so the rule's edge still depends a little on the path near the cut share. It is not
//   free of bias either: it takes that clock window out of the placebo arm only (the real arm and the shifts that did
//   not wrap keep it), and positions filled there earn more than elsewhere (more of them ride or settle, with no exit
//   fee), so the placebo mean comes out a little lower, which favours the real arm in both directions. Measured on 80
//   synthetic grids (logit random walks drifting toward the result, latch from the grid or not, gaps; rule on vs off):
//   870 of 79,030 placebo positions go (39 of them would have been open past their source, at +1.89 $ each), the
//   placebo mean goes -1.5530 -> -1.5552 $ a position (follow -0.0007, fade -0.0042) against an SE of about 0.010; real
//   positions in the window average -1.39 against -1.66 elsewhere. Most of the move (about -0.0017) is losing the 39
//   leaking rides; the rest (about -0.0005) is the window's other placebo positions. The circular shift itself puts
//   more placebo mass in the window than the real arm has there (about 5.4% of positions vs 4.0%; 4.3% with the rule).
//   diagnostics.spanWindow measures all of this on every run, with an exact replay of each series without the rule from
//   its first left-out trigger. Taking the same window out of both arms (real triggers and every placebo trigger in it)
//   would remove the asymmetry but drops production's last entries from the real arm (4% of real positions on those
//   grids): a design change for Amendment 3, not made here. The other way past the source is a sale that waits through
//   it for a bid (no bid on that side for 15+ min). Those positions are kept and counted (diagnostics
//   placeboSpanSource; ending them would give the placebo arm exits the real arm does not have).
//   Left as Amendment 3 has it: a reading on 5 m bars looks back further than the 30 min arc (RSI 14 bars), and the arc
//   covers the exits and the trigger's last bar, not the whole look-back. No
//   placebo for a match with fewer than 3600 samples (diagnostics noPlaceboMatches / noPlaceboEntries). Placebo triggers
//   go through exactly the same entry rule (end block, jump mask and fade band included), lock, exits and context
//   classification (their own context at the shifted time). The two arms make different numbers of entries per cell
//   (real triggers cluster where the price moves), so they are compared by MEAN net per entry per unit, never by sums:
//   units carry the counts for that. Day rows carry them too: a pairing by day (the registry's control row, C7) must scale
//   the placebo to the real arm's entries, n[d] x placebo sum[d] / placebo n[d], never use the raw placebo sum (the arm
//   that enters less often would gain the fees it did not pay).
//
// Universe (A5): an H match with no tape on either market is skipped and counted (diagnostics noTape).
// Zero-volume minutes (A7: flagged): entries whose decision follows 60 s without a single taker contract on either
//   market are counted in diagnostics zeroVolEntries; they are not masked.
//
// Design size (the m for Benjamini-Hochberg) = series x 2 directions x contexts x 5 exits, contexts = 1 + phases x 5
//   buckets x the tour series seen (5 phases). H: 11 TA columns x 2 bars + 16 primitives = 38 series (KXATPMATCH +
//   KXWTAMATCH: 38 x 2 x 51 x 5 = 19,380 cells); R: 11 x 4 + 24 = 68 series (KXATPMATCH only: 68 x 2 x 26 x 5 = 17,680
//   cells).
//
// Output: exportCells() (contract C3) gives every cell with a real or placebo entry: entries, the first four moments of net
// per entry, breaches, gross, fees, stressSum, per-unit and per-day [n, sum, placebo n, placebo sum], and the distinct
// markets each arm entered.
//
// Window (Amendment 4, Steven's one test; research/tennisTaWindow.ts holds the rule): every real entry of a TA reading
//   cell (never a placebo one, never a confluence primitive: a family B hot spot is one TA-Lib reading and its direction on
//   the 1 m or 5 m bars) is also a signal instance of the window test, one per direction that took the entry: a taker buy
//   of the called market (follow: the side the trigger names; fade: the other) at the event study's own entry, the ask at
//   the fill sample (decision + latency), C = max(1, floor($10 / ask)) contracts (contractsFor: the amendment's $10, no lot
//   cap), level = levelFor(ask, C, FEES), judged by windowOutcome on that market's minute candles (MatchGrid.candles, set
//   by the sweep through the sim; a grid without candles records nothing and is counted, diagnostics noCandles) under the
//   end rule endRuleTs (the match's latched progress reaching 1 - 0.30, else the close sample's time t0 + closeIdx s: a
//   MatchGrid carries no close time), with three twins (drawTwins, seeded `${event}|${row id}|${entry minute}`, the entry
//   minute's end as YYYY-MM-DDTHH:MM, as the sim seeds family A's). Rows (exportWindow, contract C12 under the shard's
//   'familyBWindow'): one per reading x bar x direction of the stratum's design, instances or none, id
//   '<reading>|<bar>|<follow|fade>', no leg, per-event arrays indexed by the study's own event list (the matches with
//   candles, in the order first seen; the sweep re-maps them onto the shard's events). The window test reads the event
//   study's entries and changes none of them, nor its exits or its placebo; the twins are its random yardstick (no placebo
//   windows).

import { loadConfig, paperEnv } from '../bot/config';
import { orderFee, type FeeSchedule } from '../bot/fees';
import { positionNetAtBid } from '../bot/strategy/fairValueStrategy';
import { taEngine, taEngineError, tl } from '../bot/ta/talib';
import { PROGRESS_LATCH_MS } from '../bot/tennis/tennisStrategy';
import type { FamilyBCell, FamilyBExport, MatchGrid } from './tennisTaTypes';
import {
  contractsFor, drawTwins, endRuleTs, levelFor, ORDER_USD, PLACEBO_SEED, SETTLE_FRAC, TWINS, WINDOW_VERSION, WindowAgg, windowOutcome, type WindowRow,
} from './tennisTaWindow';

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
const N_PB = PHASES.length * BUCKETS.length; // 25 context slots per tour series
const MAX_TOURS = 64;
const CTX_STRIDE = 1 + N_PB * MAX_TOURS;
const DIRS = ['follow', 'fade'];
/** The window test's phase names (research/tennisTaSim.ts phaseLabel, contract C12 byPhase) of the study's PHASES. */
const WINDOW_PHASES = ['pre', 'e20', 'p1', 'p2', 'p3'];

const TIME_STOP = [120, 600, 900, 900, 900];
/** The longest time stop: a position held past it rides (or waits for a bid). */
const T_MAX = Math.max(...TIME_STOP);
/** The progress latch in 1 s samples, and the slack for a grid latch taken at the sim's 5 s decisions (it can trail a latch
 *  over the 1 s readings by a decision and a sample). */
const LATCH_SAMPLES = Math.ceil(PROGRESS_LATCH_MS / 1000 - 1e-9);
const LATCH_SLACK = 10;
const MAX_SPREAD = 0.05;
const FADE_MIN = 0.1;
const FADE_MAX = 0.9;
const FIRST_PHASE_SEC = 20 * 60;
/** Minimum placebo shift (s): longer than the longest fixed exit (900 s) plus latency and the longest bar (300 s). A ride
 *  can hold longer: a wrapped placebo whose position could ride is left out (diagnostics placeboSpanExcluded), and one that
 *  waits for a bid past its source is counted (placeboSpanSource). */
export const PLACEBO_MIN_SEC = 1800;
/** H's synthesized book is one level of 100 contracts a side. */
export const H_LOT_CAP = 100;
const JUMP = 0.1;
const JUMP_LAG = 60;
const JUMP_MASK = 180;
const EPS = 1e-9;
const ZERO_SNAP = 1e-12;
const NEG = -1_000_000_000;
/** Shortest segment worth a TA-Lib pass (MOM 10 needs 11 bars for one value, a crossing two values). */
const MIN_SEG = 12;

type TaKind = 'ext' | 'zero' | 'adx';
/** How a reading's window is checked for flatness: close changes, bar ranges, STOCH's three fastK windows, signed flow,
 *  MFI's money flow. `win` = closes (close) or bars (the others) the reading at bar k reads. */
type Valid = 'close' | 'range' | 'stoch' | 'flow' | 'mfi';
interface TaReading { name: string; trigger: string; kind: TaKind; lo: number; hi: number; valid: Valid; win: number }
const TA_READINGS: TaReading[] = [
  { name: 'RSI14L', trigger: 'exitExt', kind: 'ext', lo: 30, hi: 70, valid: 'close', win: 15 },
  { name: 'STOCH14_3_3L', trigger: 'exitExt', kind: 'ext', lo: 20, hi: 80, valid: 'stoch', win: 14 },
  { name: 'WILLR14L', trigger: 'exitExt', kind: 'ext', lo: -80, hi: -20, valid: 'range', win: 14 },
  { name: 'CCI14L', trigger: 'exitExt', kind: 'ext', lo: -100, hi: 100, valid: 'range', win: 14 },
  { name: 'BBP20_2L', trigger: 'reenter', kind: 'ext', lo: 0, hi: 1, valid: 'close', win: 20 },
  { name: 'MACDH12_26_9L', trigger: 'zeroX', kind: 'zero', lo: 0, hi: 0, valid: 'close', win: 10 },
  { name: 'SLOPE14L', trigger: 'zeroX', kind: 'zero', lo: 0, hi: 0, valid: 'close', win: 14 },
  { name: 'MOM10L', trigger: 'zeroX', kind: 'zero', lo: 0, hi: 0, valid: 'close', win: 11 },
  { name: 'OBVS14', trigger: 'zeroX', kind: 'zero', lo: 0, hi: 0, valid: 'flow', win: 14 },
  { name: 'MFI14', trigger: 'exitExt', kind: 'ext', lo: 20, hi: 80, valid: 'mfi', win: 14 },
  { name: 'ADX14L', trigger: 'thrX', kind: 'adx', lo: 25, hi: 25, valid: 'range', win: 14 },
];
const N_TA = TA_READINGS.length;
const R_OBVS = TA_READINGS.findIndex((t) => t.name === 'OBVS14');

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
const FIRST_PRIM = N_TA * BAR_LENS.length;

const phaseBucketNames: string[] = [];
for (const p of PHASES) for (const b of BUCKETS) phaseBucketNames.push(`${p}:${b}`);

/** The design labels, for the report. Contexts are 'all' plus '<tour series>:<phase>:<bucket>' for every tour series seen
 *  (listed here for the two tours of the trial; any other tennis series follows the same pattern). Every phase is in the
 *  design (see designSize()). */
export const SIGNAL_SPEC: { readings: string[]; bars: string[]; exits: string[]; phases: string[]; buckets: string[]; contexts: string[] } = {
  readings: [...TA_READINGS.map((t) => t.name), 'MOM', 'OPP', 'FLOW', 'DEPTH'],
  bars: [...BAR_NAMES, '1s'],
  exits: [...EXITS],
  phases: [...PHASES],
  buckets: [...BUCKETS],
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
  /** Decision of the real trigger this one came from: the shifted-from decision for a placebo, `decision` for a real one.
   *  A placebo with source > decision and exitIdx > source was still open after its source trigger (placeboSpanSource). */
  source: number;
  /** Sample whose quotes decided the exit (a sale fills one latency later); for ride / breach the last judgement. */
  exitDecision: number;
  /** Sample of the sale, or closeIdx for ride / breach. */
  exitIdx: number;
  /** Sale price, or the settlement payout per contract (1 / 0) for ride / breach. */
  exitPx: number;
  kind: ExitKind; net: number; gross: number; fees: number; stressNet: number;
}

export interface SignalStudyOpts {
  orderUsd?: number;
  latencySec?: number;
  seed?: number;
  /** Bar lengths to run (names from '10s', '30s', '1m', '5m'; default all four). H runs 1m and 5m only (A1). */
  bars?: readonly string[];
  /** The last share of the match for the end cut (default: production TENNIS_NO_EXIT_BEFORE_END_FRAC, 0.30). */
  settleFrac?: number;
  /** No entry from this much progress before the last share (default: production TENNIS_END_ENTRY_MARGIN, 0.05). */
  endEntryMargin?: number;
  /** Stress: ticks off every sale (default 1) and multiplier on every fee (default 1.25). */
  stressTicks?: number;
  stressFeeMult?: number;
  /** The study's stratum up front (else the first match's; exportCells throws when there is neither). */
  stratum?: 'H' | 'R';
  /** Diagnostics: called for every simulated position (real and placebo). */
  trace?: (t: EntryTrace) => void;
}

/** Run counters (not part of the inference). */
export interface SignalDiagnostics {
  matches: number;
  /** H matches skipped for having no tape on either market (A5). */
  noTape: number;
  /** Grids with fewer than 2 samples. */
  tooShort: number;
  /** Matches too short for a placebo (closeIdx + 1 < 2 x 1800 samples), and the real entries they made. */
  noPlaceboMatches: number;
  noPlaceboEntries: number;
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
  /** Real triggers at or after the end-entry block. */
  endBlocked: number;
  /** Bars without a valid 5 s mark after a bar series' first close (each cuts the TA segment). */
  gapBars: number;
  /** Real H positions whose count was capped at 100; real R positions over 100 contracts (no depth on the grid). */
  hCapped: number;
  rOver100: number;
  /** Real positions by exit kind. */
  kinds: Record<ExitKind, number>;
  /** Grids whose day is before an earlier grid's (allowed: nothing in the study depends on the order). */
  outOfOrderGrids: number;
  /** Placebo positions (direction x exit) still open after the decision of the real trigger they were shifted from: a
   *  wrapped shift whose sale waited for a bid past it (kept, see the header's Placebo). */
  placeboSpanSource: number;
  /** Wrapped placebo triggers left out because their position could ride past their source (their longest time stop at
   *  or after the first reading in the last share, and the latched cut share no later than 2 min (+10 s) after it; see the
   *  header's Placebo). */
  placeboSpanExcluded: number;
  /** The size of that rule's bias, measured on every run (see the header's Placebo): sums over the run, so shards add up. */
  spanWindow: SpanWindowDiag;
  /** Matches whose grid carried production's latched progress (g.progressHigh); the others latched g.progress here. */
  progressHighFromGrid: number;
  /** The window test (Amendment 4; header, Window): matches whose grid carried no minute candles (no instance recorded for
   *  them), and the instances recorded (one per direction of every real TA entry of a match with candles). */
  noCandles: number;
  windowInstances: number;
}

/** Positions (direction x exit) and their net $ after fees around the placebo exclusion (header, Placebo). Its window: the
 *  fill's longest time stop (fill + 900 s) at or after the first reading in the last share, and the latched cut share no
 *  later than that stop + 2 min (+10 s). The rule drops the window from the placebo arm only (its wrapped triggers). The
 *  placebo arm without the rule has (allPlaceboNet - ruleOnNet + ruleOffNet) / (allPlaceboPositions - ruleOnPositions +
 *  ruleOffPositions) a position, against allPlaceboNet / allPlaceboPositions with it; realNet / realPositions against the
 *  rest of the real arm says how the window's positions differ. */
export interface SpanWindowDiag {
  /** Real positions filled in the window, and every real position. */
  realPositions: number; realNet: number; allRealPositions: number; allRealNet: number;
  /** Placebo positions recorded with the fill in the window (shifts that did not wrap), and every recorded placebo position. */
  placeboPositions: number; placeboNet: number; allPlaceboPositions: number; allPlaceboNet: number;
  /** Recorded placebo positions from each series' first left-out trigger on (per match), and the same stretch replayed
   *  from the same lock without the rule (measured only: never recorded or traced). Before that trigger both are the same. */
  ruleOnPositions: number; ruleOnNet: number; ruleOffPositions: number; ruleOffNet: number;
  /** Replayed positions open past their source: the leak the rule is for. */
  ruleOffPastSource: number; ruleOffPastSourceNet: number;
}

const spanWindowZero = (): SpanWindowDiag => ({
  realPositions: 0, realNet: 0, allRealPositions: 0, allRealNet: 0, placeboPositions: 0, placeboNet: 0, allPlaceboPositions: 0,
  allPlaceboNet: 0, ruleOnPositions: 0, ruleOnNet: 0, ruleOffPositions: 0, ruleOffNet: 0, ruleOffPastSource: 0, ruleOffPastSourceNet: 0,
});

type UnitRow = [number, number, number, number];
type DayRow = [number, number, number, number];

class Cell {
  n = 0; sum = 0; sumSq = 0; sum3 = 0; sum4 = 0;
  breaches = 0; gross = 0; fees = 0; stressSum = 0;
  /** Distinct markets (match x side) with a real / a placebo entry. */
  markets = 0; placeboMarkets = 0;
  private mStamp = -1;
  private mSeen = 0;
  readonly units = new Map<string, UnitRow>();
  readonly days = new Map<string, DayRow>();
  private uStamp = -1;
  private uRow: UnitRow = [0, 0, 0, 0];
  private dStamp = -1;
  private dRow: DayRow = [0, 0, 0, 0];
  /** The match's unit row (stamp = the match's ordinal, so a cell looks its row up once per match). */
  unitRow(stamp: number, unit: string): UnitRow {
    if (stamp !== this.uStamp) {
      let r = this.units.get(unit);
      if (!r) { r = [0, 0, 0, 0]; this.units.set(unit, r); }
      this.uRow = r; this.uStamp = stamp;
    }
    return this.uRow;
  }
  /** Counts the entry's market (side 0 = A, 1 = B of the match `stamp`) once per arm. */
  market(stamp: number, side: number, placebo: boolean): void {
    if (stamp !== this.mStamp) { this.mStamp = stamp; this.mSeen = 0; }
    const bit = (placebo ? 4 : 1) << side;
    if (this.mSeen & bit) return;
    this.mSeen |= bit;
    if (placebo) this.placeboMarkets++; else this.markets++;
  }
  dayRow(stamp: number, day: string): DayRow {
    if (stamp !== this.dStamp) {
      let r = this.days.get(day);
      if (!r) { r = [0, 0, 0, 0]; this.days.set(day, r); }
      this.dRow = r; this.dStamp = stamp;
    }
    return this.dRow;
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
/**
 * Production's latched progress over one reading every stepMs (bot/tennis/tennisStrategy.ts MatchTracker.latchProgress,
 * which applyProfitRules' end cut and entry block read). out[i] = the furthest progress that every reading from the last one
 * at or before (reading i's time - PROGRESS_LATCH_MS) through reading i has held, as of reading i. It is 0 until a whole span
 * is covered and never falls. A NaN reading in a covered span sticks as NaN, as production's Math.min / Math.max make it.
 * O(n) with a monotone queue of the span's minimum; the tracker rescans its span every tick.
 */
export function latchedProgress(prog: ArrayLike<number>, n = prog.length, stepMs = 1000, out = new Float64Array(n)): Float64Array {
  const w = Math.ceil(PROGRESS_LATCH_MS / stepMs - 1e-9);
  const q = new Int32Array(n);
  let qh = 0, qt = 0, high = 0, lastNaN = -1;
  for (let i = 0; i < n; i++) {
    const p = prog[i];
    if (p === p) { while (qt > qh && prog[q[qt - 1]] >= p) qt--; q[qt++] = i; } else lastNaN = i;
    while (qt > qh && q[qh] < i - w) qh++;
    if (i >= w) high = lastNaN >= i - w ? NaN : Math.max(high, prog[q[qh]]);
    out[i] = high;
  }
  return out;
}

/** The window test's row id of a TA series and a direction (contract C12, family B): '<reading>|<bar>|<follow|fade>'. */
function windowRowId(s: number, dir: number): string { return `${SERIES[s].reading}|${SERIES[s].bar}|${DIRS[dir]}`; }

const logit = (p: number) => { const q = p < 0.01 ? 0.01 : p > 0.99 ? 0.99 : p; return Math.log(q / (1 - q)); };
const tick = (x: number) => Math.round(x * 1e4) / 1e4;
const nz = (x: number) => (x === x ? x : 0);
const r9 = (x: number) => Math.round(x * 1e9) / 1e9;

/** Production defaults of the end cut (bot/config.ts with no TENNIS_* override), read once. */
let prodEnd: { settleFrac: number; endEntryMargin: number } | undefined;
function productionEnd(): { settleFrac: number; endEntryMargin: number } {
  if (!prodEnd) { const t = loadConfig(paperEnv({})).tennis; prodEnd = { settleFrac: t.settleFrac, endEntryMargin: t.endEntryMargin }; }
  return prodEnd;
}

// buffer slots
const F_PA = 0, F_MIDA = 1, F_MIDB = 2, F_CYA = 3, F_CNA = 4, F_CYB = 5, F_CNB = 6, F_CVOL = 7, F_CHG = 8, F_CARRY = 18, F_HIGH = 19; // F_CHG: 10 slots
const I_NBA = 1, I_NBB = 2, I_LVA = 3, I_LVB = 4, I_NVA = 5, I_NVB = 6, I_JUMP = 7;

export class SignalStudy {
  private readonly orderUsd: number;
  private readonly lat: number;
  private readonly seed: number;
  private readonly settleFrac: number;
  private readonly endEntryMargin: number;
  /** A reading at or over this is in the last share (Infinity when settleFrac is 0: no last share). */
  private readonly share: number;
  private readonly stressTicks: number;
  private readonly stressFeeMult: number;
  private readonly feesStress: FeeSchedule;
  /** Bar lengths asked for (by index into BAR_LENS). */
  private readonly barOn: boolean[];
  private readonly barsAsked: boolean;
  private readonly trace?: (t: EntryTrace) => void;
  private readonly cellMap = new Map<number, Cell>();
  private readonly tours = new Map<string, number>();
  private stratum?: 'H' | 'R';
  private lastDay = '';
  private readonly diag: SignalDiagnostics = {
    matches: 0, noTape: 0, tooShort: 0, noPlaceboMatches: 0, noPlaceboEntries: 0, triggers: 0, entries: 0, placeboEntries: 0, zeroVolEntries: 0,
    jumpMasked: 0, fadeBand: 0, endBlocked: 0, gapBars: 0, hCapped: 0, rOver100: 0,
    kinds: { time: 0, tp: 0, sl: 0, trail: 0, cut: 0, ride: 0, breach: 0 },
    outOfOrderGrids: 0, placeboSpanSource: 0, placeboSpanExcluded: 0, spanWindow: spanWindowZero(), progressHighFromGrid: 0,
    noCandles: 0, windowInstances: 0,
  };

  // ---- per-match state (buffers reused across matches) ----
  private g!: MatchGrid;
  private n = 0;
  private closeIdx = 0;
  private day = '';
  private unit = '';
  private stamp = 0;
  private tour = 0;
  private onH = true;
  private placeboOn = false;
  /** First sample where the latched progress is in the last share (the end cut judges from there), n if never. */
  private cutIdx = 0;
  /** First sample from which no entry is placed (the end-entry block, on the latched progress), n if never. */
  private entryEnd = 0;
  /** First sample whose progress reading is in the last share (a position in profit can ride from there), n if never. */
  private shareIdx = 0;
  /** Did this match's grid carry production's latched progress? */
  private highFromGrid = false;
  /** The match's latched progress a sample (progressHighOf), kept for the window test's end rule. */
  private high: ArrayLike<number> = new Float64Array(0);
  // ---- the window test (Amendment 4; header, Window) ----
  /** Rows by series x direction (key s * 2 + dir), all indexed by winIndex: event -> index of winEvents (the matches with
   *  candles, in the order first seen). */
  private readonly winAggs = new Map<number, WindowAgg>();
  private readonly winEvents: string[] = [];
  private readonly winIndex = new Map<string, number>();
  /** The current match carries candles (its entries are instances), and its end-rule time (ms). */
  private winOn = false;
  private winEndTs = 0;
  private readonly f64: Float64Array[] = [];
  private readonly i32: Int32Array[] = [];
  private trig = new Int32Array(4096);
  private nTrig = 0;
  /** Each series' triggers are trig[seriesStart[s] .. seriesEnd[s]), sorted by decision. */
  private readonly seriesStart = new Int32Array(N_SERIES);
  private readonly seriesEnd = new Int32Array(N_SERIES);
  private plc = new Int32Array(4096);
  /** The current placebo list: its first plcWrap entries wrapped (source = decision + N - offset), the rest did not
   *  (source = decision - offset). */
  private plcWrap = 0;
  private plcOff = 0;
  private plcN = 0;
  // exit scratch
  private xAt = 0;
  private xPx = 0;
  private xKind = 0;
  private xDec = 0;
  /** positionNetAtBid's bid (reused). */
  private readonly quote = { price: 0 };

  constructor(opts: SignalStudyOpts = {}) {
    if (taEngine() !== 'talib') {
      throw new Error(`tennisTaSignals: family B needs the TA-Lib engine (bot/ta/talib.ts), the active engine is ${taEngine()} (${taEngineError() ?? 'unknown reason'})`);
    }
    this.orderUsd = opts.orderUsd ?? 10;
    this.lat = Math.max(0, Math.ceil(opts.latencySec ?? 1));
    this.seed = (opts.seed ?? 20261105) >>> 0;
    const prod = opts.settleFrac === undefined || opts.endEntryMargin === undefined ? productionEnd() : undefined;
    this.settleFrac = opts.settleFrac ?? prod!.settleFrac;
    this.endEntryMargin = opts.endEntryMargin ?? prod!.endEntryMargin;
    this.share = this.settleFrac > 0 ? 1 - this.settleFrac - 1e-9 : Infinity;
    this.stressTicks = opts.stressTicks ?? 1;
    this.stressFeeMult = opts.stressFeeMult ?? 1.25;
    this.feesStress = { ...FEES, takerMultiplier: FEES.takerMultiplier * this.stressFeeMult, makerMultiplier: FEES.makerMultiplier * this.stressFeeMult };
    this.barsAsked = opts.bars !== undefined;
    for (const b of opts.bars ?? []) if (!BAR_NAMES.includes(b)) throw new Error(`tennisTaSignals: unknown bar ${b} (bars: ${BAR_NAMES.join(', ')})`);
    this.barOn = BAR_NAMES.map((b) => opts.bars === undefined || opts.bars.includes(b));
    this.stratum = opts.stratum;
    this.checkBars();
    this.trace = opts.trace;
  }

  private checkBars(): void {
    if (this.stratum !== 'H' || !this.barsAsked) return;
    const bad = BAR_NAMES.filter((_, b) => this.barOn[b] && !BAR_ON_H[b]);
    if (bad.length) throw new Error(`tennisTaSignals: bars ${bad.join(', ')} run on recorded books (R) only, not on H (A1)`);
  }

  /** How many cells exist in the design (BH m), including cells that never fired: series of this stratum x 2 directions x
   *  (1 + phases x 5 buckets x tour series seen) contexts x 5 exits. */
  designSize(): number {
    const onR = this.stratum === 'R';
    let series = 0;
    for (const s of SERIES) {
      if (s.rOnly && !onR) continue;
      if (s.ta >= 0 && !this.barOn[s.b]) continue;
      series++;
    }
    // Every phase, t3 included: the end-entry block reads the latched progress, so a reading of 2/3 or more can still enter.
    return series * 2 * (1 + PHASES.length * BUCKETS.length * this.tours.size) * N_EXIT;
  }

  diagnostics(): SignalDiagnostics {
    const w = this.diag.spanWindow, spanWindow = { ...w };
    for (const k of Object.keys(w) as (keyof SpanWindowDiag)[]) spanWindow[k] = r9(w[k]);
    return { ...this.diag, kinds: { ...this.diag.kinds }, spanWindow };
  }

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
  private push(v: number): void {
    if (this.nTrig >= this.trig.length) { const t = new Int32Array(this.trig.length * 2); t.set(this.trig); this.trig = t; }
    this.trig[this.nTrig++] = v;
  }

  /** Evaluate one completed match. Grids of one study share a stratum and carry their unit (anything else throws); they
   *  may come in any day order (a grid that is out of order is counted in diagnostics outOfOrderGrids). */
  addMatch(g: MatchGrid): void {
    if (typeof g.unit !== 'string' || !g.unit) throw new Error(`tennisTaSignals: grid ${g.event} has no unit (the sweep sets MatchGrid.unit before addMatch)`);
    if (g.stratum !== 'H' && g.stratum !== 'R') throw new Error(`tennisTaSignals: grid ${g.event} has stratum ${String(g.stratum)}`);
    if (this.stratum === undefined) { this.stratum = g.stratum; this.checkBars(); }
    else if (g.stratum !== this.stratum) throw new Error(`tennisTaSignals: grid ${g.event} is stratum ${g.stratum} in a ${this.stratum} study (H and R are never mixed)`);
    if (g.day < this.lastDay) this.diag.outOfOrderGrids++;
    else this.lastDay = g.day;
    const n = g.n;
    if (!(n > 1)) { this.diag.tooShort++; return; }
    this.g = g;
    this.n = n;
    this.closeIdx = Math.min(Math.max(0, g.closeIdx), n - 1);
    this.day = g.day;
    this.unit = g.unit;
    this.stamp++;
    this.onH = g.stratum === 'H';
    this.prepareQuotes();
    if (this.onH && this.f64[F_CVOL][n] <= 0) { this.diag.noTape++; return; }
    let tour = this.tours.get(g.series);
    if (tour === undefined) {
      if (this.tours.size >= MAX_TOURS) throw new Error(`tennisTaSignals: more than ${MAX_TOURS} tour series`);
      tour = this.tours.size;
      this.tours.set(g.series, tour);
    }
    this.tour = tour;
    this.diag.matches++;
    if (this.highFromGrid) this.diag.progressHighFromGrid++;
    this.prepareWindow();
    this.nTrig = 0;
    const onR = !this.onH;
    this.buildBarSeries(onR);
    this.buildPrimitives(onR);
    this.diag.triggers += this.nTrig;
    const N = this.closeIdx + 1;
    this.placeboOn = N >= 2 * PLACEBO_MIN_SEC;
    if (!this.placeboOn) this.diag.noPlaceboMatches++;
    const rng = mulberry32((hash32(g.event) ^ this.seed) >>> 0);
    for (let s = 0; s < N_SERIES; s++) {
      if (SERIES[s].rOnly && !onR) continue;
      // Offset in [M, N - M]: every placebo trigger is at least M from its real trigger, forward or (wrapped) backward.
      const off = this.placeboOn ? PLACEBO_MIN_SEC + Math.floor(rng() * (N - 2 * PLACEBO_MIN_SEC + 1)) : 0;
      const t0 = this.seriesStart[s], t1 = this.seriesEnd[s];
      if (t1 === t0) continue;
      const before = this.diag.entries;
      this.pass(s, this.trig, t0, t1, false);
      if (this.placeboOn) this.pass(s, this.plc, 0, this.rotate(t0, t1, off), true);
      else this.diag.noPlaceboEntries += this.diag.entries - before;
    }
  }

  /** pA, mids, the end-cut indices, next-bid lookups, valid-mid lookups, cumulative tape, jump marks. */
  private prepareQuotes(): void {
    const g = this.g, n = this.n, C = this.closeIdx;
    const pA = this.bufF(F_PA, n), mA = this.bufF(F_MIDA, n), mB = this.bufF(F_MIDB, n);
    for (let i = 0; i < n; i++) {
      const ba = g.bidA[i], aa = g.askA[i], bb = g.bidB[i], ab = g.askB[i];
      const a = ba > 0 && aa > 0 && aa >= ba ? (ba + aa) / 2 : NaN;
      const b = bb > 0 && ab > 0 && ab >= bb ? (bb + ab) / 2 : NaN;
      mA[i] = a; mB[i] = b;
      pA[i] = a === a ? (b === b ? (a + 1 - b) / 2 : a) : b === b ? 1 - b : NaN;
    }
    // The end cut and the entry block go by production's latched progress (MatchTracker.progressHigh), the ride rule by the
    // reading of the tick (g.progress).
    const frac = this.settleFrac;
    const cutAt = 1 - frac - 1e-9, blockAt = 1 - frac - this.endEntryMargin - 1e-9;
    this.cutIdx = n; this.entryEnd = n; this.shareIdx = n;
    const high = this.progressHighOf(n), prog = g.progress;
    this.high = high;
    if (frac > 0) {
      for (let i = 0; i < n; i++) if (high[i] >= blockAt) { this.entryEnd = i; break; }
      for (let i = 0; i < n; i++) if (high[i] >= cutAt) { this.cutIdx = i; break; }
      for (let i = 0; i < n; i++) if (prog[i] >= cutAt) { this.shareIdx = i; break; }
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

  /** The match's latched progress a sample: the grid's own when it carries one (research/tennisTaSim.ts grids: production's
   *  tracker over its 5 s decisions), else latchedProgress over g.progress, one reading a sample. A grid latch that is
   *  shorter than the grid or falls is not production's: it throws. */
  private progressHighOf(n: number): ArrayLike<number> {
    const g = this.g;
    const own = (g as MatchGrid & { progressHigh?: ArrayLike<number> }).progressHigh;
    this.highFromGrid = own !== undefined && own !== null;
    if (!this.highFromGrid) return latchedProgress(g.progress, n, 1000, this.bufF(F_HIGH, n));
    if (own!.length < n) throw new Error(`tennisTaSignals: grid ${g.event} has ${own!.length} progressHigh samples for ${n} samples`);
    for (let i = 1; i < n; i++) {
      if (own![i] < own![i - 1] - 1e-12) throw new Error(`tennisTaSignals: grid ${g.event} progressHigh falls at sample ${i} (${own![i - 1]} -> ${own![i]}): production's latch never falls`);
    }
    return own!;
  }

  /** The window test's state of the match (header, Window): nothing without candles (counted, diagnostics noCandles); else
   *  the event's index and the end-rule time: research/tennisTaWindow.ts endRuleTs over the match's latched progress (the
   *  same latch the end cut reads), SETTLE_FRAC 0.30 whatever the study's settleFrac (the amendment fixes it), the close
   *  sample's time as the close (a MatchGrid has closeIdx, not the market's close time; the sim sets closeIdx = floor((close
   *  - t0) / 1 s), so the two agree to the second). */
  private prepareWindow(): void {
    const g = this.g, n = this.n;
    const cand = g.candles;
    this.winOn = cand !== undefined && cand !== null;
    if (!this.winOn) { this.diag.noCandles++; return; }
    if (!this.winIndex.has(g.event)) { this.winIndex.set(g.event, this.winEvents.length); this.winEvents.push(g.event); }
    const high = this.high;
    const view = (high instanceof Float64Array ? high : Float64Array.from(high)).subarray(0, n);
    this.winEndTs = endRuleTs(view, g.t0, 1000, g.t0 + this.closeIdx * 1000, SETTLE_FRAC);
  }

  /** One real TA entry as a signal instance of the window test (header, Window): series s, direction dir, the called side
   *  (0 = A, 1 = B) bought at `ask` at the fill sample e, phase = the study's phase index at the decision. Its twins are
   *  seeded `${event}|${row id}|${entry minute}`. */
  private windowInstance(s: number, dir: number, side: number, e: number, ask: number, phase: number): void {
    const g = this.g, cand = g.candles!;
    const key = s * 2 + dir;
    let agg = this.winAggs.get(key);
    if (!agg) { agg = new WindowAgg(windowRowId(s, dir), undefined, this.winIndex); this.winAggs.set(key, agg); }
    const t = g.t0 + e * 1000;
    const C = contractsFor(ask, ORDER_USD), level = levelFor(ask, C, FEES);
    const outcome = windowOutcome(side ? cand.b : cand.a, t, ask, level, this.winEndTs);
    const minute = new Date(Math.ceil(t / 60_000) * 60_000).toISOString().slice(0, 16);
    const twins = drawTwins(cand.a, cand.b, t, this.winEndTs, `${g.event}|${agg.id}|${minute}`, TWINS, ORDER_USD, side ? 'b' : 'a');
    agg.add({ event: g.event, side: side ? 'b' : 'a', leg: DIRS[dir], t, ask, C, level, phase: WINDOW_PHASES[phase], outcome, twins });
    this.diag.windowInstances++;
  }

  /** Bars, TA-Lib readings (per gap-free segment) and their triggers for the TA series of this stratum. */
  private buildBarSeries(onR: boolean): void {
    const g = this.g, n = this.n;
    const pA = this.f64[F_PA];
    for (let s = 0; s < FIRST_PRIM; s++) { this.seriesStart[s] = this.nTrig; this.seriesEnd[s] = this.nTrig; }
    for (let b = 0; b < BAR_LENS.length; b++) {
      if (!this.barOn[b] || (!BAR_ON_H[b] && !onR)) continue;
      const L = BAR_LENS[b];
      const K = Math.floor(n / L);
      if (K < MIN_SEG) continue;
      const c = new Float64Array(K), h = new Float64Array(K), l = new Float64Array(K), v = new Float64Array(K), f = new Float64Array(K);
      const gap = new Uint8Array(K);
      let prev = NaN, seen = false;
      for (let k = 0; k < K; k++) {
        let hi = prev, lo = prev, last = NaN, vol = 0, fl = 0;
        const start = k * L, end = start + L;
        for (let i = start + ((MID_STEP - 1 - (start % MID_STEP)) % MID_STEP); i < end; i += MID_STEP) {
          const p = pA[i];
          if (p === p) { last = p; if (!(hi >= p)) hi = p; if (!(lo <= p)) lo = p; }
        }
        for (let i = start; i < end; i++) {
          const ya = nz(g.yesVolA[i]), na = nz(g.noVolA[i]), yb = nz(g.yesVolB[i]), nb = nz(g.noVolB[i]);
          vol += ya + na + yb + nb; fl += ya - na - (yb - nb);
        }
        v[k] = vol; f[k] = fl;
        if (last === last) { c[k] = last; h[k] = hi; l[k] = lo; prev = last; seen = true; }
        else { gap[k] = 1; c[k] = NaN; h[k] = NaN; l[k] = NaN; prev = NaN; if (seen) this.diag.gapBars++; }
      }
      // Flat-window masks: the latest bar (same segment) with a close change, a range, a flow, a money flow; NEG if none.
      const lastChg = new Int32Array(K), lastRng = new Int32Array(K), lastFlow = new Int32Array(K), lastMf = new Int32Array(K);
      for (let k = 0; k < K; k++) {
        if (gap[k]) { lastChg[k] = NEG; lastRng[k] = NEG; lastFlow[k] = NEG; lastMf[k] = NEG; continue; }
        const first = k === 0 || gap[k - 1] === 1;
        lastChg[k] = !first && Math.abs(c[k] - c[k - 1]) > 1e-12 ? k : first ? NEG : lastChg[k - 1];
        lastRng[k] = h[k] - l[k] > 1e-12 ? k : first ? NEG : lastRng[k - 1];
        lastFlow[k] = f[k] !== 0 ? k : first ? NEG : lastFlow[k - 1];
        const mf = !first && v[k] > 0 && Math.abs((h[k] + l[k] + c[k]) - (h[k - 1] + l[k - 1] + c[k - 1])) > 3e-12;
        lastMf[k] = mf ? k : first ? NEG : lastMf[k - 1];
      }
      const res: Float64Array[] = [];
      for (let r = 0; r < N_TA; r++) res.push(new Float64Array(K).fill(NaN));
      const pdi = new Float64Array(K).fill(NaN), mdi = new Float64Array(K).fill(NaN), obv = new Float64Array(K);
      for (let k = 0; k < K;) {
        if (gap[k]) { k++; continue; }
        let k1 = k;
        while (k1 < K && !gap[k1]) k1++;
        if (k1 - k >= MIN_SEG) this.readings(c, h, l, v, f, k, k1, res, pdi, mdi, obv);
        k = k1;
      }
      const valid = (t: TaReading, k: number): boolean => {
        if (k < 0) return false;
        switch (t.valid) {
          case 'close': return lastChg[k] >= k - t.win + 2;
          case 'range': return lastRng[k] >= k - t.win + 1;
          case 'flow': return lastFlow[k] >= k - t.win + 2;
          case 'mfi': return lastMf[k] >= k - t.win + 1;
          case 'stoch':
            for (let m = k - 2; m <= k; m++) if (m < 0 || lastRng[m] < m - t.win + 1) return false;
            return true;
        }
      };
      for (let r = 0; r < N_TA; r++) {
        const s = r * BAR_LENS.length + b;
        const t = TA_READINGS[r];
        const vals = res[r];
        this.seriesStart[s] = this.nTrig;
        let lastSign = 0;
        for (let k = 1; k < K; k++) {
          const x = vals[k];
          if (!(x === x) || !valid(t, k)) { lastSign = 0; continue; }
          let side = -1;
          if (t.kind === 'zero') {
            const snap = r === R_OBVS ? 1e-9 * Math.max(1, Math.abs(obv[k])) : ZERO_SNAP;
            const sg = x > snap ? 1 : x < -snap ? -1 : 0;
            if (sg !== 0) {
              if (lastSign !== 0 && sg !== lastSign) side = sg > 0 ? 0 : 1;
              lastSign = sg;
            }
          } else {
            const u = vals[k - 1];
            if (!(u === u) || !valid(t, k - 1)) continue;
            if (t.kind === 'ext') {
              if (u < t.lo && x >= t.lo) side = 0;
              else if (u > t.hi && x <= t.hi) side = 1;
            } else if (u < t.lo && x >= t.lo) {
              side = pdi[k] >= mdi[k] || !(mdi[k] === mdi[k]) ? 0 : 1;
            }
          }
          if (side < 0) continue;
          const d = (k + 1) * L;
          if (d < n) this.push(d * 2 + side);
        }
        this.seriesEnd[s] = this.nTrig;
      }
    }
  }

  /** TA-Lib over bars [k0, k1) (one gap-free segment); writes the readings into res (aligned to the bar index). */
  private readings(c: Float64Array, h: Float64Array, l: Float64Array, v: Float64Array, f: Float64Array, k0: number, k1: number,
    res: Float64Array[], pdi: Float64Array, mdi: Float64Array, obv: Float64Array): void {
    const M = k1 - k0;
    const lc = new Array<number>(M), lh = new Array<number>(M), ll = new Array<number>(M);
    const cc = new Array<number>(M), hc = new Array<number>(M), lcn = new Array<number>(M), vv = new Array<number>(M), ob = new Array<number>(M);
    let cum = 0;
    for (let j = 0; j < M; j++) {
      const k = k0 + j;
      lc[j] = logit(c[k]); lh[j] = logit(h[k]); ll[j] = logit(l[k]);
      cc[j] = c[k] * 100; hc[j] = h[k] * 100; lcn[j] = l[k] * 100; vv[j] = v[k];
      cum += f[k]; ob[j] = cum; obv[k] = cum;
    }
    // A TA-Lib call that returns nothing is an error here, never "no triggers".
    const got = (name: string, o: Record<string, number[]>, key: string): number[] => {
      const a = o[key];
      if (!a || a.length !== M) throw new Error(`tennisTaSignals: TA-Lib ${name} returned no ${key} for ${M} bars`);
      return a;
    };
    const need = (name: string, inputs: Record<string, number[]>, opts: Record<string, number>, key: string): number[] => got(name, tl(name, inputs, opts), key);
    const put = (dst: Float64Array, a: ArrayLike<number>) => { for (let j = 0; j < M; j++) dst[k0 + j] = a[j]; };
    const lhlc = { high: lh, low: ll, close: lc };
    const bb = tl('BBANDS', { inReal: lc }, { optInTimePeriod: 20, optInNbDevUp: 2, optInNbDevDn: 2, optInMAType: 0 });
    const up = got('BBANDS', bb, 'outRealUpperBand'), dn = got('BBANDS', bb, 'outRealLowerBand');
    const pctB = new Array<number>(M);
    for (let j = 0; j < M; j++) { const w = up[j] - dn[j]; pctB[j] = w > 1e-12 ? (lc[j] - dn[j]) / w : NaN; }
    put(res[0], need('RSI', { inReal: lc }, { optInTimePeriod: 14 }, 'outReal'));
    put(res[1], need('STOCH', lhlc, { optInFastK_Period: 14, optInSlowK_Period: 3, optInSlowK_MAType: 0, optInSlowD_Period: 3, optInSlowD_MAType: 0 }, 'outSlowK'));
    put(res[2], need('WILLR', lhlc, { optInTimePeriod: 14 }, 'outReal'));
    put(res[3], need('CCI', lhlc, { optInTimePeriod: 14 }, 'outReal'));
    put(res[4], pctB);
    put(res[5], need('MACD', { inReal: lc }, { optInFastPeriod: 12, optInSlowPeriod: 26, optInSignalPeriod: 9 }, 'outMACDHist'));
    put(res[6], need('LINEARREG_SLOPE', { inReal: lc }, { optInTimePeriod: 14 }, 'outReal'));
    put(res[7], need('MOM', { inReal: lc }, { optInTimePeriod: 10 }, 'outReal'));
    put(res[8], need('LINEARREG_SLOPE', { inReal: ob }, { optInTimePeriod: 14 }, 'outReal'));
    put(res[9], need('MFI', { high: hc, low: lcn, close: cc, volume: vv }, { optInTimePeriod: 14 }, 'outReal'));
    put(res[10], need('ADX', lhlc, { optInTimePeriod: 14 }, 'outReal'));
    put(pdi, need('PLUS_DI', lhlc, { optInTimePeriod: 14 }, 'outReal'));
    put(mdi, need('MINUS_DI', lhlc, { optInTimePeriod: 14 }, 'outReal'));
  }

  /** Confluence primitives on the 1 s grid: triggers when the signal toward a player turns on from a known "off". */
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
      // Known state at i - 1 (defined, on) per side: a trigger needs on at i and a known off at i - 1.
      let dA = false, oA = false, dB = false, oB = false;
      const step = (i: number, defA: boolean, a: boolean, defB: boolean, b: boolean) => {
        if (a && dA && !oA) this.push(i * 2);
        if (b && dB && !oB) this.push(i * 2 + 1);
        dA = defA; oA = a; dB = defB; oB = b;
      };
      if (sp.prim === 'MOM' || sp.prim === 'OPP') {
        const wi = MOM_WINDOWS.indexOf(sp.w);
        const ca = this.f64[F_CHG + 2 * wi], cb = this.f64[F_CHG + 2 * wi + 1];
        const mom = sp.prim === 'MOM';
        for (let i = 0; i < n; i++) {
          // MOM toward X reads X's mid now; OPP toward X reads the other market's mid now.
          const okA = lvA[i] === i, okB = lvB[i] === i;
          const defA = mom ? okA : okB, defB = mom ? okB : okA;
          const a = defA && (mom ? ca[i] >= lev - EPS : cb[i] <= -lev + EPS);
          const b = defB && (mom ? cb[i] >= lev - EPS : ca[i] <= -lev + EPS);
          step(i, defA, a, defB, b);
        }
      } else if (sp.prim === 'FLOW') {
        const w = sp.w;
        for (let i = 0; i < n; i++) {
          const lo = i - w + 1 < 0 ? 0 : i - w + 1;
          const ya = cya[i + 1] - cya[lo], na = cna[i + 1] - cna[lo], yb = cyb[i + 1] - cyb[lo], nb = cnb[i + 1] - cnb[lo];
          const a = ya + na > 0 && (ya - na) / (ya + na) >= lev - EPS;
          const b = yb + nb > 0 && (yb - nb) / (yb + nb) >= lev - EPS;
          step(i, true, a, true, b);
        }
      } else {
        const ia = g.imbA, ib = g.imbB;
        for (let i = 0; i < n; i++) {
          const defA = ia[i] === ia[i], defB = ib[i] === ib[i];
          step(i, defA, defA && ia[i] >= lev - EPS, defB, defB && ib[i] >= lev - EPS);
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
    this.plcWrap = k; this.plcOff = off; this.plcN = N;
    for (let t = t0; t < split; t++) { const v = this.trig[t]; this.plc[k++] = ((v >> 1) + off) * 2 + (v & 1); }
    return k;
  }

  /** One entry-locked pass of series s over a sorted trigger list: both directions and all exits share each entry. A shadow
   *  pass replays a placebo list from `from` (with the lock lock0 there) without the span rule, into diagnostics spanWindow
   *  only: it records, traces and counts nothing else. */
  private pass(s: number, arr: Int32Array, from: number, to: number, placebo: boolean, shadow = false, lock0 = -1): void {
    const g = this.g;
    const lastFill = this.closeIdx - 1;
    const prog = g.progress;
    const live = g.liveIdx;
    const sp = SERIES[s];
    const isTa = sp.ta >= 0;
    const lj = this.i32[I_JUMP];
    const cv = this.f64[F_CVOL];
    const tourBase = 1 + this.tour * N_PB;
    const E = this.entryEnd;
    const sw = this.diag.spanWindow;
    let lock = lock0;
    /** The first trigger the span rule left out, and the lock there: the rule-off replay starts from it. */
    let offFrom = -1, offLock = -1;
    for (let t = from; t < to; t++) {
      const v = arr[t];
      const d = v >> 1;
      if (d <= lock) continue;
      if (d >= E) { if (!placebo) this.diag.endBlocked += to - t; break; }
      const e = d + this.lat;
      if (e > lastFill) break;
      if (isTa && lj[d] >= d - JUMP_MASK) { if (!placebo) this.diag.jumpMasked++; continue; }
      const wrapped = placebo && t < this.plcWrap;
      // A wrapped placebo lies before its source: left out when its position could ride past it, by the trigger's time and
      // the match clock, never by its outcome (see the header's Placebo). It leaves the window out of the placebo arm only:
      // diagnostics spanWindow measures what that does (the shadow replay below).
      const inWin = e + T_MAX >= this.shareIdx && e + T_MAX + LATCH_SAMPLES + LATCH_SLACK >= this.cutIdx;
      if (wrapped && inWin && !shadow) {
        this.diag.placeboSpanExcluded++;
        if (offFrom < 0) { offFrom = t; offLock = lock; }
        continue;
      }
      const ts = v & 1;
      // The real trigger's decision this one came from (a wrapped placebo lies before it).
      const src = !placebo ? d : wrapped ? d + this.plcN - this.plcOff : d - this.plcOff;
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
          if (placebo) { if (!shadow) this.diag.placeboEntries++; }
          else { this.diag.entries++; if (cv[d + 1] - cv[d + 1 - 60 < 0 ? 0 : d + 1 - 60] <= 0) this.diag.zeroVolEntries++; }
        }
        let count = Math.max(1, Math.floor(this.orderUsd / ask + EPS));
        if (count > H_LOT_CAP) {
          if (this.onH) { count = H_LOT_CAP; if (!placebo) this.diag.hCapped++; }
          else if (!placebo) this.diag.rOver100++;
        }
        const feeIn = orderFee(count, ask, true, FEES);
        const feeInS = orderFee(count, ask, true, this.feesStress);
        // The open contracts' cost a contract, as production measures every after-fee judgement (openSidePrice +
        // openEntryFee of a one-fill position).
        const costPer = ask + feeIn / count;
        // Context: tour series, phase at the decision, bucket of the ask paid.
        const phase = live < 0 || d < live ? 0 : d < live + FIRST_PHASE_SEC ? 1 : !(prog[d] >= 1 / 3) ? 2 : prog[d] < 2 / 3 ? 3 : 4;
        // The window test (Amendment 4; header, Window): every real TA entry is a signal instance of its reading x bar x
        // direction row, on this direction's called side at its ask. It reads the entry and changes nothing below.
        if (!placebo && isTa && this.winOn) this.windowInstance(s, dir, side, e, ask, phase);
        const bucket = ask >= 0.08 - EPS && ask < 0.15 - EPS ? 0 : ask >= 0.15 - EPS && ask < 0.25 - EPS ? 1
          : ask >= 0.75 - EPS && ask < 0.85 - EPS ? 2 : ask >= 0.85 - EPS && ask <= 0.92 + EPS ? 3 : 4;
        const ctx = tourBase + phase * BUCKETS.length + bucket;
        const base = (s * 2 + dir) * CTX_STRIDE;
        for (let x = 0; x < N_EXIT; x++) {
          this.exit(e, side, x, ask, count, costPer);
          const at = this.xAt, px = this.xPx, kind = this.xKind;
          let gross: number, fees: number, net: number, snet: number;
          if (kind >= K_RIDE) {
            gross = count * px - count * ask; fees = feeIn; net = gross - fees; snet = gross - feeInS;
            lockTo = Infinity;
          } else {
            const feeOut = orderFee(count, px, true, FEES);
            gross = count * (px - ask); fees = feeIn + feeOut; net = gross - fees;
            const ps = tick(Math.max(px - 0.01 * this.stressTicks, 0.01));
            snet = count * (ps - ask) - feeInS - orderFee(count, ps, true, this.feesStress);
            if (at > lockTo) lockTo = at;
          }
          if (shadow) {
            sw.ruleOffPositions++; sw.ruleOffNet += net;
            if (src > d && at > src) { sw.ruleOffPastSource++; sw.ruleOffPastSourceNet += net; }
            continue;
          }
          if (placebo) {
            sw.allPlaceboPositions++; sw.allPlaceboNet += net;
            if (inWin) { sw.placeboPositions++; sw.placeboNet += net; }
            if (offFrom >= 0) { sw.ruleOnPositions++; sw.ruleOnNet += net; }
          } else { sw.allRealPositions++; sw.allRealNet += net; if (inWin) { sw.realPositions++; sw.realNet += net; } }
          if (!placebo) this.diag.kinds[KIND_NAMES[kind]]++;
          else if (src > d && at > src) this.diag.placeboSpanSource++;
          const breach = kind === K_BREACH;
          this.record((base + ctx) * N_EXIT + x, net, snet, gross, fees, breach, placebo, side);
          this.record(base * N_EXIT + x, net, snet, gross, fees, breach, placebo, side);
          if (this.trace) {
            this.trace({
              series: `${sp.reading}|${sp.bar}|${sp.trigger}`, dir: dir ? 'fade' : 'follow', exit: EXITS[x], context: this.ctxName(ctx), placebo,
              decision: d, fill: e, side: side ? 'B' : 'A', entryPx: ask, count, source: src, exitDecision: this.xDec, exitIdx: at, exitPx: px, kind: KIND_NAMES[kind],
              net, gross, fees, stressNet: snet,
            });
          }
        }
      }
      if (took) lock = lockTo;
    }
    if (offFrom >= 0) this.pass(s, arr, offFrom, to, true, true, offLock);
  }

  private ctxName(ctx: number): string {
    if (ctx === 0) return 'all';
    const k = ctx - 1, tour = Math.floor(k / N_PB), pb = k % N_PB;
    let name = '';
    for (const [t, i] of this.tours) if (i === tour) { name = t; break; }
    return `${name}:${phaseBucketNames[pb]}`;
  }

  private record(key: number, net: number, snet: number, gross: number, fees: number, breach: boolean, placebo: boolean, side: number): void {
    let c = this.cellMap.get(key);
    if (!c) { c = new Cell(); this.cellMap.set(key, c); }
    c.market(this.stamp, side, placebo);
    const u = c.unitRow(this.stamp, this.unit), dr = c.dayRow(this.stamp, this.day);
    if (placebo) { u[2]++; u[3] += net; dr[2]++; dr[3] += net; return; }
    u[0]++; u[1] += net;
    dr[0]++; dr[1] += net;
    const x2 = net * net;
    c.n++; c.sum += net; c.sumSq += x2; c.sum3 += x2 * net; c.sum4 += x2 * x2;
    c.stressSum += snet; c.gross += gross; c.fees += fees;
    if (breach) c.breaches++;
  }

  /** Production's net after fees at the bid (bot/strategy/fairValueStrategy.ts positionNetAtBid) on the open contracts'
   *  cost a contract. */
  private netAt(count: number, costPer: number, b: number): number {
    this.quote.price = b;
    return positionNetAtBid(count, costPer, this.quote, undefined, FEES)!;
  }

  /** Exit of a position filled at e on side (0 = A, 1 = B): sets xDec (deciding sample), xAt (sale sample, or closeIdx when
   *  it settles), xPx (sale price, or the payout 1 / 0) and xKind. costPer = the open contracts' cost a contract (the ask
   *  + the entry fee / count: production's openSidePrice + openEntryFee). */
  private exit(e: number, side: number, x: number, ask: number, count: number, costPer: number): void {
    const g = this.g, C = this.closeIdx, B = this.cutIdx, S = this.shareIdx;
    const bid = side ? g.bidB : g.bidA;
    const nb = side ? this.i32[I_NBB] : this.i32[I_NBA];
    const prog = g.progress;
    const share = this.share;
    const stop = e + TIME_STOP[x];
    const bracket = x === 2 || x === 3, trail = x === 4;
    const tp = bracket ? ask * (x === 2 ? 1.3 : 1.5) - EPS : Infinity, sl = bracket ? ask * (x === 2 ? 0.7 : 0.75) + EPS : -Infinity;
    const arm = ask + 0.02 - EPS;
    let armed = false, peak = 0;
    let dec = -1, kind = K_TIME, ride = false, judged = -1;
    let j = e + 1;
    // Before any reading is in the last share (so before the latch too): the fixed exit alone (decided on the quotes of j,
    // j >= e + 1).
    const lim = Math.min(stop - 1, S - 1, B - 1, C);
    if (bracket) {
      for (; j <= lim; j++) {
        const b = bid[j];
        if (b >= tp) { dec = j; kind = K_TP; break; }
        if (b <= sl) { dec = j; kind = K_SL; break; }
      }
    } else if (trail) {
      for (; j <= lim; j++) {
        const b = bid[j];
        if (!(b > 0)) continue;
        if (!armed) { if (b >= arm) { armed = true; peak = b; } }
        else if (b > peak) peak = b;
        else if (b <= peak - 0.03 + EPS) { dec = j; kind = K_TRAIL; break; }
      }
    } else if (j <= lim) j = lim + 1;
    if (dec < 0 && j <= C) {
      if (j < S && j < B) { dec = j; kind = K_TIME; } // j === stop
      else {
        // From the first reading in the last share: production's profit rules judge the position before the fixed exit.
        for (; j <= C; j++) {
          const b = bid[j];
          const has = b > 0;
          const cutting = j >= B;
          // In the cut share (by the latched progress) a sample without a bid is not judged: nothing to sell into.
          if (cutting && !has) continue;
          let trailHit = false;
          if (trail && has) {
            if (!armed) { if (b >= arm) { armed = true; peak = b; } }
            else if (b > peak) peak = b;
            else if (b <= peak - 0.03 + EPS) trailHit = true;
          }
          if (has) {
            const inShare = prog[j] >= share;
            if (inShare || cutting) {
              judged = j;
              const net = this.netAt(count, costPer, b);
              // lastShare and in profit after fees: rides (no exit sells it), whether or not the latch is there yet.
              if (inShare && net > EPS) { ride = true; continue; }
              // cutShare and not in profit after fees: never held to settlement.
              if (cutting && !(net > EPS)) { dec = j; kind = K_CUT; ride = false; break; }
            }
            // Not riding: under the share (a comeback, or the latch not there yet), or not in profit before the latch.
            ride = false;
          }
          if (j >= stop) { dec = j; kind = K_TIME; break; }
          if (b >= tp) { dec = j; kind = K_TP; break; }
          if (b <= sl) { dec = j; kind = K_SL; break; }
          if (trailHit) { dec = j; kind = K_TRAIL; break; }
        }
      }
    }
    const won = side === 0 ? g.resultA === 1 : g.resultA === 0;
    if (dec >= 0) {
      // Sold one latency after the deciding sample, at the first bid from there (never on the deciding sample's quote).
      const k0 = Math.max(dec + this.lat, e + 1);
      const k = k0 <= C ? nb[k0] : -1;
      if (k >= 0) { this.xDec = dec; this.xAt = k; this.xPx = bid[k]; this.xKind = kind; return; }
      // No bid to sell into up to closeIdx: held to settlement after a decision to sell, not in profit in the last share.
      ride = false;
    }
    this.xDec = dec >= 0 ? dec : judged >= 0 ? judged : C;
    this.xAt = C;
    this.xPx = won ? 1 : 0;
    this.xKind = ride ? K_RIDE : K_BREACH;
  }

  /** The window test's rows (contract C12, the shard's 'familyBWindow' block; header, Window): one per TA reading x bar x
   *  direction of this stratum's design, in design order, instances or none; `events` is the study's own event list (the
   *  matches with candles, in the order first seen), which the rows' per-event arrays index. Throws without a stratum, as
   *  exportCells does (the design differs between H and R). The study can keep running after it. */
  exportWindow(): { events: string[]; rows: WindowRow[] } {
    const stratum = this.stratum;
    if (stratum === undefined) {
      throw new Error('tennisTaSignals: exportWindow of a study that has no stratum (pass opts.stratum to new SignalStudy: a slice without a grid cannot tell H from R, and their designs differ)');
    }
    const onR = stratum === 'R';
    const rows: WindowRow[] = [];
    for (let s = 0; s < FIRST_PRIM; s++) {
      const sp = SERIES[s];
      if ((sp.rOnly && !onR) || !this.barOn[sp.b]) continue;
      for (let dir = 0; dir < 2; dir++) rows.push((this.winAggs.get(s * 2 + dir) ?? new WindowAgg(windowRowId(s, dir), undefined, this.winIndex)).row());
    }
    return { events: [...this.winEvents], rows };
  }

  /** Every cell with a real or placebo entry, in design order (contract C3); the study can keep running after it. Throws
   *  when the stratum is unknown (none given to the constructor and no grid seen): the design differs between H and R. */
  exportCells(): FamilyBExport {
    const stratum = this.stratum;
    if (stratum === undefined) {
      throw new Error('tennisTaSignals: exportCells of a study that has no stratum (pass opts.stratum to new SignalStudy: a slice without a grid cannot tell H from R, and their designs differ)');
    }
    const out: FamilyBCell[] = [];
    const keys = [...this.cellMap.keys()].sort((a, b) => a - b);
    for (const key of keys) {
      const c = this.cellMap.get(key)!;
      const x = key % N_EXIT, rest = (key - x) / N_EXIT;
      const ctx = rest % CTX_STRIDE, sd = (rest - ctx) / CTX_STRIDE;
      const dir = sd % 2, s = (sd - dir) / 2;
      const sp = SERIES[s];
      const group = `B|${sp.reading}|${sp.bar}|${sp.trigger}|${DIRS[dir]}`;
      const units: Record<string, [number, number, number, number]> = {};
      for (const [u, r] of c.units) units[u] = [r[0], r9(r[1]), r[2], r9(r[3])];
      const days: Record<string, [number, number, number, number]> = {};
      for (const [d, r] of c.days) days[d] = [r[0], r9(r[1]), r[2], r9(r[3])];
      out.push({
        id: `${group}|${this.ctxName(ctx)}|${EXITS[x]}`, group,
        n: c.n, sum: r9(c.sum), sumSq: c.sumSq, sum3: c.sum3, sum4: c.sum4,
        breaches: c.breaches, gross: r9(c.gross), fees: r9(c.fees), stressSum: r9(c.stressSum),
        units, days, markets: c.markets, placeboMarkets: c.placeboMarkets,
      });
    }
    const bars = BAR_NAMES.filter((_, b) => this.barOn[b] && (stratum === 'R' || BAR_ON_H[b]));
    return {
      stratum,
      designSize: this.designSize(),
      diagnostics: {
        ...this.diagnostics(),
        tours: [...this.tours.keys()],
        settings: {
          orderUsd: this.orderUsd, latencySec: this.lat, seed: this.seed, bars, settleFrac: this.settleFrac, endEntryMargin: this.endEntryMargin,
          phasesInDesign: [...PHASES], placeboMinSec: PLACEBO_MIN_SEC, hLotCap: H_LOT_CAP,
          // The end cut and the entry block read the progress held this long (production MatchTracker.progressHigh).
          progressLatchMs: PROGRESS_LATCH_MS,
          stress: `every sale ${this.stressTicks} tick(s) lower (F2), every fee x${this.stressFeeMult}`, stressTicks: this.stressTicks, stressFeeMult: this.stressFeeMult,
          taEngine: taEngine(),
          // The window test (header, Window): its rule's constants, as the shard's 'window' block records them.
          window: { version: WINDOW_VERSION, settleFrac: SETTLE_FRAC, orderUsd: ORDER_USD, twins: TWINS, seed: PLACEBO_SEED },
        },
      },
      cells: out,
    };
  }
}
