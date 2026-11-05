import assert from 'node:assert/strict';
import { test } from 'node:test';
import { evaluateFeeTier, parseFeeTierRates, parseFeeTiers, PerpFeeTierCheck } from '../bot/perps/feeTier';
import { KalshiPerpsRest } from '../bot/perps/perpRest';

// Kalshi's perps schedule (CFTC filing Jun 24 2026), first rows, as GET /margin/fee_tier_rates returns it.
const SCHEDULE = { fee_tier_rates: [
  { fee_schedule: 'fcm', tier: 0, maker_fee_rate: 0.0005, taker_fee_rate: 0.0012 },
  { fee_schedule: 'fcm', tier: 1, maker_fee_rate: 0.0004, taker_fee_rate: 0.001 },
  { fee_schedule: 'fcm', tier: 2, maker_fee_rate: 0.00032, taker_fee_rate: 0.0008 },
] };
const tier0 = { maker_fee_rates: { 'BTC-PERP': 0.0005, 'ETH-PERP': 0.0005 }, taker_fee_rates: { 'BTC-PERP': 0.0012, 'ETH-PERP': 0.0012 } };

test('fee tiers: rates are decimal fractions of notional, read as bps (numbers or numeric strings)', () => {
  assert.deepEqual(parseFeeTiers(tier0), [{ ticker: 'BTC-PERP', makerBps: 5, takerBps: 12 }, { ticker: 'ETH-PERP', makerBps: 5, takerBps: 12 }]);
  assert.deepEqual(parseFeeTiers({ maker_fee_rates: { 'SOL-PERP': '0.00032' }, taker_fee_rates: { 'SOL-PERP': '0.0008', 'XRP-PERP': 0.001 } }), [{ ticker: 'SOL-PERP', makerBps: 3.2, takerBps: 8 }], 'a market missing a side is left out');
  assert.deepEqual(parseFeeTiers({}), []);
  assert.deepEqual(parseFeeTiers(null), []);
  const rows = parseFeeTierRates(SCHEDULE);
  assert.deepEqual(rows.map((r) => [r.tier, r.makerBps, r.takerBps]), [[0, 5, 12], [1, 4, 10], [2, 3.2, 8]]);
  assert.deepEqual(parseFeeTierRates({ fee_tier_rates: [{ tier: 'x', maker_fee_rate: 1, taker_fee_rate: 1 }] }), []);
  assert.deepEqual(parseFeeTierRates({ fee_tier_rates: [{ tier: null, maker_fee_rate: 0.0003, taker_fee_rate: 0.0009 }, { tier: '', maker_fee_rate: 0.0003, taker_fee_rate: 0.0009 }] }), [], 'a missing tier is not tier 0');
});

test('fee tiers: tier 0 agrees with the bot defaults; the tier is named from the schedule', () => {
  const st = evaluateFeeTier(parseFeeTiers(tier0), parseFeeTierRates(SCHEDULE), { makerBps: 5, takerBps: 12, tickers: ['BTC-PERP'], at: 1 });
  assert.deepEqual(st.mismatches, []);
  assert.equal(st.rates.length, 1);
  assert.deepEqual([st.rates[0].takerTier, st.rates[0].makerTier, st.rates[0].tickers.length], ['tier 0', 'tier 0', 2]);
  assert.deepEqual(st.traded.map((t) => t.ticker), ['BTC-PERP']);
  assert.match(st.note, /taker 12 \/ maker 5 bps \(taker tier 0, maker tier 0\) on 2; the bot charges taker 12 \/ maker 5: they agree/);
});

test('fee tiers: a cheaper tier than the bot charges is a mismatch that names the tier', () => {
  const t1 = { maker_fee_rates: { 'BTC-PERP': 0.0004 }, taker_fee_rates: { 'BTC-PERP': 0.001 } };
  const st = evaluateFeeTier(parseFeeTiers(t1), parseFeeTierRates(SCHEDULE), { makerBps: 5, takerBps: 12, tickers: ['BTC-PERP', 'ETH-PERP'], at: 1 });
  assert.equal(st.mismatches.length, 1);
  assert.match(st.mismatches[0], /BTC-PERP: Kalshi charges this account taker 10 \/ maker 4 bps \(taker tier 1, maker tier 1\); the bot charges taker 12 \/ maker 5/);
  assert.deepEqual(st.missing, ['ETH-PERP']);
  // Maker reached by maker-volume share: taker and maker tiers differ.
  const mixed = evaluateFeeTier(parseFeeTiers({ maker_fee_rates: { 'BTC-PERP': 0.00032 }, taker_fee_rates: { 'BTC-PERP': 0.0012 } }), parseFeeTierRates(SCHEDULE), { makerBps: 5, takerBps: 12, at: 1 });
  assert.match(mixed.mismatches[0], /taker 12 \/ maker 3\.2 bps \(taker tier 0, maker tier 2\)/);
  assert.deepEqual(mixed.mismatchKeys, ['rates 3.2|12'], 'alerts key on the rates, not the wording');
  const unlisted = evaluateFeeTier(parseFeeTiers({ maker_fee_rates: { 'BTC-PERP': 0.00045 }, taker_fee_rates: { 'BTC-PERP': 0.0011 } }), parseFeeTierRates(SCHEDULE), { makerBps: 5, takerBps: 12, at: 1 });
  assert.match(unlisted.mismatches[0], /\(taker no schedule row, maker no schedule row\)/, 'a rate the schedule does not list is said so');
});

test('fee tiers: the bot only judges its own markets; rates outside the schedule and odd units are said so', () => {
  const fees = parseFeeTiers({ maker_fee_rates: { 'BTC-PERP': 0.0005, 'ZZZ-PERP': 0.0004 }, taker_fee_rates: { 'BTC-PERP': 0.0012, 'ZZZ-PERP': 0.001 } });
  assert.deepEqual(evaluateFeeTier(fees, [], { makerBps: 5, takerBps: 12, tickers: ['BTC-PERP'], at: 1 }).mismatches, [], 'another market at another rate is not the bot\'s');
  const all = evaluateFeeTier(fees, [], { makerBps: 5, takerBps: 12, tickers: [], at: 1, scheduleError: 'perps HTTP 403' });
  assert.equal(all.mismatches.length, 1, 'no feed yet: every listed market is compared');
  assert.match(all.mismatches[0], /^ZZZ-PERP: .*taker 10 \/ maker 4 bps;/);
  assert.match(all.note, /schedule not read \(perps HTTP 403\)/);
  const pct = evaluateFeeTier(parseFeeTiers({ maker_fee_rates: { 'BTC-PERP': 0.05 }, taker_fee_rates: { 'BTC-PERP': 0.12 } }), [], { makerBps: 5, takerBps: 12, at: 1 });
  assert.match(pct.mismatches[0], /above 100 bps: the rate may not be a fraction of notional/);
  const none = evaluateFeeTier([], [], { makerBps: 5, takerBps: 12, tickers: ['BTC-PERP'], at: 1 });
  assert.match(none.mismatches[0], /no perp market in this account's fee list/);
  const off = evaluateFeeTier(fees, [], { makerBps: 5, takerBps: 12, tickers: ['SOL-PERP'], at: 1 });
  assert.match(off.mismatches.at(-1)!, /none of the bot's perp markets \(SOL-PERP\) is in this account's fee list/);
});

test('fee tiers: the REST calls are signed GETs on the two endpoints; the check keeps the last good read', async () => {
  const calls: Array<{ url: string; method: string; signed: boolean }> = [];
  let fail = false;
  const fake = (async (url: string, init: any) => {
    calls.push({ url, method: init.method, signed: init.headers['KALSHI-ACCESS-KEY'] === 'k' });
    if (fail) return new Response('{"code":"internal"}', { status: 500 });
    const body = url.endsWith('/margin/fee_tiers') ? tier0 : url.endsWith('/margin/fee_tier_rates') ? SCHEDULE : {};
    return new Response(JSON.stringify(body), { status: 200 });
  }) as unknown as typeof fetch;
  const c = new KalshiPerpsRest('https://external-api.demo.kalshi.co/trade-api/v2', { headers: () => ({ 'KALSHI-ACCESS-KEY': 'k' }) } as any, fake);
  const check = new PerpFeeTierCheck(c, { makerBps: 5, takerBps: 12, tickers: () => ['BTC-PERP'], now: () => 42 });
  assert.match(String((check.status() as { note: string }).note), /not read yet/);
  const r = await check.run();
  assert.equal(r.error, undefined);
  assert.deepEqual(r.status!.mismatches, []);
  assert.deepEqual(calls.map((x) => [x.method, x.url.replace(/^.*trade-api\/v2/, ''), x.signed]).sort(), [['GET', '/margin/fee_tier_rates', true], ['GET', '/margin/fee_tiers', true]]);
  fail = true;
  const bad = await check.run();
  assert.match(bad.error!, /perps HTTP 500/);
  const s = check.status() as { at: number; markets: number; lastError?: { error: string } };
  assert.deepEqual([s.at, s.markets], [42, 2], 'the last good read stays');
  assert.match(s.lastError!.error, /HTTP 500/);
  // A refused schedule read keeps the last schedule; the rates are read fresh.
  let refuse = false;
  const keep = new PerpFeeTierCheck({ feeTiers: async () => tier0, feeTierRates: async () => { if (refuse) throw new Error('perps HTTP 429'); return SCHEDULE; } }, { makerBps: 5, takerBps: 12, tickers: () => ['BTC-PERP'] });
  await keep.run();
  refuse = true;
  const k2 = await keep.run();
  assert.equal(k2.status!.schedule.length, 3);
  assert.match(k2.status!.scheduleError!, /429/);
  // A read saved before a restart shows until the first read of this run.
  const fresh = new PerpFeeTierCheck({ feeTiers: async () => tier0, feeTierRates: async () => SCHEDULE }, { makerBps: 5, takerBps: 12, tickers: () => [] });
  fresh.seed(k2.status);
  assert.equal((fresh.status() as { markets: number }).markets, 2);
  fresh.seed({ junk: true } as any);
  // The schedule refused (403: not margin-enabled) still compares the account's rates.
  const partial = new PerpFeeTierCheck({ feeTiers: async () => tier0, feeTierRates: async () => { throw new Error('perps HTTP 403: not margin-enabled'); } }, { makerBps: 4, takerBps: 12, tickers: () => { throw new Error('feed down'); } });
  const p = await partial.run();
  assert.equal(p.status!.schedule.length, 0);
  assert.match(p.status!.scheduleError!, /403/);
  assert.equal(p.status!.mismatches.length, 1, 'maker 5 charged vs 4 configured, on every listed market (the feed threw)');
  assert.match(p.status!.mismatches[0], /^BTC-PERP, ETH-PERP: /);
});

test('fee tiers: config keys default on, every 6 h', async () => {
  const { loadConfig } = await import('../bot/config');
  const cfg = loadConfig({ TRADING_MODE: 'paper' } as NodeJS.ProcessEnv);
  assert.equal(cfg.perps.feeTierCheck, true);
  assert.equal(cfg.perps.feeTierHours, 6);
  const off = loadConfig({ TRADING_MODE: 'paper', PERP_FEE_TIER_CHECK: 'false', PERP_FEE_TIER_HOURS: '24' } as NodeJS.ProcessEnv);
  assert.deepEqual([off.perps.feeTierCheck, off.perps.feeTierHours], [false, 24]);
});
