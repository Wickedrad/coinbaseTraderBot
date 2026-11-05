// Perps fee tier check (Steven, Nov 5 2026): this account's real Kalshi perps fee rates against the fees the bot charges.
//
// - GET /margin/fee_tiers (signed): the account's maker and taker rate per perp market, as decimal fractions of notional
//   (0.0012 = 0.12% = 12 bps). It names no tier.
// - GET /margin/fee_tier_rates (signed, added Sep 3 2026): the fee schedule, entry tier upward, rows
//   {fee_schedule, tier, maker_fee_rate, taker_fee_rate}. 403 when the account is not margin-enabled.
// The account's tier is found by matching its rates against the schedule, maker and taker apart (maker tiers 6-10 can also
// be reached by a share of perps maker volume). Tiers follow 30-day perps plus prediction volume and update once a day
// (Kalshi's CFTC filing of Jun 24 2026: tier 0 is taker 12 / maker 5 bps).
//
// The bot charges PERP_TAKER_FEE_BPS / PERP_MAKER_FEE_BPS in paper perps (bot/perps/paperPerp.ts) and in the setup
// trader's and perp trader's costs (bot/main.ts); a live account pays whatever Kalshi charges. This check only reports
// and alerts: it never changes the fees the bot charges.

/** One row of Kalshi's perps fee schedule, in bps of notional. */
export interface FeeTierRow { schedule: string; tier: number; makerBps: number; takerBps: number }
/** What this account pays on one perp market, in bps of notional. */
export interface MarketFee { ticker: string; makerBps: number; takerBps: number }

export interface FeeTierStatus {
  /** When the rates were read (ms). */
  at: number;
  /** The fees the bot charges (PERP_MAKER_FEE_BPS / PERP_TAKER_FEE_BPS). */
  configured: { makerBps: number; takerBps: number };
  /** Markets in the account's fee list. */
  markets: number;
  /** The distinct rates across those markets, with the schedule tier each one matches (null: no row matches). */
  rates: Array<{ makerBps: number; takerBps: number; makerTier: string | null; takerTier: string | null; tickers: string[] }>;
  /** The markets the bot reads (its perps feed), with their rates; missing: in the feed but not in the account's list. */
  traded: MarketFee[];
  missing: string[];
  /** The fee schedule as read (empty when /margin/fee_tier_rates refused). */
  schedule: FeeTierRow[];
  scheduleError?: string;
  /** Differences between what Kalshi charges this account and what the bot charges (empty: they agree). */
  mismatches: string[];
  /** One stable key per mismatch (its rates, not its wording), for alerting once per day. */
  mismatchKeys: string[];
  /** One line for the log and the info alert. */
  note: string;
}

/** A rate (decimal fraction of notional, number or numeric string) in bps, or undefined. */
function toBps(v: unknown): number | undefined {
  const x = typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN;
  return Number.isFinite(x) ? Math.round(x * 1e8) / 1e4 : undefined;
}

/** GET /margin/fee_tiers → the account's rate per market, sorted by ticker. A market missing either rate is left out. */
export function parseFeeTiers(raw: unknown): MarketFee[] {
  const r = (raw ?? {}) as { maker_fee_rates?: Record<string, unknown>; taker_fee_rates?: Record<string, unknown> };
  const mk = r.maker_fee_rates && typeof r.maker_fee_rates === 'object' ? r.maker_fee_rates : {};
  const tk = r.taker_fee_rates && typeof r.taker_fee_rates === 'object' ? r.taker_fee_rates : {};
  const out: MarketFee[] = [];
  for (const ticker of [...new Set([...Object.keys(mk), ...Object.keys(tk)])].sort()) {
    const makerBps = toBps(mk[ticker]), takerBps = toBps(tk[ticker]);
    if (makerBps !== undefined && takerBps !== undefined) out.push({ ticker, makerBps, takerBps });
  }
  return out;
}

/** GET /margin/fee_tier_rates → the schedule rows, in the order Kalshi lists them (entry tier upward). */
export function parseFeeTierRates(raw: unknown): FeeTierRow[] {
  const rows = (raw as { fee_tier_rates?: unknown } | undefined)?.fee_tier_rates;
  if (!Array.isArray(rows)) return [];
  const out: FeeTierRow[] = [];
  for (const x of rows as Array<Record<string, unknown>>) {
    const t = x?.tier;
    const tier = typeof t === 'number' ? t : typeof t === 'string' && t.trim() !== '' ? Number(t) : NaN;
    const makerBps = toBps(x?.maker_fee_rate), takerBps = toBps(x?.taker_fee_rate);
    if (Number.isInteger(tier) && makerBps !== undefined && takerBps !== undefined) out.push({ schedule: String(x.fee_schedule ?? ''), tier, makerBps, takerBps });
  }
  return out;
}

const fmt = (x: number) => String(+x.toFixed(4));
const same = (a: number, b: number, tol: number) => Math.abs(a - b) <= tol;
/** Every schedule row whose maker (or taker) rate equals `bps`, as "tier N" (with the schedule name when there are several). */
function tierOf(bps: number, rows: FeeTierRow[], side: 'makerBps' | 'takerBps'): string | null {
  const hit = rows.filter((r) => same(r[side], bps, 0.005));
  if (!hit.length) return null;
  const multi = new Set(rows.map((r) => r.schedule)).size > 1;
  return hit.map((r) => `tier ${r.tier}${multi && r.schedule ? ` (${r.schedule})` : ''}`).join(' or ');
}

/** Compares the account's rates with the fees the bot charges. `tickers` are the markets the bot reads; when none of
 *  them is known yet, every market in the account's list is compared. A difference above `tolBps` is a mismatch. */
export function evaluateFeeTier(fees: MarketFee[], schedule: FeeTierRow[], o: { makerBps: number; takerBps: number; tickers?: string[]; at: number; tolBps?: number; scheduleError?: string }): FeeTierStatus {
  const tol = o.tolBps ?? 0.05;
  const byTicker = new Map(fees.map((f) => [f.ticker, f]));
  const want = [...new Set(o.tickers ?? [])].sort();
  const traded = want.map((t) => byTicker.get(t)).filter((f): f is MarketFee => !!f);
  const missing = want.filter((t) => !byTicker.has(t));
  const groups = new Map<string, FeeTierStatus['rates'][number]>();
  for (const f of fees) {
    const k = `${f.makerBps}|${f.takerBps}`;
    const g = groups.get(k) ?? { makerBps: f.makerBps, takerBps: f.takerBps, makerTier: tierOf(f.makerBps, schedule, 'makerBps'), takerTier: tierOf(f.takerBps, schedule, 'takerBps'), tickers: [] };
    g.tickers.push(f.ticker);
    groups.set(k, g);
  }
  const rates = [...groups.values()].sort((a, b) => b.tickers.length - a.tickers.length);
  const mismatches: string[] = [], mismatchKeys: string[] = [];
  const compared = traded.length ? traded : fees;
  // Markets with the same rates are reported together.
  const off = new Map<string, MarketFee[]>();
  for (const f of compared) {
    if (same(f.takerBps, o.takerBps, tol) && same(f.makerBps, o.makerBps, tol)) continue;
    const k = `${f.makerBps}|${f.takerBps}`;
    off.set(k, [...(off.get(k) ?? []), f]);
  }
  const units = (f: MarketFee) => (Math.abs(f.takerBps) > 100 || Math.abs(f.makerBps) > 100 ? ' (above 100 bps: the rate may not be a fraction of notional)' : '');
  for (const fs of off.values()) {
    const f = fs[0], g = groups.get(`${f.makerBps}|${f.takerBps}`);
    const names = fs.length > 4 ? `${fs.slice(0, 4).map((x) => x.ticker).join(', ')} and ${fs.length - 4} more` : fs.map((x) => x.ticker).join(', ');
    const tier = schedule.length ? ` (taker ${g?.takerTier ?? 'no schedule row'}, maker ${g?.makerTier ?? 'no schedule row'})` : '';
    mismatches.push(`${names}: Kalshi charges this account taker ${fmt(f.takerBps)} / maker ${fmt(f.makerBps)} bps${tier}${units(f)}; the bot charges taker ${fmt(o.takerBps)} / maker ${fmt(o.makerBps)} (PERP_TAKER_FEE_BPS / PERP_MAKER_FEE_BPS)`);
    mismatchKeys.push(`rates ${f.makerBps}|${f.takerBps}`);
  }
  if (!fees.length) { mismatches.push('Kalshi returned no perp market in this account\'s fee list (GET /margin/fee_tiers); the bot\'s fees could not be checked'); mismatchKeys.push('no markets'); }
  else if (want.length && !traded.length) { mismatches.push(`none of the bot's perp markets (${want.join(', ')}) is in this account's fee list; compared every listed market instead`); mismatchKeys.push('none traded'); }
  const top = rates[0];
  const note = !fees.length ? 'no perp market in the account\'s fee list'
    : `${fees.length} market(s); ${rates.map((r) => `taker ${fmt(r.takerBps)} / maker ${fmt(r.makerBps)} bps (taker ${r.takerTier ?? '?'}, maker ${r.makerTier ?? '?'}) on ${r.tickers.length}`).join('; ')}; the bot charges taker ${fmt(o.takerBps)} / maker ${fmt(o.makerBps)}${mismatches.length ? '' : ': they agree'}${schedule.length ? '' : `; schedule not read${o.scheduleError ? ` (${o.scheduleError})` : ''}`}${top && missing.length ? `; not in the list: ${missing.join(', ')}` : ''}`;
  return { at: o.at, configured: { makerBps: o.makerBps, takerBps: o.takerBps }, markets: fees.length, rates, traded, missing, schedule, scheduleError: o.scheduleError, mismatches, mismatchKeys, note };
}

export interface FeeTierSource { feeTiers(): Promise<unknown>; feeTierRates(): Promise<unknown> }

/** Reads both endpoints and keeps the last good result (a failed read is kept beside it, never over it). */
export class PerpFeeTierCheck {
  private last?: FeeTierStatus;
  private lastError?: { at: number; error: string };

  constructor(private readonly src: FeeTierSource, private readonly o: { makerBps: number; takerBps: number; tickers: () => string[]; now?: () => number; tolBps?: number }) {}

  /** One read. Resolves with the new status, or with `{ error }` when the account's rates could not be read. */
  async run(): Promise<{ status?: FeeTierStatus; error?: string }> {
    const at = (this.o.now ?? Date.now)();
    const msg = (e: unknown) => String((e as Error)?.message ?? e).slice(0, 300);
    try {
      const [ft, fr] = await Promise.all([this.src.feeTiers(), this.src.feeTierRates().then((v) => ({ v }), (e: unknown) => ({ e: msg(e) }))]);
      // A refused schedule read keeps the last one read (the tier labels stay; the account's rates are always fresh).
      const schedule = 'v' in fr ? parseFeeTierRates(fr.v) : (this.last?.schedule ?? []);
      let tickers: string[] = [];
      try { tickers = this.o.tickers(); } catch { /* the feed is not up yet: every listed market is compared */ }
      const status = evaluateFeeTier(parseFeeTiers(ft), schedule, { makerBps: this.o.makerBps, takerBps: this.o.takerBps, tickers, at, tolBps: this.o.tolBps, scheduleError: 'e' in fr ? fr.e : undefined });
      this.last = status;
      this.lastError = undefined;
      return { status };
    } catch (e) {
      this.lastError = { at, error: msg(e) };
      return { error: this.lastError.error };
    }
  }

  /** The last good read from before a restart (shown until the first read of this run). */
  seed(s: FeeTierStatus | undefined): void { if (!this.last && s && typeof s.at === 'number' && Array.isArray(s.mismatches)) this.last = s; }

  /** For /api/status: the last good read, and the last failure if it came after it. */
  status(): (FeeTierStatus & { lastError?: { at: number; error: string } }) | { lastError?: { at: number; error: string }; note: string } {
    if (!this.last) return { note: this.lastError ? 'not read yet (the last read failed)' : 'not read yet', ...(this.lastError ? { lastError: this.lastError } : {}) };
    return { ...this.last, ...(this.lastError ? { lastError: this.lastError } : {}) };
  }
}
