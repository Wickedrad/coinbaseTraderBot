/** As-of context from public messages already present in native bot recordings. */
import type { FeatureGroup } from './features';

interface Snapshot { ts: number; knownAt: number; values: Record<string, number | null> }
const finite = (v: unknown) => typeof v === 'number' && Number.isFinite(v) ? v : null;
const positive = (v: unknown) => { const n = finite(v); return n !== null && n > 0 ? n : null; };
const share = (v: unknown, max: number) => { const n = finite(v); return n !== null && n >= 0 && n <= max ? n : null; };
export class RecordedMarketContext {
  private readonly perps = new Map<string, Snapshot>();
  private dominance?: Snapshot;
  constructor(private readonly sha256: string) {}
  observe(e: { t: number; k: string; [key: string]: unknown }) {
    if (e.k !== 'perp' && e.k !== 'dominance') return;
    const ts = e.ts ?? e.t;
    if (!Number.isSafeInteger(ts) || (ts as number) < 0 || !Number.isSafeInteger(e.t) || (ts as number) > e.t) throw new Error('invalid or future recorded context clock');
    if (e.k === 'dominance') {
      if (this.dominance && (ts as number) < this.dominance.ts) return;
      this.dominance = { ts: ts as number, knownAt: e.t,
        values: { btcd: share(e.btcd, 100), usdtd: share(e.usdtd, 100), btcdom: share(e.btcdom, 100), covered_share: share(e.covered, 1) } };
    } else if (typeof e.asset === 'string') {
      const old = this.perps.get(e.asset); if (old && (ts as number) < old.ts) return;
      const funding = finite(e.fundingRate), oi = positive(e.openInterest) ?? (e.openInterest === 0 ? 0 : null);
      const adjacent = old && (ts as number) - old.ts <= 60000;
      this.perps.set(e.asset, { ts: ts as number, knownAt: e.t, values: {
        funding_rate: funding, open_interest_contracts: oi, contract_size: positive(e.contractSize),
        mark_per_contract: positive(e.mark), bid_per_contract: positive(e.bid), ask_per_contract: positive(e.ask),
        funding_change: adjacent && funding !== null && old.values.funding_rate !== null ? finite(funding - old.values.funding_rate) : null,
        open_interest_change: adjacent && oi !== null && old.values.open_interest_contracts !== null ? oi - old.values.open_interest_contracts : null,
      } });
    }
  }
  at(asset: string, now: number, index: number): Record<string, FeatureGroup> {
    if (!Number.isSafeInteger(now) || now < 0) throw new Error('invalid recorded context lookup clock');
    const group = (s: Snapshot | undefined, source: string, values: Record<string, number | null>): FeatureGroup => {
      if (s && s.knownAt > now) throw new Error('future recorded context lookup');
      const stale = !!s && now - s.ts > 60000;
      return { source, sha256: this.sha256, timeframe: 'micro', status: !s ? 'missing' : stale ? 'stale' : 'ready',
        bars: s ? 1 : 0, firstOpen: s?.ts ?? null, lastOpen: s?.ts ?? null, knownAt: s?.knownAt ?? null,
        publicationLagMs: s ? s.knownAt - s.ts : 0,
        timing: 'Observed native snapshot and actual arrival; 60-second maximum source age, no daily-provider relabeling',
        values: !s || stale ? Object.fromEntries(Object.keys(values).map((k) => [k, null])) : values };
    };
    const p = this.perps.get(asset), v = p?.values;
    const size = v?.contract_size ?? null, mark = v?.mark_per_contract ?? null;
    const perCoin = size !== null && mark !== null ? finite(mark / size) : null;
    const perp = { funding_rate: v?.funding_rate ?? null, funding_change: v?.funding_change ?? null,
      open_interest_contracts: v?.open_interest_contracts ?? null, open_interest_change: v?.open_interest_change ?? null,
      contract_size: size, mark_per_coin: perCoin, source_age_sec: p ? (now - p.ts) / 1000 : null,
      premium_bps: perCoin !== null && index > 0 ? finite((perCoin / index - 1) * 10000) : null };
    const micro = group(p, 'observed-native-perp-snapshot', perp);
    // Premium also depends on the index observed at this decision, so its conservative
    // group availability is the decision arrival, not merely the older perp message.
    if (p && micro.status === 'ready') micro.knownAt = now;
    return { micro_perp: micro, observed_dominance: group(this.dominance, 'observed-native-dominance-snapshot',
      this.dominance?.values ?? { btcd: null, usdtd: null, btcdom: null, covered_share: null }) };
  }
}
