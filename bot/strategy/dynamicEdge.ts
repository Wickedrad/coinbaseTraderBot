// Dynamic entry edge: the edge the bot asks for before it quotes or takes, moved with what the market is doing now
// (phase 3 of the dynamic-scaling plan, Oct 28). One function for the engine and the backtester, so a replay asks for the
// same edge the bot asked for.
//
//   minEdge = STRATEGY_MIN_EDGE + session add + clamp(sum of the parts below, -maxDown, +maxUp)
//
//   vol          k x (rv15m / rv1h - 1): volatility rising makes the price stale sooner (asks more), calming asks less
//   change       k x P(change point in the last 5 minutes): the process just changed, the model's history fits it less
//   spread       k x the median Kalshi spread: a wide book is a sign informed traders are on the other side
//   flow         k x |taker imbalance|: one-sided flow is the toxicity reading (adverse selection on fills)
//   uncertainty  k x the model's standard deviation of p: less sure, more margin
//   quiet        k x max(0, 1 - jump / quietRef): the coin is not moving. Scaling lab round 1 (Oct 31): across every arm the
//                third of trades entered after the smallest 1-hour moves (jump under ~1.6 sigma) lost and the largest
//                (over ~2.2 sigma) earned, so a quiet coin asks more edge and a moving one asks no extra
//   calm profile (Steven's dynamics rule, Nov 1-2): when the coin's 1-hour realized volatility is under calmRv1h, the
//                readings mean something else. Scaling lab round 2 (recorded Oct 29-31, Nov 2): on the wild day (rv1h ~1.5e-4)
//                tight Kalshi books and one-sided flow were where the bot earned; on the two calm days (rv1h ~3e-5) the
//                same entries lost (tight book <= 1c: -$152 and -$83; flow over ~0.07: -$122 and -$328). So in a calm
//                market the edge also asks calmTight x (1 - spread / calmTightRef) on books tighter than calmTightRef, plus
//                calmFlow x |taker imbalance| and a flat calmBias. A wild market is untouched. Live reading only (rv1h of
//                the last hour), so no lookahead; the same code in paper and live.
//
// Every k is 0 by default, so nothing changes until the sweep (research/randomSweep.ts, PBO < 0.3 and a deflated Sharpe
// on held-out days) finds settings that earn more than today's. A reading the market state does not have yet adds 0.
import type { MarketStateReading } from '../marketdata/marketState';

export interface DynamicEdgeParams {
  vol: number;
  change: number;
  spread: number;
  flow: number;
  uncertainty: number;
  quiet: number;
  /** Jump (1-hour sigmas) at or above which the quiet term adds nothing. */
  quietRef: number;
  /** Calm-market profile (0 = off): rv1h below which it applies, and its parts (see the header). */
  calmRv1h: number;
  calmTight: number;
  calmTightRef: number;
  calmFlow: number;
  calmBias: number;
  /** Multiplier on the other parts (vol .. quiet) when the coin is NOT calm (rv1h known and >= calmRv1h); 1 = unchanged.
   *  Round 3 (Nov 4, today's code): the base terms cost -$297 on the wild Oct 29 and earned on the calm days. */
  wildScale: number;
  /** Adversarial controls (research): a flat add, and a placebo that hands back a random earlier add instead of this one. */
  bias: number;
  placebo: boolean;
  /** Most the edge can rise or fall from the static one (probability points). */
  maxUp: number;
  maxDown: number;
}

export const DYNAMIC_EDGE_OFF: DynamicEdgeParams = { vol: 0, change: 0, spread: 0, flow: 0, uncertainty: 0, quiet: 0, quietRef: 2.2, calmRv1h: 0, calmTight: 0, calmTightRef: 0.015, calmFlow: 0, calmBias: 0, wildScale: 1, bias: 0, placebo: false, maxUp: 0.05, maxDown: 0.01 };

export interface DynamicEdge {
  /** What to add to minEdge (probability points). */
  add: number;
  parts: { vol: number; change: number; spread: number; flow: number; uncertainty: number; quiet: number; calm: number };
}

const v = (x: number | null | undefined) => (x === null || x === undefined || !Number.isFinite(x) ? 0 : x);

export function dynamicEdge(p: DynamicEdgeParams, r: MarketStateReading | undefined, pStd: number | undefined): DynamicEdge {
  const parts = {
    vol: p.vol && r?.volRatio != null ? p.vol * (r.volRatio - 1) : 0,
    change: p.change * v(r?.changeProb),
    spread: p.spread * v(r?.spread),
    flow: p.flow * Math.abs(v(r?.flowImbalance)),
    uncertainty: p.uncertainty * v(pStd),
    quiet: p.quiet && p.quietRef > 0 && r?.jump != null && Number.isFinite(r.jump) ? p.quiet * Math.max(0, 1 - r.jump / p.quietRef) : 0,
    calm: calmAdd(p, r),
  };
  if (p.wildScale !== 1 && p.calmRv1h > 0 && r?.rv1h != null && Number.isFinite(r.rv1h) && r.rv1h >= p.calmRv1h) {
    for (const k of ['vol', 'change', 'spread', 'flow', 'uncertainty', 'quiet'] as const) parts[k] *= p.wildScale;
  }
  const sum = parts.vol + parts.change + parts.spread + parts.flow + parts.uncertainty + parts.quiet + parts.calm + p.bias;
  const add = Math.max(-p.maxDown, Math.min(p.maxUp, sum));
  return { add: p.placebo ? placeboAdd(add) : add, parts };
}

/** The calm-market profile's add: 0 unless the profile is on and the reading says the coin is calm (rv1h known and low). */
export function calmAdd(p: DynamicEdgeParams, r: MarketStateReading | undefined): number {
  if (!(p.calmRv1h > 0) || r?.rv1h == null || !Number.isFinite(r.rv1h) || r.rv1h >= p.calmRv1h) return 0;
  const tight = p.calmTight && p.calmTightRef > 0 && r.spread != null && Number.isFinite(r.spread) ? p.calmTight * Math.max(0, 1 - r.spread / p.calmTightRef) : 0;
  return tight + p.calmFlow * Math.abs(v(r.flowImbalance)) + p.calmBias;
}

// The placebo (adversarial evaluator, Steven Nov 1): the same distribution of adds, but cut loose from the market state of
// the moment. If the placebo earns as much as the real edge, the gain comes from asking more on average, not from reading
// the market. Deterministic (fixed seed) so paired replays stay paired.
const placeboBuf: number[] = [];
let placeboSeed = 12345;
function placeboAdd(add: number): number {
  if (placeboBuf.length < 5000) placeboBuf.push(add);
  else placeboBuf[placeboSeed % 5000] = add;
  placeboSeed = (Math.imul(placeboSeed, 1664525) + 1013904223) >>> 0;
  return placeboBuf[placeboSeed % placeboBuf.length];
}

export const dynamicEdgeOn = (p: DynamicEdgeParams) => p.vol !== 0 || p.change !== 0 || p.spread !== 0 || p.flow !== 0 || p.uncertainty !== 0 || p.quiet !== 0 || p.bias !== 0 || (p.calmRv1h > 0 && (p.calmTight !== 0 || p.calmFlow !== 0 || p.calmBias !== 0));
