/**
 * QUOTE_LAG_HOLD (off by default): Kalshi's quote follows the coin-implied fair value a few seconds to a minute late
 * (the quote-lag study, research/quoteLagStudy.ts: it closes about a quarter of a gap in 5-60 s). When fair value has
 * moved at least `theta` over the last `windowSec` and the quote has not followed (gap = fair's move - mid's move, same
 * sign, at least theta), buying the side the gap is AGAINST is dear right now: the quote is about to move in its favour.
 * The hold drops orders that open or add to that side for up to `maxSec`, then lets them through until the gap clears.
 * Entries on the side the gap favours, exits and reduce-only orders are never held (the study's control: holding those
 * costs ~1.2c). Recorded days to Nov 1, 3 s latency + 1c slip: theta 10c, w 10 s, H 60 s saved 3.5c [2.5, 4.6] a
 * contract; placebo (no gap) 0.0c. Same code in paper and live.
 */
import type { RestingQuote, StrategyOutput } from './fairValueStrategy';

/** cancelResting (QUOTE_LAG_HOLD_CANCEL): also pull a resting maker quote that buys the against side while the hold runs.
 *  The edge-driven plan never places a new against-side entry (d29-hold3: 623 triggers, 0 against entries), but a quote
 *  placed before the move still rests there: the adverse-selection case (fidelity: real markout ~1c worse than the sim). */
export interface QuoteLagHoldConfig { theta: number; windowSec: number; maxSec: number; cancelResting?: boolean }

interface Sample { t: number; fair: number; mid: number }

export class QuoteLagHold {
  private hist = new Map<string, Sample[]>();
  private since = new Map<string, { side: 'yes' | 'no'; t: number }>();
  /** Diagnostics: evaluations seen, with a gap reading, with the hold triggered, and entries on each side while triggered. */
  readonly stats = { evals: 0, withGap: 0, triggered: 0, againstEntries: 0, favouredEntries: 0, maxAbsGap: 0, restingCancelled: 0 };
  constructor(readonly cfg: QuoteLagHoldConfig) {}

  /** Record one evaluation's fair value and quote mid for a market. */
  record(ticker: string, t: number, fair: number, mid: number): void {
    if (!Number.isFinite(fair) || !Number.isFinite(mid)) return;
    let h = this.hist.get(ticker);
    if (!h) this.hist.set(ticker, (h = []));
    h.push({ t, fair, mid });
    const keep = t - (this.cfg.windowSec + 30) * 1000;
    while (h.length > 2 && h[0].t < keep) h.shift();
  }

  /** The gap and fair's own move over the window (probability units), or undefined without a sample about windowSec ago. */
  gap(ticker: string, t: number): { gap: number; fairMove: number } | undefined {
    const h = this.hist.get(ticker);
    if (!h?.length) return undefined;
    const now = h[h.length - 1], target = t - this.cfg.windowSec * 1000;
    let j = -1;
    for (let i = h.length - 1; i >= 0; i--) if (h[i].t <= target) { j = i; break; }
    if (j < 0 || now.t - h[j].t > (this.cfg.windowSec + 5) * 1000) return undefined;
    const f = now.fair - h[j].fair;
    return { gap: f - (now.mid - h[j].mid), fairMove: f };
  }

  /** The side the gap is against right now ('no' when fair jumped up and the quote lags), or undefined. */
  against(ticker: string, t: number): 'yes' | 'no' | undefined {
    const g = this.gap(ticker, t), th = this.cfg.theta;
    if (!g || Math.abs(g.gap) < th || Math.abs(g.fairMove) < th || Math.sign(g.gap) !== Math.sign(g.fairMove)) return undefined;
    return g.gap > 0 ? 'no' : 'yes';
  }

  /** Drop the plan's orders that open or add to the side the gap is against, within maxSec of the hold starting. */
  apply(plan: StrategyOutput, ticker: string, t: number, position: number, resting?: { bid?: RestingQuote; ask?: RestingQuote }): number {
    this.stats.evals++;
    const g = this.gap(ticker, t);
    if (g) { this.stats.withGap++; this.stats.maxAbsGap = Math.max(this.stats.maxAbsGap, Math.abs(g.gap)); }
    const side = this.against(ticker, t);
    if (!side) { this.since.delete(ticker); return 0; }
    this.stats.triggered++;
    for (const p of plan.place) if (!p.reduceOnly && p.purpose !== 'exit' && p.count > 0) {
      if ((p.side === 'bid' ? 'yes' : 'no') === side) this.stats.againstEntries++; else this.stats.favouredEntries++;
    }
    let s = this.since.get(ticker);
    if (!s || s.side !== side) this.since.set(ticker, (s = { side, t }));
    if (t - s.t >= this.cfg.maxSec * 1000) return 0; // waited long enough: let it through until the gap clears
    if (this.cfg.cancelResting && resting) {
      const q = side === 'yes' ? resting.bid : resting.ask; // a resting bid buys YES, a resting ask buys NO
      const reduces = side === 'yes' ? position < 0 : position > 0;
      if (q && q.remaining > 0 && !reduces && !plan.cancel.some((c) => c.clientOrderId === q.clientOrderId)) {
        plan.cancel.push({ clientOrderId: q.clientOrderId, reason: `quote lag hold: pull the resting ${side.toUpperCase()} quote (the quote lags fair value)` });
        this.stats.restingCancelled++;
      }
    }
    const before = plan.place.length;
    plan.place = plan.place.filter((p) => {
      if (p.reduceOnly || p.purpose === 'exit' || !(p.count > 0)) return true;
      const buysYes = p.side === 'bid';
      if (buysYes ? position < 0 && p.count <= -position + 1e-9 : position > 0 && p.count <= position + 1e-9) return true; // reduces
      if ((buysYes ? 'yes' : 'no') !== side) return true;
      plan.notes.push(`quote lag hold: held ${p.purpose} ${buysYes ? 'YES' : 'NO'} at ${(buysYes ? p.price : 1 - p.price).toFixed(2)} (the quote lags fair value; ${Math.round((t - s!.t) / 1000)} s of ${this.cfg.maxSec})`);
      return false;
    });
    return before - plan.place.length;
  }

  forget(ticker: string): void { this.hist.delete(ticker); this.since.delete(ticker); }
}
