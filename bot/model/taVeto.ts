// Job 6 of the TA rework (thread "Rework TA signals into real bot edge", round 4, Nov 2): the TA pieces as a CONTRARIAN
// veto on entries. On 240 replay days (Mar-Oct 2026) the bot's own entries, split at the median of each signal oriented to
// the bought side, made far less when the signal agreed with the trade: 30 s order flow for our side -27.8 c/ct
// [-37.5, -18.3] (day bootstrap), TA confluence for our side -18.7 [-27.5, -10.5], a busy tape (trade intensity 60 s
// above its median) -16.2 [-26.8, -5.8]. The crowd is already in and Kalshi's quote has moved; the gap to fair value
// that pays (+47 c/ct for the wide half) is then already chased. Each veto is off unless its threshold is set, and acts
// the same in paper and live (it reads the decision's feature map). Exits always pass.

export interface TaVetoConfig {
  /** Skip when the 30 s order-flow imbalance, oriented to the bought side, is above this (TA_VETO_OFI; NaN = off). */
  ofi: number;
  /** Skip when the confluence count, oriented to the bought side, is above this (TA_VETO_CONF; NaN = off). */
  conf: number;
  /** Skip when log(1 + contracts traded in 60 s) is above this (TA_VETO_INTENSITY; NaN = off). */
  intensity: number;
  /** How many of the set vetoes must fire to skip (TA_VETO_MIN, default 1). */
  min: number;
  /** Adversary: veto when the signals are AGAINST the bought side instead (TA_VETO_REVERSE). */
  reverse?: boolean;
  /** Adversary: skip this share of entries at random, ignoring the signals (TA_VETO_RANDOM; NaN = off). */
  random?: number;
}

export const taVetoOn = (c: TaVetoConfig | undefined): c is TaVetoConfig => !!c && (Number.isFinite(c.ofi) || Number.isFinite(c.conf) || Number.isFinite(c.intensity) || Number.isFinite(c.random ?? NaN));

let seed = 4242;
function draw(): number { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }

/** Which vetoes fire for an entry on `side` (feature map of the decision). */
export function taVetoReasons(c: TaVetoConfig, side: 'yes' | 'no', f: Record<string, number>): string[] {
  const s = (side === 'yes' ? 1 : -1) * (c.reverse ? -1 : 1);
  const out: string[] = [];
  const v = (k: string) => (Number.isFinite(f[k]) ? f[k] : undefined);
  const ofi = v('ofi_30s'), conf = v('conf_count'), inten = v('trade_intensity_60s');
  if (Number.isFinite(c.ofi) && ofi !== undefined && s * ofi > c.ofi) out.push(`order flow ${(s * ofi).toFixed(2)} for ${side.toUpperCase()}`);
  if (Number.isFinite(c.conf) && conf !== undefined && s * conf > c.conf) out.push(`confluence ${(s * conf).toFixed(0)} for ${side.toUpperCase()}`);
  if (Number.isFinite(c.intensity) && inten !== undefined && (c.reverse ? inten < c.intensity : inten > c.intensity)) out.push(`${c.reverse ? 'quiet' : 'busy'} tape ${inten.toFixed(1)}`);
  return out;
}

type VetoOrder = { side: 'bid' | 'ask'; price: number; reduceOnly: boolean; purpose: string; why: string };
/** Drop the entry orders (takes and maker entry quotes) the veto fires on. Returns how many were dropped. */
export function applyTaVeto<T extends VetoOrder>(plan: { place: T[]; notes: string[] }, c: TaVetoConfig | undefined, f: Record<string, number>): number {
  if (!taVetoOn(c)) return 0;
  let n = 0;
  plan.place = plan.place.filter((o) => {
    if (o.reduceOnly || o.purpose === 'exit' || (o.purpose === 'quote' && !o.why.startsWith('maker '))) return true;
    const side = o.side === 'bid' ? 'yes' : 'no';
    const r = Number.isFinite(c.random ?? NaN) ? (draw() < c.random! ? ['random control'] : []) : taVetoReasons(c, side, f);
    if (r.length < (Number.isFinite(c.random ?? NaN) ? 1 : Math.max(1, c.min))) return true;
    n++;
    plan.notes.push(`TA veto: skip ${side.toUpperCase()} @ ${(side === 'yes' ? o.price : 1 - o.price).toFixed(2)} (${r.join(', ')})`);
    return false;
  });
  return n;
}

/** Entry spread filter (TA_MAX_SPREAD, unset = off): no new entry into a contract quoted wider than maxSpread (a 1c bid
 * and 99c ask gives a 50c "mid" that is not a price). Exits, reduce-only orders and cancels always pass. */
export function applyMaxSpread<T extends VetoOrder & { reduceOnly?: boolean }>(plan: { place: T[]; notes: string[] }, maxSpread: number | undefined, bid: number, ask: number): number {
  if (maxSpread === undefined || !Number.isFinite(maxSpread) || ask - bid <= maxSpread) return 0;
  let n = 0;
  plan.place = plan.place.filter((o) => {
    if (o.reduceOnly || o.purpose === 'exit') return true;
    n++;
    return false;
  });
  if (n) plan.notes.push(`TA spread filter: skipped ${n} entries (spread ${(ask - bid).toFixed(2)} > ${maxSpread})`);
  return n;
}
