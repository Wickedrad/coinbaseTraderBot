// Tennis match-winner markets (KXATPMATCH, KXWTAMATCH): a rules-based, order-book
// driven strategy with hard budget caps.
//
// Phases per match (an event with one "Will <player> win?" market per player):
//
//   1. UNDERDOG BOUNCE. Just before or just after the start, if the market is
//      heavily skewed (underdog <= underdogMax, favorite >= 1 - underdogMax),
//      bid for the underdog as a maker. After a fill, rest a maker take-profit
//      at max(entry + takeProfitCents, entry x (1 + takeProfitPct)). This is a
//      VOLATILITY trade: early breaks move tennis prices a lot, and the plan is
//      to sell into that bounce. Research on tennis and Kalshi (favourite-
//      longshot bias: Lahvicka 2014; Burgi, Deng & Whelan) finds longshots win
//      LESS often than their price implies, so holding underdogs to settlement
//      is expected to lose. The take-profit is the point of the trade; an
//      optional stop exists (off by default: max loss is the entry price).
//   2. WAIT while tracking the match.
//   3. FAVORITE RE-ENTRY. Once the match is at least favMinProgress done and
//      one side leads clearly (price in [favMin, favMax]) and has been stable
//      (not down more than favStableCents over 5 minutes), bid for the leader
//      as a maker and hold to settlement (optional stop, off by default).
//      "Safer" means a high hit rate, not low risk: at 85c a win pays 15c and a
//      loss costs 85c.
//
// Match state:
//   - started = the published start time passed, or (without one) the first
//     mid move of liveMoveCents within 3 minutes (in-play prices move on
//     every point; pre-match prices barely move);
//   - progress is measured in points by a tennis scoring model
//     (tennisModel.ts: deuce, 7-point tiebreaks, 10-point final-set tiebreak
//     at the Slams, best of 3/5) calibrated to the pre-match price, blended
//     with how much of the match's price uncertainty has already resolved.
//     With a live score (TENNIS_SCORE_FEED) progress comes from the exact
//     score. See MatchTracker.progress.
//
// Steven's profit rules apply here as on every contract type (Oct 29-30, see decideMatch): the quota snipe
// sells a position whose profit after fees covers what the clock hour needs, and in the last 30% of the
// match (by that progress, not the market's window) a position in profit rides to settlement, until our
// player's win chance turns (Nov 12). Out of profit (Nov 12): a loser cut that narrows as the match goes on
// (20c a contract at the start, 10c at 60%, 3c from 85%) and in the last 10% the end cut sells it at the bid.
//
// Pure logic (no I/O): the engine turns plans into risk-checked orders.

import type { TennisConfig } from '../config';
import type { OrderBook } from '../marketdata/orderBook';
import { LiquidityRatchet } from '../strategy/exitPolicies';
import { quotaCall, type PacerFloorMode, type QuotaFloors } from '../risk/quotaPacer';
import { floorToTick, round } from '../util/num';
import { impliedModel, scoreProgress, timeProgress, type MatchFormat, type TennisScore } from './tennisModel';

export interface Quote { bid?: number; ask?: number; bidSize?: number; askSize?: number }

export interface MatchMarket {
  ticker: string; title?: string; quote: Quote; position: number; avgEntry?: number; book?: OrderBook;
  /** Signed taker flow on this market over the last minute: (YES-taker - NO-taker) / total, in [-1, 1]. */
  flow?: number;
  /** The whole position's profit after fees if sold at the bid now, the entry fee in (the quota snipe's measure on every
   *  contract type, bot/strategy/fairValueStrategy.ts positionNetAtBid); undefined when flat or unknown. */
  netAtBid?: number;
  /** The lowest price at which selling the whole position now nets at least zero after the taker exit fee, the entry fee in
   *  (engine-computed from the book's cost and the series' fees); undefined when flat or unknown. The profit-taking exits
   *  never sell below it: entry + 1 tick alone can realize a loss after fees (Steven: take profit after fees). */
  breakEven?: number;
}

/** The lowest exit price that takes a profit: one tick over the entry and at or over the break-even after fees. */
function profitFloor(m: MatchMarket, entry: number, tick: number): number {
  const be = m.breakEven !== undefined && Number.isFinite(m.breakEven) ? Math.ceil(m.breakEven / tick - 1e-9) * tick : -Infinity;
  return round(Math.max(entry + tick, be), 4);
}

export type MatchPhase = 'pre' | 'underdog_window' | 'live' | 'late' | 'done';

export interface MatchSnapshot {
  event: string;
  now: number;
  /** Published start time, if any. */
  startTime?: number;
  /** The two player markets (one is enough: the other side is 1 - p). */
  markets: MatchMarket[];
  closeTime: number;
  /** Live score, when a score feed is configured (TENNIS_SCORE_FEED). */
  score?: TennisScore;
  /** When that score was read (the engine passes the last good one on after a failed poll); unset: now. */
  scoreAt?: number;
  /** The score's player A is the first market's player (TENNIS_SCORE_FEED=livetennis matches the names to the market titles;
   *  Kalshi's live data does not say which player is home). Only such a score gives a win chance (MatchTracker.winChance). */
  scoreOriented?: boolean;
  /** Tennis MLP fair P(player A wins), present only when that model is validated. */
  fairA?: number;
}

/** The tennis MLP decides whether an entry is worth taking: our player's fair P(win) must clear the
 *  buy price by fairMinEdge. Undefined = no validated model (the rules decide alone). */
function fairBlocks(s: MatchSnapshot, m: MatchMarket, px: number, cfg: TennisConfig): string | undefined {
  if (s.fairA === undefined) return undefined;
  const fair = m === s.markets[0] ? s.fairA : 1 - s.fairA;
  return fair - px < cfg.fairMinEdge - 1e-12 ? `tennis model: fair ${fair.toFixed(3)} - price ${px.toFixed(2)} < ${cfg.fairMinEdge}` : undefined;
}

export interface TennisPlan {
  ticker: string;
  side: 'bid' | 'ask';
  price: number;
  count: number;
  postOnly: boolean;
  reduceOnly: boolean;
  timeInForce: 'good_till_canceled' | 'immediate_or_cancel';
  leg: 'underdog_entry' | 'underdog_tp' | 'underdog_trail' | 'underdog_late' | 'underdog_cut' | 'underdog_stop' | 'fav_entry' | 'fav_trail' | 'fav_stop' | 'quota_snipe' | 'end_cut' | 'loser_cut' | 'prob_turn';
  why: string;
}

const GRAND_SLAMS = /(australian open|roland garros|french open|wimbledon|us open)/i;

const mid = (q: Quote) => (q.bid !== undefined && q.ask !== undefined && q.ask >= q.bid ? (q.bid + q.ask) / 2 : undefined);

/** Per-match state machine. */
/** How long a progress reading must hold before the loser cut and the entry block take it as reached (MatchTracker.progressHigh). */
export const PROGRESS_LATCH_MS = 120_000;
/** How old a live score may be and still give a win chance: the Live Tennis feed is read every 5 minutes while a position is held. */
export const SCORE_FRESH_MS = 6 * 60_000;
/** The widest spread a book may have for the market's win chance (MatchTracker.winChance) to count: one tick's thin or
 *  one-sided book (asks pulled, a stale or gapped book) moves the mid without any trade, and a ride's sale (prob_turn) must
 *  not follow it. Every market of the match must be two-sided within this, else the market gives no reading that tick. */
export const WIN_CHANCE_MAX_SPREAD = 0.06;

export class MatchTracker {
  liveSince?: number;
  underdogTicker?: string;
  underdogEntered = false;
  underdogClosed = false;
  favEntered = false;
  /** Trailing stops (per held market): armed once the bid reached the target. */
  readonly armed = new Set<string>();
  readonly ratchets = new Map<string, LiquidityRatchet>();
  readonly stops = new Map<string, number>();
  /** When each trail armed, and the best bid seen since (conservative price hunt). */
  readonly armedAt = new Map<string, number>();
  /** The price each trail starts at while the bid is still below it (PACER_FLOOR: a set price above the quota). */
  readonly trailStart = new Map<string, number>();
  readonly peak = new Map<string, number>();
  /** The furthest progress the match has held for PROGRESS_LATCH_MS (every reading in that span at least this). Progress
   *  falls back when the price returns toward 50/50 (a comeback), so the loser cut and the entry block go by this, not the
   *  reading of the tick (TENNIS_END_LOSER_CUT); one tick's thin or one-sided book cannot set it. */
  progressHigh = 0;
  private readonly progressSeen: Array<{ ts: number; p: number }> = [];
  /** Per held market riding to settlement in profit: our player's best win chance since the ride began, by each reading
   *  (TENNIS_PROB_TURN). A ride once begun lasts while the position is in profit, whatever the progress does. */
  readonly rides = new Map<string, { score?: number; market?: number }>();
  /** Markets a ride's sale (prob_turn) has sold this match: no new entry on them for the rest of it. The win chance turned
   *  against that player, so the favorite leg must not buy the same player back a tick later. */
  readonly turnSold = new Set<string>();

  /** Takes this tick's progress reading and returns progressHigh. */
  latchProgress(now: number, p: number): number {
    const seen = this.progressSeen;
    if (seen.length && now < seen[seen.length - 1].ts) seen.length = 0;
    seen.push({ ts: now, p });
    // Keep one reading at or before the span's start, so the span is known to be covered.
    while (seen.length > 1 && seen[1].ts <= now - PROGRESS_LATCH_MS) seen.shift();
    if (seen[0].ts <= now - PROGRESS_LATCH_MS) this.progressHigh = Math.max(this.progressHigh, Math.min(...seen.map((x) => x.p)));
    return this.progressHigh;
  }
  /** Last tennis-confluence reading per held market (dashboard). */
  readonly signals = new Map<string, { score: number; momentum: boolean; flow: boolean; depth: boolean; crossMarket: boolean }>();
  private history: Array<{ ts: number; p: number }> = [];
  /** Match price at the start (calibrates the scoring model), last pre-match price, realized
   * variation of the price since the start (information clock), live score when known. */
  pStart?: number;
  private pPre?: number;
  private qv = 0;
  private qvLast?: { ts: number; p: number };
  score?: TennisScore;
  /** When the score was read, and whether its player A is the first market's (MatchSnapshot.scoreAt, scoreOriented). */
  scoreAt?: number;
  scoreOriented = false;
  private readonly mids = new Map<string, Array<{ ts: number; p: number }>>();

  /** Mid change of one market over the last `ms` (undefined without enough history). */
  midChange(ticker: string, now: number, ms = 60_000): number | undefined {
    const h = this.mids.get(ticker);
    if (!h?.length) return undefined;
    const past = h.find((x) => x.ts >= now - ms);
    const last = h[h.length - 1];
    if (!past || last.ts - past.ts < ms / 2) return undefined;
    return last.p - past.p;
  }

  constructor(readonly event: string, private readonly cfg: TennisConfig) {}

  /** P(first market's player wins) from the book(s): average of market A and 1 - market B when both exist. */
  static probability(ms: MatchMarket[]): number | undefined {
    const a = ms[0] ? mid(ms[0].quote) : undefined;
    const b = ms[1] ? mid(ms[1].quote) : undefined;
    if (a !== undefined && b !== undefined) return (a + (1 - b)) / 2;
    return a ?? (b !== undefined ? 1 - b : undefined);
  }

  /** Grand Slam main draw: best of 5 with a 10-point final-set tiebreak. Slam qualifying, and the women's
   * matches (WTA series) at the Slams: best of 3 with the 10-point final-set tiebreak. Everything else on
   * the tours: best of 3, 7-point tiebreaks. */
  format(ms: MatchMarket[]): MatchFormat {
    const titles = ms.map((m) => m.title ?? '').join(' ');
    const slam = GRAND_SLAMS.test(titles);
    const quali = /qualif/i.test(titles);
    const wta = ms.some((m) => /^KXWTA/i.test(m.ticker));
    return { bestOf: slam && !quali && !wta ? 5 : 3, finalTiebreak: slam ? 10 : 7 };
  }

  bestOf(ms: MatchMarket[]): 3 | 5 {
    return this.format(ms).bestOf;
  }

  /**
   * How far along the match is, 0..1, measured in points rather than minutes:
   *  - score clock (when a live score is known): points played vs the model's expected remaining
   *    points from the exact score (sets, games, deuce, tiebreak);
   *  - otherwise a blend of
   *    - point clock: minutes / secPerPoint vs the model's distribution of the match length, which
   *      depends on the format and on how lopsided the pre-match price was (a 90/10 match is ~20%
   *      shorter than a 50/50 one); a match running long is assumed to have more to go, never 100%;
   *    - information clock: the share of the match's price uncertainty already resolved. The win
   *      probability is a martingale ending at 0 or 1, so the price variation still to come is
   *      p(1-p) on average: progress = resolved / (resolved + p(1-p)), resolved = max(realised
   *      variation, p0(1-p0) - p(1-p)). A blowout resolves fast, a tight tiebreak-heavy match slowly.
   */
  progress(now: number, ms: MatchMarket[]): number {
    return this.progressDetail(now, ms).progress;
  }

  progressDetail(now: number, ms: MatchMarket[]): { progress: number; time?: number; info?: number; score?: number; expectedMin?: number; bestOf: 3 | 5 } {
    const format = this.format(ms);
    if (this.liveSince === undefined) return { progress: 0, bestOf: format.bestOf };
    const model = impliedModel(this.pStart ?? 0.5, format, this.cfg.serveBase);
    const st = model.start();
    const expectedMin = (st.mean * this.cfg.secPerPoint) / 60;
    if (this.score) {
      const sc = scoreProgress(model, this.score);
      return { progress: sc, score: sc, expectedMin, bestOf: format.bestOf };
    }
    const time = timeProgress(Math.max(0, now - this.liveSince) / 1000 / this.cfg.secPerPoint, st.mean, st.sd);
    const p = this.history.length ? this.history[this.history.length - 1].p : undefined;
    const rest = p === undefined ? undefined : p * (1 - p);
    // Resolved variance so far: realised variation, or at least the drop in p(1-p) since the start
    // (their expectations are equal; the drop is robust to smooth drifts and sparse sampling).
    const p0 = this.pStart ?? 0.5;
    const resolved = rest === undefined ? 0 : Math.max(this.qv, p0 * (1 - p0) - rest);
    const info = rest === undefined ? undefined : resolved + rest > 0 ? resolved / (resolved + rest) : 1;
    const w = info === undefined ? 0 : this.cfg.progressInfoWeight;
    return { progress: w * (info ?? 0) + (1 - w) * time, time, info, expectedMin, bestOf: format.bestOf };
  }

  /** Our player's chance to win the match, by each reading there is: the market's price (MatchTracker.probability), and the
   *  scoring model's (the points, games and sets still to play from the exact score, on serve-point odds calibrated to the
   *  match's starting price: tennisModel.ts) from a live score that names its players (scoreOriented) and was read within
   *  SCORE_FRESH_MS of `now`. The market's reading needs every book of the match two-sided within WIN_CHANCE_MAX_SPREAD.
   *  Undefined when the ticker is not one of the match's markets. */
  winChance(ms: MatchMarket[], ticker: string, now?: number): { score?: number; market?: number } | undefined {
    const a = ms[0]?.ticker === ticker;
    if (!a && ms[1]?.ticker !== ticker) return undefined;
    const side = (pA: number | undefined) => (pA === undefined || !Number.isFinite(pA) ? undefined : a ? pA : 1 - pA);
    const fresh = now === undefined || this.scoreAt === undefined || now - this.scoreAt <= SCORE_FRESH_MS;
    const score = this.score && this.liveSince !== undefined && this.scoreOriented && fresh
      ? side(impliedModel(this.pStart ?? 0.5, this.format(ms), this.cfg.serveBase).remaining(this.score).pA) : undefined;
    const tight = (q: Quote) => q.bid !== undefined && q.ask !== undefined && q.ask >= q.bid && q.ask - q.bid <= WIN_CHANCE_MAX_SPREAD + 1e-9;
    const market = ms.every((m) => tight(m.quote)) ? side(MatchTracker.probability(ms)) : undefined;
    return { ...(score !== undefined ? { score } : {}), ...(market !== undefined ? { market } : {}) };
  }

  /** Update from a snapshot; returns the phase. */
  observe(s: MatchSnapshot): MatchPhase {
    const p = MatchTracker.probability(s.markets);
    if (p !== undefined) {
      this.history.push({ ts: s.now, p });
      while (this.history.length && this.history[0].ts < s.now - 15 * 60_000) this.history.shift();
    }
    for (const m of s.markets) {
      const mp = mid(m.quote);
      if (mp === undefined) continue;
      const h = this.mids.get(m.ticker) ?? [];
      h.push({ ts: s.now, p: mp });
      while (h.length && h[0].ts < s.now - 5 * 60_000) h.shift();
      this.mids.set(m.ticker, h);
    }
    if (s.score) { this.score = s.score; this.scoreAt = s.scoreAt ?? s.now; this.scoreOriented = s.scoreOriented === true; }
    if (this.liveSince === undefined) {
      if (s.startTime !== undefined && s.now >= s.startTime) this.liveSince = s.startTime;
      else if ((s.startTime === undefined || (this.cfg.liveByMove && s.startTime - s.now <= this.cfg.liveByMoveLeadMin * 60_000)) && p !== undefined) {
        const recent = this.history.filter((h) => h.ts >= s.now - 3 * 60_000);
        const moved = recent.length > 1 && Math.max(...recent.map((h) => h.p)) - Math.min(...recent.map((h) => h.p)) >= this.cfg.liveMoveCents - 1e-9;
        if (moved) { this.liveSince = s.now; this.pPre = recent[0].p; }
      }
      if (this.liveSince === undefined && p !== undefined) this.pPre = p;
    }
    if (this.liveSince !== undefined && p !== undefined) {
      this.pStart ??= this.pPre ?? p;
      if (!this.qvLast) this.qvLast = { ts: s.now, p: this.pStart };
      if (s.now - this.qvLast.ts >= this.cfg.qvSampleSec * 1000) {
        this.qv += (p - this.qvLast.p) ** 2;
        this.qvLast = { ts: s.now, p };
      }
    }
    if (s.now >= s.closeTime) return 'done';
    if (this.liveSince === undefined) {
      const soon = s.startTime !== undefined && s.startTime - s.now <= this.cfg.preStartMin * 60_000;
      return soon ? 'underdog_window' : 'pre';
    }
    if (s.now - this.liveSince <= this.cfg.entryWindowMin * 60_000) return 'underdog_window';
    return this.progress(s.now, s.markets) >= this.cfg.favMinProgress ? 'late' : 'live';
  }

  /** Price change of a side over the last `ms` (positive = up). */
  change(side: 'a' | 'b', now: number, ms = 5 * 60_000): number | undefined {
    const past = this.history.find((h) => h.ts >= now - ms);
    const last = this.history[this.history.length - 1];
    if (!past || !last || last.ts - past.ts < ms / 2) return undefined;
    const d = last.p - past.p;
    return side === 'a' ? d : -d;
  }
}

/**
 * Tennis confluence: tennis has no macro factors, but the book and tape of the two player
 * markets give four independent confirmations that a move toward OUR player is real
 * (thresholds configurable; defaults over the last 60 s):
 *   momentum     our player's mid rose >= confMomentumCents (1c)
 *   flow         taker flow on our market favours our player (>= confFlow, +0.2)
 *   depth        top-3 book imbalance favours our player (bids heavier, >= confDepth, +0.2)
 *   crossMarket  the opponent's market fell >= confOpponentCents (1c): the move is not one
 *                noisy book
 * Used to enter (underdog, favorite) and to decide whether to keep hunting past the target.
 */
export function tennisConfluence(t: MatchTracker, m: MatchMarket, other: MatchMarket | undefined, now: number, cfg: TennisConfig) {
  const w = cfg.confWindowSec * 1000;
  const mom = t.midChange(m.ticker, now, w);
  const oth = other ? t.midChange(other.ticker, now, w) : undefined;
  const momentum = mom !== undefined && mom >= cfg.confMomentumCents - 1e-9;
  const flow = m.flow !== undefined && m.flow >= cfg.confFlow - 1e-9;
  const depth = m.book !== undefined && m.book.imbalance(3) >= cfg.confDepth - 1e-9;
  const crossMarket = oth !== undefined && oth <= -cfg.confOpponentCents + 1e-9;
  return { score: [momentum, flow, depth, crossMarket].filter(Boolean).length, momentum, flow, depth, crossMarket };
}

/** Sell price that the visible bids can absorb for the whole position, never below `minPx`. */
function nextFillableExit(m: MatchMarket, minPx: number): number | undefined {
  const bid = m.quote.bid;
  if (bid === undefined) return undefined;
  let px = bid;
  if (m.book) {
    let cum = 0;
    for (const l of m.book.snapshot(20).bids) { cum += l.size; px = l.price; if (cum + 1e-9 >= m.position) break; }
  }
  const limit = Math.max(px, minPx);
  return bid >= minPx - 1e-9 ? limit : undefined;
}

/**
 * Conservative price hunt past the target, then the next available exit in profit.
 *  - Below the target: no exit order, the position rides.
 *  - At the target: hunt only if >= huntMinSignals tennis-confluence signals agree; otherwise take
 *    the profit right away.
 *  - While hunting: stop = max(target lock, order-book wall ratchet (levels that can fill the whole
 *    position), peak bid - huntTrailTicks). The hunt lasts at most huntMaxSec.
 *  - Exit (bid breaks the stop, signals fade, or time is up): sell reduce-only at the price the
 *    visible bids can absorb, never below entry + 1 tick. Below that, hold (optional hard stop).
 */
function huntExit(t: MatchTracker, m: MatchMarket, other: MatchMarket | undefined, entry: number, target: number, now: number, cfg: TennisConfig, tick: number, leg: 'underdog_trail' | 'fav_trail', notes: string[]): TennisPlan[] {
  const bid = m.quote.bid;
  const sig = tennisConfluence(t, m, other, now, cfg);
  t.signals.set(m.ticker, sig);
  if (!t.armed.has(m.ticker)) {
    if (bid === undefined || bid < target - 1e-9) {
      notes.push(`${leg}: holding, hunt starts at ${target.toFixed(2)} (bid ${bid ?? '—'})`);
      t.trailStart.set(m.ticker, target);
      return [];
    }
    t.trailStart.delete(m.ticker);
    t.armed.add(m.ticker);
    t.armedAt.set(m.ticker, now);
  }
  const floorPx = profitFloor(m, entry, tick);
  const sell = (why: string): TennisPlan[] => {
    const px = nextFillableExit(m, floorPx);
    if (px === undefined) { notes.push(`${leg}: exit wanted but bid ${bid} is not in profit; holding`); return []; }
    return [{ ticker: m.ticker, side: 'ask', price: round(px, 4), count: m.position, postOnly: false, reduceOnly: true, timeInForce: 'immediate_or_cancel', leg, why }];
  };
  const peak = Math.max(t.peak.get(m.ticker) ?? 0, bid ?? 0);
  t.peak.set(m.ticker, peak);
  let stop = Math.max(target, round(peak - cfg.huntTrailTicks * tick, 4));
  if (m.book) {
    let r = t.ratchets.get(m.ticker);
    if (!r) { r = new LiquidityRatchet({ minFillRatio: cfg.trailMinFillRatio, minWallAgeMs: cfg.trailMinWallAgeSec * 1000, slippageTicks: cfg.trailSlippageTicks }); t.ratchets.set(m.ticker, r); }
    const out = r.evaluate({ position: m.position, book: m.book, now, tick, fees: { takerMultiplier: 1, makerMultiplier: 1 }, floor: target });
    if (out.stop !== undefined) stop = Math.max(stop, out.stop);
  }
  t.stops.set(m.ticker, stop);
  const huntedSec = (now - (t.armedAt.get(m.ticker) ?? now)) / 1000;
  notes.push(`${leg}: hunting, stop ${stop.toFixed(2)}, confluence ${sig.score}/4, ${huntedSec.toFixed(0)}s`);
  if (bid !== undefined && bid < stop - 1e-9) return sell(`${leg}: bid ${bid} broke the stop ${stop.toFixed(2)}`);
  if (sig.score < cfg.huntMinSignals) return sell(`${leg}: only ${sig.score}/4 confluence signals: taking the profit`);
  if (huntedSec >= cfg.huntMaxSec) return sell(`${leg}: hunt time limit ${cfg.huntMaxSec}s: taking the profit`);
  return [];
}

/** Buy-side view of a market: price to bid (maker) for YES of this player. */
function makerBid(q: Quote, tick: number, maxSpread: number): number | undefined {
  if (q.bid === undefined || q.ask === undefined) return undefined;
  const spread = q.ask - q.bid;
  if (spread > maxSpread + 1e-9) return undefined;
  // Improve by one tick when the spread allows, else join.
  const px = spread >= 2 * tick - 1e-9 ? round(q.bid + tick, 4) : q.bid;
  return px < q.ask ? px : undefined;
}

export interface BudgetView {
  /** Working cash pool (tradable bankroll). */
  bankroll: number;
  /** Worst-case loss of all tennis positions + resting orders now. */
  tennisRisk: number;
  /** Worst-case loss already committed to this match. */
  matchRisk: number;
}

/** Contracts for a new entry within the per-order, per-match and 25% total caps. Tennis series
 * charge maker fees (multiplier 1: 0.0175 x P(1-P) per contract, rounded up per order), so the
 * fee and one cent of rounding are budgeted too. */
export function tennisSize(price: number, cfg: TennisConfig, b: BudgetView, makerMultiplier = 1): number {
  const room = Math.min(
    cfg.orderFrac * b.bankroll,
    cfg.maxMatchFrac * b.bankroll - b.matchRisk,
    cfg.maxTotalFrac * b.bankroll - b.tennisRisk,
  ) - 0.01;
  const cost = price + makerMultiplier * 0.0175 * price * (1 - price);
  if (!(room > 0) || !(price > 0)) return 0;
  return Math.floor((room / cost) * 100) / 100;
}

/** Steven's profit rules as tennis sees them (Oct 29-30; bot/risk/quotaPacer.ts). */
export interface TennisProfitRules {
  /** The net dollars a position must be up for its sale now (the pacer's slice); undefined while the pacer is off. */
  pacerUsd?: number;
  /** The last share of the match (TENNIS_NO_EXIT_BEFORE_END_FRAC, 0.30) in which a position in profit after fees
   *  rides to settlement. A share of the match's progress (MatchTracker.progress: the live score's sets, games and points
   *  against the format's best-of, else the time and information clocks), not of the market's window: a match market
   *  closes long after the match ends. 0 or unset = off. */
  settleFrac?: number;
  /** TENNIS_END_LOSER_CUT: in that last share a position not in profit after fees is sold at the bid (never held to
   *  settlement), and no entry is placed. */
  endLoserCut?: boolean;
  /** TENNIS_END_ENTRY_MARGIN: with endLoserCut, no new entry once the match is this much short of its last share. */
  endEntryMargin?: number;
  /** TENNIS_END_CUT_FRAC (Steven, Nov 12: 0.10, the match's last 10%): the share in which endLoserCut sells a position not in
   *  profit and no entry is placed. Unset: settleFrac's share (the rule before Nov 12). */
  endCutFrac?: number;
  /** The loser cut by the match's progress (Steven, Nov 12): a position not in profit after fees is sold at the bid once the
   *  bid is this far under its entry (dollars a contract). loserCut is the line at 60% of the match (TENNIS_LOSER_CUT_C, 10c);
   *  it runs from loserCutOpen at the start (TENNIS_LOSER_CUT_OPEN_C, 20c) to it, then to loserCutLate by 85%
   *  (TENNIS_LOSER_CUT_LATE_C, 3c) and stays there. 0 or unset = off. Goes by the furthest progress held (progressHigh). */
  loserCut?: number;
  loserCutOpen?: number;
  loserCutLate?: number;
  /** TENNIS_PROB_TURN (0.05): a position riding to settlement in profit is sold at the bid once our player's win chance
   *  (MatchTracker.winChance) is this far under its best since the ride began, while it is still in profit. 0 = off. */
  probTurn?: number;
  /** PACER_FLOOR (bot/risk/quotaPacer.ts): which legs count as aiming higher than the quota (off when unset), and the floors. */
  floorMode?: PacerFloorMode;
  floors?: QuotaFloors;
  /** PACER_FLOOR_TICKS: the floor's cushion, price ticks a contract. */
  floorTicks?: number;
}

/** The match's real start for the tracker (Nov 12 2026). Kalshi's tennis start field (occurrence_datetime, the market's
 *  startTime) is the expected finish, about 3 h after the first serve; the market's expiration_time is the scheduled
 *  first serve plus 14 days. So: expiration minus 14 days when that lands within 6 h before the published time, else the
 *  published time moved startShiftMin earlier. No published time: undefined (the tracker then reads play from the price). */
export function tennisStartTime(published: number | undefined, expiration: number | undefined, cfg: Pick<TennisConfig, 'startFromExpiry' | 'startShiftMin'>): number | undefined {
  if (published === undefined) return undefined;
  if (cfg.startFromExpiry && expiration !== undefined) {
    const fromExpiry = expiration - 14 * 86_400_000;
    if (fromExpiry <= published && published - fromExpiry <= 6 * 3_600_000) return fromExpiry;
  }
  return published - cfg.startShiftMin * 60_000;
}

/**
 * Decide orders for one match. Returns the desired resting/IOC plans; the
 * caller cancels resting tennis orders that are not in the plan.
 */
export function decideMatch(t: MatchTracker, s: MatchSnapshot, cfg: TennisConfig, budget: BudgetView, tick = 0.01, rules: TennisProfitRules = {}): { phase: MatchPhase; plans: TennisPlan[]; notes: string[] } {
  return applyProfitRules(t, s, decideLegs(t, s, cfg, budget, tick), rules, tick);
}

/** The loser cut's line at a share of the match done (0..1), in dollars a contract under the entry: loserCutOpen at the start
 *  down to loserCut at 60%, down to loserCutLate at 85%, then flat (Steven, Nov 12: wide early, today's amount at 60%, quite
 *  small by 85%; the last 10% is endLoserCut's). Ends unset take loserCut's value; 0 when the cut is off. */
export const TENNIS_CUT_MID_FRAC = 0.6;
export const TENNIS_CUT_LATE_FRAC = 0.85;
export function tennisLoserCutAt(r: Pick<TennisProfitRules, 'loserCut' | 'loserCutOpen' | 'loserCutLate'>, done: number): number {
  const mid = r.loserCut ?? 0;
  if (!(mid > 0)) return 0;
  const open = r.loserCutOpen ?? mid, late = r.loserCutLate ?? mid;
  const f = Math.min(1, Math.max(0, Number.isFinite(done) ? done : 0));
  const cut = f <= TENNIS_CUT_MID_FRAC ? open + ((mid - open) * f) / TENNIS_CUT_MID_FRAC
    : f <= TENNIS_CUT_LATE_FRAC ? mid + ((late - mid) * (f - TENNIS_CUT_MID_FRAC)) / (TENNIS_CUT_LATE_FRAC - TENNIS_CUT_MID_FRAC)
      : late;
  return round(cut, 4);
}

/**
 * Steven's profit rules (Oct 29-30), on tennis as on every contract type. Inside the last share of the match a position in
 * profit after fees rides to settlement: no exit sells it. One that is not is never held to settlement: with endLoserCut it is
 * sold at the bid (end_cut), and no entry is placed from endEntryMargin before it; without it, it keeps the legs' exits (the
 * stops, the late cut). The cut and the entry block go by the furthest progress the match has held for PROGRESS_LATCH_MS (2
 * min): a comeback pulls the progress back below the last share just as a favorite goes under water, and the position must
 * not ride that to settlement, while one tick's thin book must not start the cut for the rest of the match.
 * Elsewhere the quota snipe sells a position whose whole profit after fees at the bid covers what the clock hour needs,
 * whatever the legs planned for it (the hunt, the take-profit, the favorite's hold); a thin bid takes what it can and the
 * rest is judged again next tick. Under PACER_FLOOR (Steven, Oct 31) a leg aiming higher keeps the position instead, the
 * need it covered its floor, and the position is sold once its profit falls below that floor (tennisHigher).
 * Steven, Nov 12: the end cut and the entry block take their own share (endCutFrac, the last 10%); before it a position not
 * in profit is sold once its bid is the loser cut's line under the entry, a line that narrows as the match goes on
 * (tennisLoserCutAt by progressHigh); and a position riding in profit is sold at once, still in profit, when our player's win
 * chance turns (probTurn under its best since the ride began, by the market's price or a fresh, named live score). A ride
 * once begun lasts while the position is in profit, even when a comeback pulls the progress back under the last share: the
 * turn the exit is for pulls the progress back too. Out of profit, the cuts take it from there.
 */
function applyProfitRules(t: MatchTracker, s: MatchSnapshot, out: { phase: MatchPhase; plans: TennisPlan[]; notes: string[] }, r: TennisProfitRules, tick: number): { phase: MatchPhase; plans: TennisPlan[]; notes: string[] } {
  const frac = r.settleFrac ?? 0;
  const prog = t.liveSince !== undefined ? t.progress(s.now, s.markets) : 0;
  const lastShare = frac > 0 && prog >= 1 - frac - 1e-9;
  const high = t.latchProgress(s.now, prog);
  const endFrac = r.endCutFrac ?? frac;
  const cutShare = endFrac > 0 && high >= 1 - endFrac - 1e-9;
  const mode = r.floorMode ?? 'off';
  const pct = (x: number) => `${(x * 100).toFixed(0)}%`;
  const at = prog < high - 1e-9 ? `${pct(prog)} done, ${pct(high)} at its furthest` : `${pct(prog)} done`;
  const rebuy = out.plans.filter((p) => p.side === 'bid' && !p.reduceOnly && t.turnSold.has(p.ticker));
  if (rebuy.length) {
    out.plans = out.plans.filter((p) => !rebuy.includes(p));
    out.notes.push(`no new entry on ${[...new Set(rebuy.map((p) => p.ticker))].join(', ')} (${rebuy.map((p) => p.leg).join(', ')}): a ride was sold there this match when the win chance turned`);
  }
  if (r.endLoserCut && endFrac > 0 && high >= 1 - endFrac - (r.endEntryMargin ?? 0) - 1e-9) {
    const entries = out.plans.filter((p) => p.side === 'bid' && !p.reduceOnly);
    if (entries.length) {
      out.plans = out.plans.filter((p) => !entries.includes(p));
      out.notes.push(`match ${pct(high)} done (its last ${pct(endFrac)} from ${pct(1 - endFrac)}): no new entry (${entries.map((p) => p.leg).join(', ')}), it could not be held to settlement unless in profit`);
    }
  }
  for (const m of s.markets) {
    const floor = mode === 'off' ? undefined : r.floors?.floor(m.ticker, Math.max(0, m.position));
    if (!(m.position > 0)) { t.rides.delete(m.ticker); continue; }
    const net = m.netAtBid;
    const others = (p: TennisPlan) => p.ticker !== m.ticker || p.side !== 'ask';
    const ride = t.rides.get(m.ticker);
    const riding = frac > 0 && net !== undefined && net > 1e-9 && (lastShare || high >= 1 - frac - 1e-9 || ride !== undefined);
    if (!riding && net === undefined && ride !== undefined) {
      // No usable bid this tick (a reconnect, a stale or crossed book, a feed-lag halt): the profit is unknown, so the ride
      // and its best stand, and nothing is sold (every sale needs a bid).
      out.plans = out.plans.filter(others);
      out.notes.push(`${m.ticker}: riding to settlement, no usable bid this tick: held, its best win chance kept`);
      continue;
    }
    if (!riding) t.rides.delete(m.ticker);
    const cutLine = tennisLoserCutAt(r, high);
    if (riding) {
      // In profit in the last share: rides to settlement, unless our player's win chance turns while it is still in profit.
      // Each reading keeps its own best, so a score arriving mid-ride (a different estimate) is not taken for a turn.
      const w = (r.probTurn ?? 0) > 0 ? t.winChance(s.markets, m.ticker, s.now) : undefined;
      const best = { ...ride };
      if (w?.score !== undefined) best.score = Math.max(best.score ?? w.score, w.score);
      if (w?.market !== undefined) best.market = Math.max(best.market ?? w.market, w.market);
      t.rides.set(m.ticker, best);
      const turns = (['score', 'market'] as const)
        .map((k) => ({ k, p: w?.[k], b: best[k] }))
        .filter((x): x is { k: 'score' | 'market'; p: number; b: number } => x.p !== undefined && x.b !== undefined && x.b - x.p >= r.probTurn! - 1e-9)
        .sort((x, y) => (y.b - y.p) - (x.b - x.p));
      const read = (['score', 'market'] as const).filter((k) => w?.[k] !== undefined).map((k) => `${pct(w![k]!)} by the ${k} (best ${pct(best[k]!)})`).join(', ');
      out.plans = out.plans.filter(others);
      if (turns.length && m.quote.bid !== undefined) {
        const bid = m.quote.bid, x = turns[0];
        t.turnSold.add(m.ticker);
        out.plans.push({ ticker: m.ticker, side: 'ask', price: bid, count: m.position, postOnly: false, reduceOnly: true, timeInForce: 'immediate_or_cancel', leg: 'prob_turn',
          why: `riding in profit (match ${at}), win chance ${pct(x.p)} by the ${x.k}, down ${((x.b - x.p) * 100).toFixed(1)} points from ${pct(x.b)}: selling +$${net!.toFixed(2)} after fees at bid ${bid}` });
      } else out.notes.push(`${m.ticker}: match ${at} (its last ${pct(frac)}), +$${net!.toFixed(2)} after fees: riding to settlement${read ? `, win chance ${read}` : ''}`);
    } else if (cutShare && r.endLoserCut && net !== undefined && !(net > 1e-9) && m.quote.bid !== undefined) {
      // Not in profit after fees: never held to settlement. A thin bid takes what it can and the rest is judged next tick.
      const bid = m.quote.bid;
      out.plans = out.plans.filter(others);
      out.plans.push({ ticker: m.ticker, side: 'ask', price: bid, count: m.position, postOnly: false, reduceOnly: true, timeInForce: 'immediate_or_cancel', leg: 'end_cut',
        why: `match ${at} (its last ${pct(endFrac)}), ${net < 0 ? '-' : '+'}$${Math.abs(net).toFixed(2)} after fees at bid ${bid}: not in profit, not held to settlement` });
    } else if (cutLine > 0 && !(net !== undefined && net > 1e-9) && m.avgEntry !== undefined && m.quote.bid !== undefined && m.quote.bid <= m.avgEntry - cutLine + 1e-9) {
      // The loser cut: its line narrows as the match goes on (wide at the start, loserCut at 60%, loserCutLate from 85%).
      const bid = m.quote.bid;
      out.plans = out.plans.filter(others);
      out.plans.push({ ticker: m.ticker, side: 'ask', price: bid, count: m.position, postOnly: false, reduceOnly: true, timeInForce: 'immediate_or_cancel', leg: 'loser_cut',
        why: `loser cut: bid ${bid} is ${((m.avgEntry - bid) * 100).toFixed(1)}c under the ${round(m.avgEntry, 4)} entry, the cut is ${(cutLine * 100).toFixed(1)}c at match ${at}${net !== undefined ? ` (${net < 0 ? '-' : '+'}$${Math.abs(net).toFixed(2)} after fees)` : ''}` });
    } else if (r.pacerUsd !== undefined && net !== undefined && m.quote.bid !== undefined) {
      const bid = m.quote.bid;
      const selling = out.plans.some((p) => p.ticker === m.ticker && p.side === 'ask' && p.timeInForce === 'immediate_or_cancel');
      const higher = mode === 'off' || selling ? undefined : tennisHigher(t, m, out.plans, bid, mode, tick);
      const unit = tick * m.position;
      const call = quotaCall(net, r.pacerUsd, floor, higher, (r.floorTicks ?? 0) * unit, unit);
      if (call.arm !== undefined) {
        r.floors?.arm(m.ticker, m.position, call.arm);
        out.notes.push(`${m.ticker}: quota floor: +$${net.toFixed(2)} net covers the $${call.arm.toFixed(2)} the hour needs; held for ${higher}, sold if the profit falls below its floor`);
      }
      if (call.sell) {
        out.plans = out.plans.filter(others);
        out.plans.push({ ticker: m.ticker, side: 'ask', price: bid, count: m.position, postOnly: false, reduceOnly: true, timeInForce: 'immediate_or_cancel', leg: 'quota_snipe',
          why: call.sell === 'floor' ? `${net < 0 ? '-' : '+'}$${Math.abs(net).toFixed(2)} net on ${m.position} at bid ${bid} fell below its $${floor!.toFixed(2)} floor` : `+$${net.toFixed(2)} net on ${m.position} at bid ${bid} covers the $${r.pacerUsd.toFixed(2)} the hour needs` });
      }
    }
  }
  return out;
}

/** PACER_FLOOR on tennis: why a leg aims higher than the quota for this held market (undefined: none). A set price below the
 *  payout: a resting take-profit above the bid, or a trail's start the bid has not reached; riding mode adds a trail hunting
 *  with its stop. The favorite held for settlement does not aim higher. */
function tennisHigher(t: MatchTracker, m: MatchMarket, plans: TennisPlan[], bid: number, mode: PacerFloorMode, tick: number): string | undefined {
  const set = (px: number | undefined) => px !== undefined && px > bid + 1e-9 && px <= 1 - tick + 1e-9;
  const tp = plans.find((p) => p.ticker === m.ticker && p.side === 'ask' && p.postOnly && set(p.price));
  if (tp) return `the take-profit resting at ${tp.price.toFixed(2)}`;
  const start = t.trailStart.get(m.ticker);
  if (!t.armed.has(m.ticker) && set(start)) return `the trail starting at ${start!.toFixed(2)}`;
  if (mode === 'riding' && t.armed.has(m.ticker)) return `the trail riding its stop ${t.stops.get(m.ticker)?.toFixed(2) ?? ''}`.trim();
  return undefined;
}

function decideLegs(t: MatchTracker, s: MatchSnapshot, cfg: TennisConfig, budget: BudgetView, tick: number): { phase: MatchPhase; plans: TennisPlan[]; notes: string[] } {
  const phase = t.observe(s);
  const plans: TennisPlan[] = [];
  const notes: string[] = [];
  const pA = MatchTracker.probability(s.markets);
  if (pA === undefined || s.markets.length === 0) return { phase, plans, notes: ['no two-sided book'] };

  // Map "side" -> market to buy YES on (use the player's own market when listed).
  const marketFor = (side: 'a' | 'b'): MatchMarket | undefined => (side === 'a' ? s.markets[0] : s.markets[1]);
  const pSide = (side: 'a' | 'b') => (side === 'a' ? pA : 1 - pA);
  const held = s.markets.filter((m) => m.position > 0);

  // A flat market has no trail (a later leg on the same player starts a fresh one).
  for (const m of s.markets) if (m.position <= 0) { t.armed.delete(m.ticker); t.ratchets.delete(m.ticker); t.stops.delete(m.ticker); t.armedAt.delete(m.ticker); t.peak.delete(m.ticker); t.signals.delete(m.ticker); t.trailStart.delete(m.ticker); }

  // After a restart the tracker is fresh: a held position bought cheap is the underdog trade.
  if (!t.underdogTicker && !t.underdogEntered && !t.favEntered && held.length) {
    const h = held[0];
    if ((h.avgEntry ?? 1) <= cfg.underdogMax + 0.05) t.underdogTicker = h.ticker;
  }

  // ---- Open underdog position: take-profit (and optional stop) ------------------
  const ud = t.underdogTicker ? s.markets.find((m) => m.ticker === t.underdogTicker) : undefined;
  if (ud && ud.position > 0 && !t.underdogClosed) {
    t.underdogEntered = true;
    const entry = ud.avgEntry ?? ud.quote.bid ?? 0;
    const target = Math.min(0.99, Math.max(entry + cfg.takeProfitCents, entry * (1 + cfg.takeProfitPct)));
    const tpPx = floorToTick(target + tick - 1e-9, tick); // target rounded up to the tick
    const prog = t.progress(s.now, s.markets);
    const other = s.markets.find((x) => x.ticker !== ud.ticker);
    if (cfg.underdogCutProgress > 0 && prog >= cfg.underdogCutProgress && ud.quote.bid !== undefined) {
      // Underdogs usually lose late: salvage what the position is still worth.
      plans.push({ ticker: ud.ticker, side: 'ask', price: ud.quote.bid, count: ud.position, postOnly: false, reduceOnly: true, timeInForce: 'immediate_or_cancel', leg: 'underdog_cut', why: `match ${(prog * 100).toFixed(0)}% done: underdogs usually lose late, selling at ${ud.quote.bid}` });
      return { phase, plans, notes };
    }
    if (prog >= cfg.underdogLateProgress && ud.quote.bid !== undefined && ud.quote.bid >= profitFloor(ud, entry, tick) - 1e-9) {
      // Past the early phase: no more hunting, take the next available exit in profit after fees.
      const px = nextFillableExit(ud, profitFloor(ud, entry, tick));
      if (px !== undefined) {
        plans.push({ ticker: ud.ticker, side: 'ask', price: round(px, 4), count: ud.position, postOnly: false, reduceOnly: true, timeInForce: 'immediate_or_cancel', leg: 'underdog_late', why: `match ${(prog * 100).toFixed(0)}% done: taking the profit while the underdog is still ahead` });
        return { phase, plans, notes };
      }
    }
    if (cfg.trail) {
      // Ratcheting trail from the target: no fixed exit; the stop starts at the target and climbs
      // to order-book walls the price moves past.
      plans.push(...huntExit(t, ud, other, entry, tpPx, s.now, cfg, tick, 'underdog_trail', notes));
    } else if (ud.quote.bid !== undefined && ud.quote.bid >= tpPx - 1e-9) {
      // The bounce already went past the target: take the profit at the bid now.
      plans.push({ ticker: ud.ticker, side: 'ask', price: ud.quote.bid, count: ud.position, postOnly: false, reduceOnly: true, timeInForce: 'immediate_or_cancel', leg: 'underdog_tp', why: `underdog bid ${ud.quote.bid} >= take-profit ${round(tpPx, 2)} (entry ${round(entry, 3)})` });
    } else {
      plans.push({ ticker: ud.ticker, side: 'ask', price: round(tpPx, 4), count: ud.position, postOnly: true, reduceOnly: false, timeInForce: 'good_till_canceled', leg: 'underdog_tp', why: `underdog take-profit ${round(tpPx, 2)} (entry ${round(entry, 3)})` });
    }
    if (cfg.underdogStopCents > 0 && ud.quote.bid !== undefined && ud.quote.bid <= entry - cfg.underdogStopCents) {
      plans.length = 0;
      plans.push({ ticker: ud.ticker, side: 'ask', price: ud.quote.bid, count: ud.position, postOnly: false, reduceOnly: true, timeInForce: 'immediate_or_cancel', leg: 'underdog_stop', why: `underdog stop ${ud.quote.bid}` });
    }
    return { phase, plans, notes };
  }
  if (t.underdogEntered && (!ud || ud.position <= 0)) t.underdogClosed = true;

  // ---- Underdog entry ---------------------------------------------------------
  if (phase === 'underdog_window' && !t.underdogEntered && held.length === 0) {
    const side: 'a' | 'b' = pA < 0.5 ? 'a' : 'b';
    const pU = pSide(side);
    const m = marketFor(side);
    if (pU > cfg.underdogMax) notes.push(`not skewed enough: underdog ${pU.toFixed(2)} > ${cfg.underdogMax}`);
    else if (pU < cfg.underdogMin) notes.push(`underdog ${pU.toFixed(2)} below ${cfg.underdogMin}: too long a shot`);
    else if (!m) notes.push('underdog market not listed');
    else {
      // Entry confirmation: the tennis confluence must be leaning toward the underdog.
      const pre = t.liveSince === undefined;
      const sig = tennisConfluence(t, m, s.markets.find((x) => x.ticker !== m.ticker), s.now, cfg);
      t.signals.set(m.ticker, sig);
      const need = pre ? cfg.entryMinSignalsPre : cfg.entryMinSignalsLive;
      // Early is what matters: full size before the start and in the first minutes, tapering after.
      const minIn = pre ? 0 : (s.now - t.liveSince!) / 60_000;
      const span = Math.max(1e-9, cfg.entryWindowMin - cfg.earlyFullSizeMin);
      const early = minIn <= cfg.earlyFullSizeMin ? 1 : Math.max(0.5, 1 - (0.5 * (minIn - cfg.earlyFullSizeMin)) / span);
      const px = makerBid(m.quote, tick, cfg.maxSpread);
      const n = px ? Math.floor(tennisSize(px, cfg, budget) * early * 100) / 100 : 0;
      const fairNo = px ? fairBlocks(s, m, px, cfg) : undefined;
      if (sig.score < need) notes.push(`underdog entry waits for confluence: ${sig.score}/4 < ${need} (${pre ? 'pre-match' : 'live'})`);
      else if (!px) notes.push('underdog book too wide or one-sided');
      else if (n <= 0) notes.push('tennis budget exhausted');
      else if (fairNo) notes.push(`underdog entry skipped: ${fairNo}`);
      else {
        t.underdogTicker = m.ticker;
        plans.push({ ticker: m.ticker, side: 'bid', price: px, count: n, postOnly: true, reduceOnly: false, timeInForce: 'good_till_canceled', leg: 'underdog_entry', why: `underdog ${pU.toFixed(2)} vs favorite ${(1 - pU).toFixed(2)}, confluence ${sig.score}/4, ${pre ? 'pre-match' : `${minIn.toFixed(0)} min in`}${early < 1 ? `, size x${early.toFixed(2)}` : ''}` });
      }
    }
    return { phase, plans, notes };
  }

  // ---- Favorite: open position (optional stop) ----------------------------------
  // Any position held after the underdog trade is closed is the favorite trade (possibly on the
  // same player, if the underdog became the leader).
  const fav = held.find((m) => t.underdogClosed || m.ticker !== t.underdogTicker);
  if (fav) {
    t.favEntered = true;
    if (cfg.favStopCents > 0 && fav.avgEntry !== undefined && fav.quote.bid !== undefined && fav.quote.bid <= fav.avgEntry - cfg.favStopCents && !t.armed.has(fav.ticker)) {
      plans.push({ ticker: fav.ticker, side: 'ask', price: fav.quote.bid, count: fav.position, postOnly: false, reduceOnly: true, timeInForce: 'immediate_or_cancel', leg: 'fav_stop', why: `favorite stop ${fav.quote.bid}` });
    } else if (cfg.trail && fav.avgEntry !== undefined) {
      const target = floorToTick(Math.min(cfg.favTrailCap, fav.avgEntry + cfg.favTrailCents) + tick - 1e-9, tick);
      plans.push(...huntExit(t, fav, s.markets.find((x) => x.ticker !== fav.ticker), fav.avgEntry, target, s.now, cfg, tick, 'fav_trail', notes));
    }
    return { phase, plans, notes };
  }

  // ---- Favorite re-entry after half the match ------------------------------------
  if (phase === 'late' && !t.favEntered && held.length === 0) {
    const side: 'a' | 'b' = pA >= 0.5 ? 'a' : 'b';
    const pL = pSide(side);
    const m = marketFor(side);
    const chg = t.change(side, s.now);
    if (pL < cfg.favMin || pL > cfg.favMax) notes.push(`leader ${pL.toFixed(2)} outside [${cfg.favMin}, ${cfg.favMax}]`);
    else if (chg === undefined) notes.push('leader stability unknown (need 5 min of prices)');
    else if (chg < -cfg.favStableCents) notes.push(`leader slipping ${(chg * 100).toFixed(1)}c over 5 min`);
    else if (!m) notes.push('leader market not listed');
    else {
      const sig = tennisConfluence(t, m, s.markets.find((x) => x.ticker !== m.ticker), s.now, cfg);
      t.signals.set(m.ticker, sig);
      const px = makerBid(m.quote, tick, cfg.maxSpread);
      const n = px ? tennisSize(px, cfg, budget) : 0;
      const fairNo = px ? fairBlocks(s, m, px, cfg) : undefined;
      if (sig.score < cfg.favEntryMinSignals) notes.push(`favorite entry waits for confluence: ${sig.score}/4 < ${cfg.favEntryMinSignals}`);
      else if (!px) notes.push('leader book too wide or one-sided');
      else if (n <= 0) notes.push('tennis budget exhausted');
      else if (fairNo) notes.push(`favorite entry skipped: ${fairNo}`);
      else plans.push({ ticker: m.ticker, side: 'bid', price: px, count: n, postOnly: true, reduceOnly: false, timeInForce: 'good_till_canceled', leg: 'fav_entry', why: `leader ${pL.toFixed(2)} at ${(t.progress(s.now, s.markets) * 100).toFixed(0)}% of the match` });
    }
  }
  return { phase, plans, notes };
}
