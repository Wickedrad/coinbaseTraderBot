// One profit ratchet for every position (Steven, Nov 11 2026). 8:53 AM EST / 13:53 UTC: "the ratchet should allow for the
// profit after fees price to go higher if it runs past the $1.50 profit and ratchet stop loss after that"; 8:58 AM EST / 13:58
// UTC: trail $0.50. The design he accepted:
//   net     the trade's profit after fees, in dollars: what partial sales of the position banked since it opened plus the rest
//           sold at the held side's bid now after the entry fee and the taker exit fee (tradeNetAtBid, the hold exit's measure;
//           the answer given to Steven, Nov 11 9:10 AM EST / 14:10 UTC: a thin bid that took part of the position is no drop)
//   arm     net >= RATCHET_ARM_USD ($1.50): best = net, stop = max(RATCHET_STOP_MIN_USD $1.00, best - RATCHET_TRAIL_USD $0.50)
//   raise   each evaluation after: best = max(best, net), stop = max(stop, $1.00, best - $0.50). Never lowered (asserted), and
//           never under $0, the fee break-even (net is after both fees)
//   sell    net <= stop: the whole position, reduce-only, immediate-or-cancel; once decided the sale goes on until flat
// The 10 s hold exit (bot/strategy/holdExit.ts) stands aside while the ratchet is armed and the profit set a new best in the
// last HOLD_EXIT_RUN_SEC (3 s), so a runner rides the ratchet; a sitter is still sold by the hold exit. The quota snipe and the
// quota floor (PACER_FLOOR) are unchanged: two stops, whichever triggers first sells.
// This file is the core: ratchetStep is pure and both sales run it. A plan position's (bot/plan/planRatchet.ts, PLAN_RULES)
// adds the plan's own sale (the bid less 2 ticks, retries, the 3-failure alert, gaps, the minute clock) and its end rule. Any
// other position's goes through decide() with the quota snipe's order (bot/strategy/fairValueStrategy.ts), on the state kept
// here by ProfitRatchets, in memory as the quota floors are. The engine (paper and live alike) and the replay
// (research/backtest.ts) run the same code.

export interface RatchetSettings {
  /** RATCHET_ARM_USD (1.50): the profit after fees, whole position, that arms the ratchet. */
  armUsd: number;
  /** RATCHET_STOP_MIN_USD (1.00): the stop's lowest level once armed. */
  stopMinUsd: number;
  /** RATCHET_TRAIL_USD (0.50): how far under the best profit since arming the stop trails. */
  trailUsd: number;
}

export interface RatchetConfig extends RatchetSettings {
  /** RATCHET (default true): every position that is not a plan position has the ratchet. Off: none has (plan positions keep
   *  the plan's, which PLAN_RULES runs), and the hold exit never stands aside. */
  enabled: boolean;
}

export interface RatchetState {
  armed: boolean;
  armedAt?: number;
  /** Best net since arming, dollars. */
  best?: number;
  /** The stop, dollars: never lowered. */
  stop?: number;
}

export interface RatchetStep {
  state: RatchetState;
  /** 'arm': armed on this evaluation; 'raise': the stop went up. */
  event?: 'arm' | 'raise';
  prevStop?: number;
  /** Armed and the net at or under the stop. */
  sell: boolean;
}

const EPS = 1e-9;
const r4 = (x: number) => Math.round(x * 1e4) / 1e4;

/** The stop for a best net: the trail under it, never under the stop's minimum nor under the fee break-even. `breakEvenUsd`:
 *  the smallest net at or above $0 the position can sell for on the price grid (the plan passes the net at its fee floor price,
 *  so a stop held at break-even sells on that tick, not a tick under it); $0 when not given. */
export function ratchetStopFor(best: number, s: RatchetSettings, breakEvenUsd = 0): number {
  return r4(Math.max(s.stopMinUsd, best - s.trailUsd, breakEvenUsd, 0));
}

/** The stop is never lowered: throws if a computation would. */
export function assertStopNotLowered(prev: number | undefined, next: number | undefined): void {
  if (prev !== undefined && (next === undefined || next < prev - EPS)) throw new Error(`profit ratchet: stop lowered from ${prev} to ${next}`);
}

/** One evaluation of the ratchet on the position's net (dollars, whole position, after both fees). The input state is not
 *  changed; the returned one replaces it. `breakEvenUsd`: see ratchetStopFor. */
export function ratchetStep(state: RatchetState, netUsd: number, s: RatchetSettings, now: number, breakEvenUsd = 0): RatchetStep {
  const st: RatchetState = { ...state };
  const out: RatchetStep = { state: st, sell: false };
  if (!st.armed) {
    if (netUsd >= s.armUsd - EPS) {
      st.armed = true;
      st.armedAt = now;
      st.best = r4(netUsd);
      st.stop = ratchetStopFor(netUsd, s, breakEvenUsd);
      out.event = 'arm';
    }
  } else {
    const prev = st.stop;
    st.best = r4(Math.max(st.best ?? netUsd, netUsd));
    const next = r4(Math.max(prev ?? -Infinity, ratchetStopFor(st.best, s, breakEvenUsd)));
    assertStopNotLowered(prev, next);
    st.stop = next;
    if (prev === undefined || next > prev + EPS) { out.event = 'raise'; out.prevStop = prev; }
  }
  out.sell = st.armed && st.stop !== undefined && netUsd <= st.stop + EPS;
  return out;
}

/** What decide() reads (opts.ratchet) for a position that is not a plan position. */
export interface RatchetReading {
  armed: boolean;
  best?: number;
  stop?: number;
  /** Sell the position: the net reached the stop on this evaluation, or did on an earlier one and the position is not flat yet. */
  sell: boolean;
  /** The sale was decided on an earlier evaluation; this is what is left. */
  rest?: boolean;
  /** Armed or raised on this evaluation (the engine audits an arm). */
  event?: 'arm' | 'raise';
  prevStop?: number;
}

interface Track { sign: number; lastTs: number; state: RatchetState; selling: boolean }

/** The ratchet of each held position that is not a plan position, by market. A position that goes flat or changes side starts
 *  from nothing, also when no evaluation saw it flat (onFill). In memory: after a restart it arms again from the next profit it
 *  sees, as the quota floors do. */
export class ProfitRatchets {
  private readonly tracks = new Map<string, Track>();

  constructor(readonly cfg: RatchetSettings) {}

  /** Records the trade's net (`netUsd`, tradeNetAtBid; undefined: no bid, nothing is decided) at `now` and says whether it
   *  sells. */
  step(ticker: string, position: number, netUsd: number | undefined, now: number): RatchetReading {
    if (!(Math.abs(position) > EPS)) {
      this.tracks.delete(ticker);
      return { armed: false, sell: false };
    }
    const sign = Math.sign(position);
    let t = this.tracks.get(ticker);
    if (!t || t.sign !== sign) {
      t = { sign, lastTs: -Infinity, state: { armed: false }, selling: false };
      this.tracks.set(ticker, t);
    }
    const read = (fresh?: RatchetStep): RatchetReading => {
      const x = t!.state;
      return {
        armed: x.armed, ...(x.best !== undefined ? { best: x.best } : {}), ...(x.stop !== undefined ? { stop: x.stop } : {}), sell: t!.selling,
        ...(t!.selling && !fresh?.sell ? { rest: true } : {}),
        ...(fresh?.event ? { event: fresh.event } : {}), ...(fresh?.prevStop !== undefined ? { prevStop: fresh.prevStop } : {}),
      };
    };
    // An evaluation older than the last one (overlapping ticks under the kill switch) changes nothing; no bid decides nothing.
    if (now < t.lastTs || netUsd === undefined || !Number.isFinite(netUsd)) return read();
    t.lastTs = now;
    if (t.selling) return read();
    const r = ratchetStep(t.state, netUsd, this.cfg, now);
    t.state = r.state;
    if (r.sell) t.selling = true;
    return read(r);
  }

  /** A fill moved the position from `before` to `after`: flat or on the other side, the next position starts from nothing. */
  onFill(ticker: string, before: number, after: number): void {
    if (!(Math.abs(after) > EPS) || Math.sign(after) !== Math.sign(before)) this.tracks.delete(ticker);
  }

  /** The market settled, is no longer watched, or its position became a plan position. */
  forget(ticker: string): void {
    this.tracks.delete(ticker);
  }
}
