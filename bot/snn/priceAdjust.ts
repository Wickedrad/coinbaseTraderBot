/**
 * SNN_PRICE (off by default): the SNN's contract call in the price, pulled toward the market and gated by regime.
 * The judge (research/snnAblation.ts, Nov 2): the raw SNN is worse than Kalshi's mid (it over-corrects), but pulled
 * toward the mid it beats the mid on held-out days; the pull picked per volatility regime on early days (normal x0.25,
 * low x0.5, high x0.5) gave -0.00023 Brier vs the mid on later days, uniform x0.5 -0.00021, shuffled-regime placebo
 * -0.00013. It still loses on "greater" (above-strike) contracts, so those are off by default.
 *   p_adj = mid + k(regime) (p_snn - mid);  p = (1 - alpha) p_model + alpha p_adj
 * The regime is the asset's volatility over its own one-day EWMA (time-based, so the engine's 1 s and the replay's
 * evaluations agree). Same code in paper, live and the replay.
 */
export interface SnnPriceConfig { alpha: number; kLow: number; kNormal: number; kHigh: number; offKinds: string[] }

export const DEFAULT_SNN_PRICE: SnnPriceConfig = { alpha: 0.25, kLow: 0.5, kNormal: 0.25, kHigh: 0.5, offKinds: ['greater'] };

/** Per-asset one-day EWMA of sigma, by elapsed time. */
export class VolRef {
  private m = new Map<string, { ref: number; t: number }>();
  ratio(asset: string, sigma: number, t: number): number {
    if (!(sigma > 0)) return 1;
    const s = this.m.get(asset);
    if (!s) { this.m.set(asset, { ref: sigma, t }); return 1; }
    const dt = Math.max(0, t - s.t) / 1000;
    s.ref += (1 - Math.exp(-dt / 86_400)) * (sigma - s.ref);
    s.t = t;
    return s.ref > 0 ? sigma / s.ref : 1;
  }
}

export function volRegime(volRatio: number): 'low' | 'normal' | 'high' {
  return volRatio < 0.8 ? 'low' : volRatio < 1.25 ? 'normal' : 'high';
}

/** The price with the SNN folded in, or pModel unchanged (with the reason) when the gate keeps it out. */
export function snnPrice(pModel: number, pSnn: number | undefined, mid: number, volRatio: number, kind: string, cfg: SnnPriceConfig): { p: number; why: string } {
  if (pSnn === undefined || !Number.isFinite(pSnn) || !Number.isFinite(mid)) return { p: pModel, why: 'no SNN call' };
  if (cfg.offKinds.includes(kind)) return { p: pModel, why: `off for ${kind}` };
  const reg = volRegime(volRatio);
  const k = reg === 'low' ? cfg.kLow : reg === 'normal' ? cfg.kNormal : cfg.kHigh;
  if (!(k > 0) || !(cfg.alpha > 0)) return { p: pModel, why: `off in ${reg} vol` };
  const adj = mid + k * (pSnn - mid);
  const p = Math.max(0.001, Math.min(0.999, (1 - cfg.alpha) * pModel + cfg.alpha * adj));
  return { p, why: `${reg} vol: k ${k}, alpha ${cfg.alpha}, shift ${((p - pModel) * 100).toFixed(2)}c` };
}
