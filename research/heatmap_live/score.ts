/** Scores shadow entries on the captured public books with the one test, under PREREG.md.
 *  Pure functions; the CLI below reads capture segments and (optionally) a private file of the bot's opening
 *  fills, and prints totals only. No prices of single trades, no log rows. */
import fs from 'node:fs';
import path from 'node:path';
import { gunzipSync } from 'node:zlib';
import { takerFee } from '../../bot/fees';
import { snapToGrid, tickAt, type PriceBand } from '../../bot/kalshi/priceGrid';

export const RULES = Object.freeze({
  stakeUsd: 10, minSide: 0.10, maxSide: 0.90, entryLagMs: 20_000, windowMs: 60_000, sampleGapMs: 25_000, holeMs: 60_000,
  m15: { from: 840_000, to: 300_000, deadline: 90_000 }, hourly: { from: 3_300_000, to: 600_000, deadline: 360_000 },
  marginPerContract: 0.01, randomMinutes: 10, bootstrap: 2000, seed: 20261111,
});
export type Side = 'yes' | 'no';
export type Kind = '15m' | 'hourly';
export interface Market { ticker: string; asset: string; kind: Kind; openTime: number; closeTime: number; tickSize?: number; priceRanges?: PriceBand[] }
/** One book sample: time, best YES bid and size, best YES ask and size (NaN when that side is empty). */
export interface Sample { t: number; yb: number; ybs: number; ya: number; yas: number }
export interface Forecast { asset: string; horizon: 15 | 60; featureAt: number; publishedAt: number; p: number[]; uniform: number[]; prior: number[]; axes?: number; curves?: number }

export const sideAsk = (s: Sample, side: Side) => side === 'yes' ? s.ya : 1 - s.yb;
export const sideBid = (s: Sample, side: Side) => side === 'yes' ? s.yb : 1 - s.ya;
export const sideBidSize = (s: Sample, side: Side) => side === 'yes' ? s.ybs : s.yas;
const twoSided = (s: Sample) => Number.isFinite(s.yb) && Number.isFinite(s.ya) && s.ya > s.yb;
const r4 = (x: number) => Math.round(x * 10000) / 10000;
export const callOf = (p: number[]): 'up' | 'down' | null => Math.abs(p[0] - p[2]) < 1e-10 ? null : p[0] > p[2] ? 'up' : 'down';

/** The lowest grid price at which selling C contracts nets the entry cost (with its fee) plus 1c a contract. */
export function exitLevel(ask: number, contracts: number, m: Pick<Market, 'tickSize' | 'priceRanges'>, entryFee = takerFee(contracts, ask)): number | undefined {
  const need = contracts * ask + entryFee + RULES.marginPerContract * contracts, tick = m.tickSize ?? 0.01;
  let b = snapToGrid(ask, m.priceRanges, tick, 1);
  for (let i = 0; b !== undefined && b < 1 && i < 2000; i++) {
    if (contracts * b - takerFee(contracts, b) >= need - 1e-9) return b;
    b = snapToGrid(r4(b + tickAt(b + 1e-7, m.priceRanges, tick)), m.priceRanges, tick, 1);
  }
  return undefined;
}

export interface Scored {
  status: 'scored' | 'no-book' | 'one-sided' | 'out-of-band' | 'incomplete';
  ask?: number; contracts?: number; level?: number; window?: boolean; windowDepth?: boolean; toWindowMs?: number; windowMs?: number; dip?: number;
}
/** First index with t >= x (samples sorted by t). */
export function lowerBound(samples: Sample[], x: number): number {
  let lo = 0, hi = samples.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (samples[mid].t < x) lo = mid + 1; else hi = mid; }
  return lo;
}
/** The one test for one entry: buy `side` at the ask of the first book at or after `at`. `own` scores a real fill instead. */
export function scoreEntry(m: Market, samples: Sample[], side: Side, at: number, o: { band?: boolean; own?: { price: number; contracts: number; fee: number } } = {}): Scored {
  const i = lowerBound(samples, at), e = samples[i];
  if (!e || e.t - at > RULES.entryLagMs) return { status: 'no-book' };
  if (!twoSided(e)) return { status: 'one-sided' };
  const ask = o.own ? o.own.price : r4(sideAsk(e, side));
  if (o.band !== false && !(ask >= RULES.minSide - 1e-9 && ask <= RULES.maxSide + 1e-9)) return { status: 'out-of-band', ask };
  const contracts = o.own ? o.own.contracts : Math.max(1, Math.floor(RULES.stakeUsd / ask + 1e-9));
  const level = exitLevel(ask, contracts, m, o.own ? o.own.fee : undefined);
  const deadline = m.closeTime - (m.kind === '15m' ? RULES.m15.deadline : RULES.hourly.deadline);
  // The record must run from the entry book to the deadline with no hole over a minute.
  let prev = e.t, end = i;
  for (let j = i + 1; j < samples.length && samples[j].t <= deadline; j++) { if (samples[j].t - prev > RULES.holeMs) return { status: 'incomplete', ask, contracts, level }; prev = samples[j].t; end = j; }
  if (deadline - prev > RULES.holeMs) return { status: 'incomplete', ask, contracts, level };
  let window = false, windowDepth = false, toWindowMs: number | undefined, windowMs: number | undefined, dip = 0, run = -1, depthRun = -1, last = -Infinity;
  for (let j = i + 1; j <= end; j++) {
    const s = samples[j], bid = sideBid(s, side), ok = level !== undefined && Number.isFinite(bid) && bid >= level - 1e-9;
    if (s.t - last > RULES.sampleGapMs) { run = -1; depthRun = -1; }
    last = s.t;
    if (!window && Number.isFinite(bid)) dip = Math.min(dip, bid - ask);
    if (!ok) { run = -1; depthRun = -1; continue; }
    if (run < 0) run = j;
    if (sideBidSize(s, side) >= contracts) { if (depthRun < 0) depthRun = j; } else depthRun = -1;
    if (s.t - samples[run].t >= RULES.windowMs) { if (!window) { window = true; toWindowMs = samples[run].t - e.t; } windowMs = s.t - samples[run].t; }
    if (depthRun >= 0 && s.t - samples[depthRun].t >= RULES.windowMs) windowDepth = true;
  }
  return { status: 'scored', ask, contracts, level, window, windowDepth, toWindowMs, windowMs, dip: r4(dip) };
}

// ---- deterministic randomness (seeded, so every run of the scorer gives the same numbers) ----
export function rng(seed: number) { let a = seed >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const hash = (s: string) => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; };

export interface Entry {
  contender: string; asset: string; kind: Kind; ticker: string; contract: string; slot: number; side: Side; at: number;
  /** Scores: called side, opposite side, the coin's usual side, same side at random minutes (mean). 1/0, or undefined when not scorable. */
  called?: number; opposite?: number; usual?: number; randomMinute?: number; calledDepth?: number; own?: number;
  toWindowMs?: number; windowMs?: number; dip?: number; status: Scored['status']; first: boolean; agree?: boolean; differsFromUsual?: boolean;
}
const flip = (s: Side): Side => s === 'yes' ? 'no' : 'yes';
const win = (s: Scored) => s.status === 'scored' ? Number(!!s.window) : undefined;
const windowOf = (m: Market) => m.kind === '15m' ? RULES.m15 : RULES.hourly;
const inWindow = (m: Market, at: number) => { const w = windowOf(m), ttc = m.closeTime - at; return ttc <= w.from && ttc >= w.to; };

/** Same side at up to K random book times inside the contract's entry window (the timing control). */
function randomMinuteScore(m: Market, samples: Sample[], side: Side, key: string): number | undefined {
  const w = windowOf(m), lo = lowerBound(samples, m.closeTime - w.from), hi = lowerBound(samples, m.closeTime - w.to + 1);
  if (hi <= lo) return undefined;
  const r = rng(hash(key) ^ RULES.seed); let n = 0, sum = 0;
  for (let k = 0; k < RULES.randomMinutes; k++) { const s = win(scoreEntry(m, samples, side, samples[lo + Math.floor(r() * (hi - lo))].t)); if (s !== undefined) { n++; sum += s; } }
  return n ? sum / n : undefined;
}

export interface Capture { markets: Map<string, Market>; books: Map<string, Sample[]>; forecasts: Forecast[] }

/** Shadow entries of the heat maps: the 15-minute call on the 15-minute contract, the 1-hour call on the hourly strike nearest 50c. */
export function heatEntries(c: Capture, from: number, to: number): { entries: Entry[]; noEntry: Record<string, number> } {
  const entries: Entry[] = [], noEntry: Record<string, number> = {}, seen = new Set<string>();
  const miss = (k: string) => { noEntry[k] = (noEntry[k] ?? 0) + 1; };
  const byAsset = new Map<string, Market[]>();
  for (const m of c.markets.values()) { const k = `${m.asset}:${m.kind}`; if (!byAsset.has(k)) byAsset.set(k, []); byAsset.get(k)!.push(m); }
  const hourCall = new Map<string, 'up' | 'down' | null>();
  for (const f of c.forecasts) if (f.horizon === 60) hourCall.set(`${f.asset}:${f.featureAt}`, callOf(f.p));
  for (const f of [...c.forecasts].sort((a, b) => a.publishedAt - b.publishedAt)) {
    if (f.publishedAt < from || f.publishedAt >= to) continue;
    const kind: Kind = f.horizon === 15 ? '15m' : 'hourly', name = f.horizon === 15 ? 'map15' : 'map60', call = callOf(f.p);
    if (!call) { miss(`${name}:tie`); continue; }
    const live = (byAsset.get(`${f.asset}:${kind}`) ?? []).filter((m) => m.openTime <= f.publishedAt && m.closeTime > f.publishedAt && inWindow(m, f.publishedAt));
    if (!live.length) { miss(`${name}:outside-entry-window`); continue; }
    const close = Math.min(...live.map((m) => m.closeTime));
    // Hourly: the watched strike whose YES mid is nearest 50c at this moment.
    let pick: Market | undefined, best = Infinity;
    for (const m of live.filter((x) => x.closeTime === close)) {
      const ss = c.books.get(m.ticker) ?? [], s = ss[lowerBound(ss, f.publishedAt)];
      if (!s || s.t - f.publishedAt > RULES.entryLagMs || !twoSided(s)) continue;
      const d = Math.abs((s.yb + s.ya) / 2 - 0.5); if (d < best) { best = d; pick = m; }
    }
    if (!pick) { miss(`${name}:no-two-sided-book`); continue; }
    const samples = c.books.get(pick.ticker)!, side: Side = call === 'up' ? 'yes' : 'no', usualSide: Side = (callOf(f.prior) ?? call) === 'up' ? 'yes' : 'no';
    const s = scoreEntry(pick, samples, side, f.publishedAt);
    if (s.status === 'out-of-band' || s.status === 'no-book' || s.status === 'one-sided') { miss(`${name}:${s.status}`); continue; }
    const contract = kind === '15m' ? pick.ticker : `${f.asset}:${close}`, key = `${name}:${contract}`, first = !seen.has(key); seen.add(key);
    const opp = scoreEntry(pick, samples, flip(side), f.publishedAt, { band: false });
    const h = hourCall.get(`${f.asset}:${f.featureAt}`);
    entries.push({ contender: name, asset: f.asset, kind, ticker: pick.ticker, contract, slot: close, side, at: f.publishedAt, status: s.status, first,
      called: win(s), opposite: win(opp), usual: usualSide === side ? win(s) : win(opp), calledDepth: s.status === 'scored' ? Number(!!s.windowDepth) : undefined,
      randomMinute: randomMinuteScore(pick, samples, side, key + f.publishedAt), toWindowMs: s.toWindowMs, windowMs: s.windowMs, dip: s.dip,
      agree: f.horizon === 15 && h ? h === call : undefined, differsFromUsual: usualSide !== side });
  }
  return { entries, noEntry };
}

export interface BotFill { ticker: string; side: Side; ts: number; price: number; count: number; fee: number }
/** The bot's opening fills, scored at the ask like the shadow entries and at their own price and size. */
export function botEntries(c: Capture, fills: BotFill[], from: number, to: number): { entries: Entry[]; noEntry: Record<string, number> } {
  const entries: Entry[] = [], noEntry: Record<string, number> = {}, seen = new Set<string>();
  const miss = (k: string) => { noEntry[k] = (noEntry[k] ?? 0) + 1; };
  for (const f of [...fills].sort((a, b) => a.ts - b.ts)) {
    if (f.ts < from || f.ts >= to) continue;
    const m = c.markets.get(f.ticker), samples = c.books.get(f.ticker);
    if (!m || !samples?.length) { miss('bot:contract-not-watched'); continue; }
    const s = scoreEntry(m, samples, f.side, f.ts, { band: false });
    if (s.status === 'no-book' || s.status === 'one-sided') { miss(`bot:${s.status}`); continue; }
    const key = `bot:${f.ticker}`, first = !seen.has(key); seen.add(key);
    const opp = scoreEntry(m, samples, flip(f.side), f.ts, { band: false }), own = scoreEntry(m, samples, f.side, f.ts, { band: false, own: { price: f.price, contracts: f.count, fee: f.fee } });
    entries.push({ contender: 'bot', asset: m.asset, kind: m.kind, ticker: f.ticker, contract: f.ticker, slot: m.closeTime, side: f.side, at: f.ts, status: s.status, first,
      called: win(s), opposite: win(opp), calledDepth: s.status === 'scored' ? Number(!!s.windowDepth) : undefined, own: win(own),
      randomMinute: randomMinuteScore(m, samples, f.side, key + f.ts), toWindowMs: s.toWindowMs, windowMs: s.windowMs, dip: s.dip });
  }
  return { entries, noEntry };
}

// ---- totals ----
const mean = (xs: number[]) => xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN;
const median = (xs: number[]) => { if (!xs.length) return NaN; const s = [...xs].sort((a, b) => a - b); return s[Math.floor((s.length - 1) / 2)]; };
export interface Row {
  n: number; slots: number; rate: number; randomSide: number; gap: number; gapSe: number; z: number;
  usualRate?: number; gapVsUsual?: number; gapVsUsualSe?: number; randomMinute?: number; gapVsRandomMinute?: number; gapVsRandomMinuteSe?: number;
  rateDepth?: number; ownRate?: number; incomplete: number; medianToWindowSec?: number; medianWindowSec?: number; medianDipCents?: number;
}
/** A per-entry value whose mean over the entries that have it is the statistic. */
type Value = (e: Entry) => number | undefined;
const vRandomSide: Value = (e) => e.called !== undefined && e.opposite !== undefined ? (e.called - e.opposite) / 2 : undefined;
const vUsual: Value = (e) => e.called !== undefined && e.usual !== undefined ? e.called - e.usual : undefined;
const vRandomMinute: Value = (e) => e.called !== undefined && e.randomMinute !== undefined ? e.called - e.randomMinute : undefined;
const meanOf = (es: Entry[], v: Value) => mean(es.map(v).filter((x): x is number => x !== undefined));
/** Per time slot: the sum and count of a value. Coins in one slot move together, so slots are what is resampled. */
function slotSums(es: Entry[], v: Value): Map<number, [number, number]> {
  const g = new Map<number, [number, number]>();
  for (const e of es) { const x = v(e); if (x === undefined) continue; const c = g.get(e.slot) ?? [0, 0]; c[0] += x; c[1]++; g.set(e.slot, c); }
  return g;
}
/** Standard error of a mean by resampling whole time slots. */
export function slotSe(es: Entry[], v: Value, seed: number): number {
  const g = [...slotSums(es, v).values()]; if (g.length < 2) return NaN;
  const r = rng(seed), vals: number[] = [];
  for (let b = 0; b < RULES.bootstrap; b++) { let s = 0, n = 0; for (let i = 0; i < g.length; i++) { const c = g[Math.floor(r() * g.length)]; s += c[0]; n += c[1]; } if (n) vals.push(s / n); }
  const m = mean(vals); return Math.sqrt(mean(vals.map((x) => (x - m) ** 2)));
}
export function summarize(all: Entry[]): Row {
  const es = all.filter((e) => e.status === 'scored'), p = es.filter((e) => vRandomSide(e) !== undefined);
  const gap = meanOf(es, vRandomSide), gapSe = slotSe(es, vRandomSide, RULES.seed);
  const row: Row = { n: es.length, slots: new Set(es.map((e) => e.slot)).size, rate: mean(es.map((e) => e.called!)), randomSide: mean(p.map((e) => (e.called! + e.opposite!) / 2)), gap, gapSe, z: gap / gapSe,
    incomplete: all.length - es.length, rateDepth: mean(es.filter((e) => e.calledDepth !== undefined).map((e) => e.calledDepth!)),
    medianToWindowSec: Math.round(median(es.filter((e) => e.toWindowMs !== undefined).map((e) => e.toWindowMs!)) / 1000),
    medianWindowSec: Math.round(median(es.filter((e) => e.windowMs !== undefined).map((e) => e.windowMs!)) / 1000),
    medianDipCents: Math.round(median(es.filter((e) => e.dip !== undefined).map((e) => e.dip!)) * 1000) / 10 };
  if (es.some((e) => vUsual(e) !== undefined)) { row.usualRate = mean(es.filter((e) => e.usual !== undefined).map((e) => e.usual!)); row.gapVsUsual = meanOf(es, vUsual); row.gapVsUsualSe = slotSe(es, vUsual, RULES.seed + 1); }
  if (es.some((e) => vRandomMinute(e) !== undefined)) { row.randomMinute = mean(es.filter((e) => e.randomMinute !== undefined).map((e) => e.randomMinute!)); row.gapVsRandomMinute = meanOf(es, vRandomMinute); row.gapVsRandomMinuteSe = slotSe(es, vRandomMinute, RULES.seed + 2); }
  const own = es.filter((e) => e.own !== undefined); if (own.length) row.ownRate = mean(own.map((e) => e.own!));
  return row;
}
/** Is contender A's gap over random side larger than B's? The same time slots are drawn for both. */
export function compareGaps(a: Entry[], b: Entry[]): { diff: number; se: number; z: number } {
  const A = a.filter((e) => e.status === 'scored'), B = b.filter((e) => e.status === 'scored'), ga = slotSums(A, vRandomSide), gb = slotSums(B, vRandomSide);
  const slots = [...new Set([...ga.keys(), ...gb.keys()])], diff = meanOf(A, vRandomSide) - meanOf(B, vRandomSide), r = rng(RULES.seed + 7), vals: number[] = [];
  for (let k = 0; k < RULES.bootstrap && slots.length > 1; k++) {
    let sa = 0, na = 0, sb = 0, nb = 0;
    for (let i = 0; i < slots.length; i++) { const s = slots[Math.floor(r() * slots.length)], x = ga.get(s), y = gb.get(s); if (x) { sa += x[0]; na += x[1]; } if (y) { sb += y[0]; nb += y[1]; } }
    if (na && nb) vals.push(sa / na - sb / nb);
  }
  const m = mean(vals), se = Math.sqrt(mean(vals.map((x) => (x - m) ** 2)));
  return { diff, se, z: diff / se };
}

// ---- reading capture segments ----
function lines(file: string): string[] { return fs.existsSync(file) ? (file.endsWith('.gz') ? gunzipSync(fs.readFileSync(file)).toString('utf8') : fs.readFileSync(file, 'utf8')).split('\n').filter(Boolean) : []; }
function find(dir: string, name: string, out: string[] = []): string[] {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) { const p = path.join(dir, e.name); if (e.isDirectory()) find(p, name, out); else if (e.name === name || e.name === `${name}.gz`) out.push(p); }
  return out;
}
export function loadCapture(dir: string): Capture {
  const markets = new Map<string, Market>(), books = new Map<string, Sample[]>(), forecasts: Forecast[] = [], seen = new Set<string>();
  for (const f of find(dir, 'markets.jsonl')) for (const l of lines(f)) { const m = JSON.parse(l); if (!markets.has(m.ticker)) markets.set(m.ticker, m); }
  for (const f of find(dir, 'forecasts.jsonl')) for (const l of lines(f)) { const r = JSON.parse(l), k = `${r.asset}:${r.horizon}:${r.featureAt}`; if (!seen.has(k)) { seen.add(k); forecasts.push(r); } }
  for (const f of find(dir, 'books.jsonl')) for (const l of lines(f)) {
    const b = JSON.parse(l); if (!books.has(b.x)) books.set(b.x, []);
    books.get(b.x)!.push({ t: b.t, yb: b.yb[0]?.[0] ?? NaN, ybs: b.yb[0]?.[1] ?? 0, ya: b.ya[0]?.[0] ?? NaN, yas: b.ya[0]?.[1] ?? 0 });
  }
  for (const s of books.values()) s.sort((a, b) => a.t - b.t);
  return { markets, books, forecasts };
}

const pct = (x: number | undefined) => x === undefined || !Number.isFinite(x) ? 'n/a' : `${(100 * x).toFixed(1)}%`;
const pts = (x: number | undefined, se?: number) => x === undefined || !Number.isFinite(x) ? 'n/a' : `${x >= 0 ? '+' : ''}${(100 * x).toFixed(1)}${se !== undefined && Number.isFinite(se) ? ` ± ${(100 * se).toFixed(1)}` : ''}`;
export function report(c: Capture, fills: BotFill[] | undefined, from: number, to: number): { markdown: string; json: unknown } {
  const heat = heatEntries(c, from, to), bot = fills ? botEntries(c, fills, from, to) : undefined;
  const sets: Array<[string, Entry[]]> = [];
  const add = (label: string, es: Entry[]) => sets.push([label, es]);
  for (const primary of [true, false]) {
    const tag = primary ? 'first entry per contract' : 'every qualifying entry', pick = (es: Entry[]) => primary ? es.filter((e) => e.first) : es;
    const m15 = pick(heat.entries.filter((e) => e.contender === 'map15')), m60 = pick(heat.entries.filter((e) => e.contender === 'map60'));
    add(`15-minute map on 15-minute contracts (${tag})`, m15);
    add(`  when the 1-hour map agrees (${tag})`, m15.filter((e) => e.agree === true));
    add(`  when the 1-hour map disagrees (${tag})`, m15.filter((e) => e.agree === false));
    add(`  when the call differs from the coin's usual side (${tag})`, m15.filter((e) => e.differsFromUsual));
    add(`1-hour map on hourly contracts (${tag})`, m60);
    if (bot) { const b = pick(bot.entries); add(`Bot, 15-minute contracts (${tag})`, b.filter((e) => e.kind === '15m')); add(`Bot, hourly contracts (${tag})`, b.filter((e) => e.kind === 'hourly')); }
  }
  const rows = sets.map(([label, es]) => ({ label, ...summarize(es) }));
  const md = ['| Contender | Entries | Time slots | Window rate | Random side | Gap (pts ± SE) | Gap / SE | vs usual side | vs random minute | With bid size | At own fill price | Median secs to window | Median dip (c) | Left out (holes) |', '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|'];
  for (const r of rows) md.push(`| ${r.label} | ${r.n} | ${r.slots} | ${pct(r.rate)} | ${pct(r.randomSide)} | ${pts(r.gap, r.gapSe)} | ${Number.isFinite(r.z) ? r.z.toFixed(2) : 'n/a'} | ${pts(r.gapVsUsual, r.gapVsUsualSe)} | ${pts(r.gapVsRandomMinute, r.gapVsRandomMinuteSe)} | ${pct(r.rateDepth)} | ${pct(r.ownRate)} | ${Number.isFinite(r.medianToWindowSec!) ? r.medianToWindowSec : 'n/a'} | ${Number.isFinite(r.medianDipCents!) ? r.medianDipCents : 'n/a'} | ${r.incomplete} |`);
  const versus: Record<string, unknown> = {};
  if (bot) for (const kind of ['15m', 'hourly'] as const) {
    const h = heat.entries.filter((e) => e.first && e.kind === kind && e.contender === (kind === '15m' ? 'map15' : 'map60')), b = bot.entries.filter((e) => e.first && e.kind === kind);
    const cmp = compareGaps(h, b); versus[kind] = cmp;
    const hb = new Map(h.map((e) => [e.kind === '15m' ? e.ticker : e.contract, e])); let both = 0, same = 0;
    for (const e of b) { const x = hb.get(e.kind === '15m' ? e.ticker : `${e.asset}:${e.slot}`); if (x) { both++; same += Number(x.side === e.side); } }
    md.push('', `Heat map minus bot, ${kind === '15m' ? '15-minute' : 'hourly'} contracts (gap over random side, first entries): ${pts(cmp.diff, cmp.se)} points, ${Number.isFinite(cmp.z) ? cmp.z.toFixed(2) : 'n/a'} standard errors. Contracts both entered: ${both}; same side on ${same}.`);
  }
  const byCoin = ['BTC', 'ETH', 'SOL', 'XRP'].map((a) => ({ coin: a, map15: summarize(heat.entries.filter((e) => e.first && e.contender === 'map15' && e.asset === a)), map60: summarize(heat.entries.filter((e) => e.first && e.contender === 'map60' && e.asset === a)) }));
  md.push('', 'By coin, first entries (window rate, gap over random side): ' + byCoin.map((r) => `${r.coin} 15m ${pct(r.map15.rate)} ${pts(r.map15.gap, r.map15.gapSe)} (n ${r.map15.n}), 1h ${pct(r.map60.rate)} ${pts(r.map60.gap, r.map60.gapSe)} (n ${r.map60.n})`).join('; '));
  md.push('', `Calls that became no entry: ${JSON.stringify(heat.noEntry)}${bot ? `; bot fills not scored: ${JSON.stringify(bot.noEntry)}` : ''}.`);
  md.push(`Capture: ${c.forecasts.length} calls, ${c.markets.size} contracts watched, ${[...c.books.values()].reduce((a, s) => a + s.length, 0)} book samples.`);
  return { markdown: md.join('\n'), json: { from, to, rules: RULES, rows, versus, byCoin, noEntry: heat.noEntry, botNoEntry: bot?.noEntry } };
}

const arg = (name: string, fallback = '') => { const i = process.argv.indexOf(`--${name}`); return i < 0 ? fallback : process.argv[i + 1]; };
if (process.argv[1] && /(^|[/\\])score\.(ts|js)$/.test(process.argv[1])) {
  const c = loadCapture(arg('capture')), from = Date.parse(arg('from', '2026-11-11T00:00:00Z')), to = Date.parse(arg('to', new Date().toISOString()));
  const fills = arg('bot') && fs.existsSync(arg('bot')) ? lines(arg('bot')).map((l) => JSON.parse(l) as BotFill) : undefined;
  const r = report(c, fills, from, to);
  if (arg('out')) { fs.mkdirSync(arg('out'), { recursive: true }); fs.writeFileSync(path.join(arg('out'), 'score.md'), r.markdown + '\n'); fs.writeFileSync(path.join(arg('out'), 'score.json'), JSON.stringify(r.json, null, 2) + '\n'); }
  console.log(r.markdown);
}
