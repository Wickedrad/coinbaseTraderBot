// Steven's hold exit (Nov 11 2026, 13:42-13:45 UTC): "once it's $1.50 after profit it should count seconds it is in profit and
// exit after it remains there for 10 seconds. it can reenter if there is still more than 50% of the window time left and it
// has a signal on the same contract. The Snipe is just an immediate exit once it hits it." Then: "10 seconds cumulatively, not
// consecutively, though as an exit rule it should also have 5 seconds consecutively in +$1 profit after fees", "both must be
// true together", "and 3 instead of 5 seconds".
//
// One rule, two conditions true together at the moment of sale, both on the trade's profit after the entry fee and the exit
// fee at the bid (the quota snipe's measure, netProfitAtBid in bot/strategy/fairValueStrategy.ts, plus what partial sales
// banked: see "The trade" below):
//   total   at least HOLD_EXIT_SEC (10) seconds in all at or above HOLD_EXIT_USD ($1.50); a dip below does not reset it
//   run     the last HOLD_EXIT_RUN_SEC (3) seconds or more in a row at or above HOLD_EXIT_RUN_USD ($1.00), up to now
// The sale is the quota snipe's: the whole position at the bid, where and when the snipe could sell (decide()). The snipe is
// unchanged; whichever fires first sells. Nothing else goes out with either sale, and the market's resting quotes are pulled
// (bot/engine.ts liquidate). Once the rule has sold part of the position (a thin bid), the rest is sold at the next bids while
// the trade is not at a loss after fees: the rule decided to exit the whole position.
// Time comes from the evaluations' timestamps, never from counting ticks: a stretch between two evaluations counts toward the
// total only when both were at the level and it is at most HOLD_EXIT_MAX_GAP_MS long (plus HOLD_EXIT_JOIN_SLACK_MS for timer
// jitter: a market skipped one tick as busy is sampled a little over 2 s later), and then at most 2 s of it. A longer gap (a
// data gap, a stalled loop) counts nothing and restarts the run; an evaluation older than the last one changes nothing. No
// profit measure (no bid) is not in profit. A position that goes flat or changes side starts from nothing, also when no
// evaluation saw it flat (onFill). The count is kept in memory: after a restart it starts again.
// Re-entry: after a hold exit or a quota snipe sold on a contract (marked on the sale's fill), a new entry there opens only
// while more than HOLD_EXIT_REENTRY_SHARE (half) of the contract's window (open to close) is left, and only on the bot's
// normal entry signal. A profit ratchet sale alone marks nothing (the rule names these two). The marks are saved
// (hold_exit_state.json beside the pacer's state) and kept until the market closes.
// Tennis is not covered: its snipe (bot/tennis/tennisStrategy.ts) marks nothing and its entries are not limited, since a
// match contract's open-to-close times say nothing about how much of the match is left; that is for Steven to settle.
// Plan positions too (Steven, Nov 11 8:52 AM EST / 13:52 UTC): the hold exit sells a plan position (PLAN_RULES) as any other;
// whichever of it and the plan's ratchet or end rule fires first sells.
// A runner rides the ratchet (Steven, Nov 11 8:53-8:58 AM EST / 13:53-13:58 UTC; bot/strategy/profitRatchet.ts): while the
// position's ratchet is armed and its profit set a new best in the last HOLD_EXIT_RUN_SEC (3 s), the hold exit stands aside;
// the ratchet's stop, $0.50 under the best, sells it on the way down. A position sitting near $1.50 sets no new best and is
// sold at 10 s as before. With no ratchet armed (RATCHET=false, or not yet armed) nothing stands aside. The best is the
// highest profit any evaluation of the position saw, on the same timestamps.
// The trade, not the rest (the answer given to Steven, Nov 11 9:10 AM EST / 14:10 UTC): the profit sampled is what partial
// sales of the position banked since it opened plus the rest at the bid (tradeNetAtBid, bot/strategy/fairValueStrategy.ts), so
// a thin bid that took part of the position (on any exit) is not a drop, and the rest is not left under a $1.50 bar meant for
// the whole position.
// Failed tries (Steven's idea, Nov 11 9:15 AM EST / 14:15 UTC, and his card at 9:21 AM EST / 14:21 UTC): a try starts when the
// trade's profit reaches HOLD_EXIT_RUN_USD ($1.00) and ends once it has stayed under it for HOLD_EXIT_RUN_SEC (3 s) in a row;
// it failed when it never touched HOLD_EXIT_USD ($1.50) on the way. Back at $1.00 within the 3 s, the same try goes on; the
// next rise to $1.00 after a try ended starts a new one. Same clock and joins as the count above (a gap restarts the 3 s, no
// profit measure is under $1.00). After HOLD_EXIT_LINE_AFTER_FAILS (5) failed tries on the position, the line exit (the exit
// curve's cross, bot/engine.ts) may sell it with SINUOUS_CROSS off, on its own conditions: its last resort. 0 turns that off.
// Not a plan position: the curve neither holds nor sells one (its tries are counted all the same).
// The engine (paper and live alike) and the replay (research/backtest.ts) run this class on their own clocks.

import fs from 'fs';
import path from 'path';

export interface HoldExitConfig {
  /** HOLD_EXIT: the hold exit and its re-entry rule are on. */
  enabled: boolean;
  /** HOLD_EXIT_USD (1.50) and HOLD_EXIT_SEC (10): the profit after fees, and the seconds in all at or above it. */
  usd: number;
  sec: number;
  /** HOLD_EXIT_RUN_USD (1.00) and HOLD_EXIT_RUN_SEC (3): the profit after fees, and the seconds in a row at or above it. */
  runUsd: number;
  runSec: number;
  /** HOLD_EXIT_REENTRY_SHARE (0.5): after a hold exit or a quota snipe, an entry on the same contract only while more than this
   *  share of its window is left. 0 = no limit. */
  reentryShare: number;
  /** HOLD_EXIT_LINE_AFTER_FAILS (5): after this many failed tries on a position the line exit may sell it as a last resort,
   *  SINUOUS_CROSS off or not. 0 = never. The tries are counted only with `enabled`: HOLD_EXIT=false restores the behaviour
   *  before the hold exit, the last resort off as well. */
  lineAfterFails: number;
}

/** The longest stretch between two evaluations that counts as time in profit (one evaluation a second, with room for a slow one). */
export const HOLD_EXIT_MAX_GAP_MS = 2000;
/** Timer jitter on top of it: two 1 s ticks plus event-loop lag still join (at most 2 s of the stretch is counted). */
export const HOLD_EXIT_JOIN_SLACK_MS = 500;

export interface HoldReading {
  /** Sell the position: both conditions hold now, or the rule already sold part of it and the rest is not at a loss. */
  fire: boolean;
  /** Seconds in all at or above `usd` since the position was opened, and of the current run at or above `runUsd`. */
  cumSec: number;
  runSec: number;
  /** The rule sold part of the position; this is the rest. */
  rest?: boolean;
  /** Both conditions are met but the profit is still climbing under an armed ratchet: the hold exit stands aside. */
  climbing?: boolean;
  /** Failed tries on this position so far (set once there is one): reached $1.00, back under it for 3 s, never $1.50. */
  fails?: number;
}

const EPS = 1e-9;

interface Track {
  sign: number; lastTs: number; lastNet: number | undefined; cumMs: number; runFrom: number | undefined;
  /** The best profit seen and when it was last raised. */
  best: number | undefined; bestAt: number;
  /** The rule's sale filled part of the position: the rest is sold too. */
  selling: boolean;
  /** The try under way (undefined: none): whether it touched `usd`, and since when it has been under `runUsd`. */
  attempt: { touched: boolean; underFrom: number | undefined } | undefined;
  fails: number;
}

export class HoldExits {
  private readonly tracks = new Map<string, Track>();
  /** Contracts a hold exit or a quota snipe has sold, with their markets' close (ms): the re-entry rule applies to them. */
  private readonly sold = new Map<string, number>();

  /** `file`: where the re-entry marks are saved (undefined: memory only, as in the replay); `now` drops marks of closed markets. */
  constructor(readonly cfg: HoldExitConfig, private readonly file?: string, now = Date.now(), private readonly maxGapMs = HOLD_EXIT_MAX_GAP_MS) {
    this.load(now);
  }

  /** Records the trade's profit after fees (`netUsd`: banked by partial sales plus the rest at its bid, tradeNetAtBid;
   *  undefined: none) at `now` (ms) and says whether it sells. `ratchetArmed`: the position's profit ratchet is armed, so the
   *  hold exit stands aside while the profit is still climbing. */
  sample(ticker: string, position: number, netUsd: number | undefined, now: number, ratchetArmed = false): HoldReading {
    if (!(Math.abs(position) > EPS)) {
      this.tracks.delete(ticker);
      return { fire: false, cumSec: 0, runSec: 0 };
    }
    const sign = Math.sign(position);
    let t = this.tracks.get(ticker);
    if (!t || t.sign !== sign) {
      t = { sign, lastTs: -Infinity, lastNet: undefined, cumMs: 0, runFrom: undefined, best: undefined, bestAt: -Infinity, selling: false, attempt: undefined, fails: 0 };
      this.tracks.set(ticker, t);
    }
    // An evaluation older than the last one (overlapping ticks under the kill switch) adds nothing and sells nothing: the newer
    // one already judged the position.
    if (now < t.lastTs) return { fire: false, cumSec: t.cumMs / 1000, runSec: t.runFrom === undefined ? 0 : (t.lastTs - t.runFrom) / 1000, ...(t.fails ? { fails: t.fails } : {}) };
    const net = netUsd !== undefined && Number.isFinite(netUsd) ? netUsd : undefined;
    const at = (x: number | undefined, usd: number) => x !== undefined && x >= usd - EPS;
    const dt = now - t.lastTs;
    const joined = dt <= this.maxGapMs + HOLD_EXIT_JOIN_SLACK_MS;
    if (joined && at(t.lastNet, this.cfg.usd) && at(net, this.cfg.usd)) t.cumMs += Math.min(dt, this.maxGapMs);
    if (!at(net, this.cfg.runUsd)) t.runFrom = undefined;
    else if (t.runFrom === undefined || !joined) t.runFrom = now;
    // Failed tries: a try runs from the rise to runUsd until 3 s in a row under it (runSec), and fails unless it touched usd.
    if (at(net, this.cfg.runUsd)) {
      t.attempt ??= { touched: false, underFrom: undefined };
      t.attempt.underFrom = undefined;
      if (at(net, this.cfg.usd)) t.attempt.touched = true;
    } else if (t.attempt) {
      if (t.attempt.underFrom === undefined || !joined) t.attempt.underFrom = now;
      if (now - t.attempt.underFrom >= this.cfg.runSec * 1000 - EPS) {
        if (!t.attempt.touched) t.fails++;
        t.attempt = undefined;
      }
    }
    t.lastTs = now;
    t.lastNet = net;
    if (net !== undefined && (t.best === undefined || net > t.best + EPS)) { t.best = net; t.bestAt = now; }
    const runMs = t.runFrom === undefined ? 0 : now - t.runFrom;
    const met = t.runFrom !== undefined && t.cumMs >= this.cfg.sec * 1000 - EPS && runMs >= this.cfg.runSec * 1000 - EPS;
    // A new best within the last HOLD_EXIT_RUN_SEC under an armed ratchet: the runner rides the ratchet. Once the rule has sold
    // part of the position, the rest is not held back.
    const climbing = met && !t.selling && ratchetArmed && now - t.bestAt < this.cfg.runSec * 1000 - EPS;
    const rest = !met && t.selling && at(net, 0);
    return { fire: (met && !climbing) || rest, cumSec: t.cumMs / 1000, runSec: runMs / 1000, ...(rest ? { rest: true } : {}), ...(climbing ? { climbing: true } : {}), ...(t.fails ? { fails: t.fails } : {}) };
  }

  /** A fill moved the position from `before` to `after`: flat or on the other side, the next position starts from nothing
   *  (a same-side position reopened between two evaluations must not inherit the old one's seconds). */
  onFill(ticker: string, before: number, after: number): void {
    if (!(Math.abs(after) > EPS) || Math.sign(after) !== Math.sign(before)) this.tracks.delete(ticker);
  }

  /** A hold exit or a quota snipe sold on this contract (a fill of its order; call onFill first), whose market closes at
   *  `closeTs` (ms). `hold`: the hold exit had fired, so what a thin bid left of the position is sold as well. */
  soldBy(ticker: string, closeTs: number, now: number, hold = false): void {
    const t = this.tracks.get(ticker);
    if (hold && t) t.selling = true;
    for (const [k, c] of this.sold) if (c <= now) this.sold.delete(k);
    this.sold.set(ticker, closeTs);
    this.save();
  }

  /** Why no entry may open on this contract now (undefined: it may): a hold exit or a quota snipe sold it, and no more than
   *  reentryShare of its window (`windowSec`, open to close) is left. */
  reentryBlock(ticker: string, tauSec: number, windowSec: number | undefined): string | undefined {
    const share = this.cfg.reentryShare;
    if (!this.cfg.enabled || !(share > 0) || !this.sold.has(ticker) || windowSec === undefined || tauSec > share * windowSec) return undefined;
    return `re-entry after a hold exit or quota snipe: ${Math.max(0, Math.round(tauSec))} s of the ${Math.round(windowSec)} s window left, not more than ${Math.round(share * 100)}%`;
  }

  /** The market is no longer watched (the engine's prune): its count goes; its re-entry mark stays until the market closes. */
  unwatch(ticker: string): void {
    this.tracks.delete(ticker);
  }

  /** The market settled or is gone. */
  forget(ticker: string): void {
    this.tracks.delete(ticker);
    if (this.sold.delete(ticker)) this.save();
  }

  private save(): void {
    if (!this.file) return;
    try {
      fs.mkdirSync(path.dirname(this.file), { recursive: true });
      fs.writeFileSync(this.file, JSON.stringify({ sold: Object.fromEntries(this.sold) }));
    } catch { /* best effort: the next mark tries again */ }
  }

  private load(now: number): void {
    if (!this.file || !fs.existsSync(this.file)) return;
    try {
      const s = JSON.parse(fs.readFileSync(this.file, 'utf8')) as { sold?: Record<string, unknown> };
      for (const [k, c] of Object.entries(s.sold ?? {})) if (typeof c === 'number' && c > now) this.sold.set(k, c);
    } catch { /* unreadable state: no marks */ }
  }
}
