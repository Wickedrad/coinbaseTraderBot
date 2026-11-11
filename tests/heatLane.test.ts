// The heat entry lane (bot/heat/heatLane.ts, heatBook.ts): the pure decision rule by rule, then the lane's book.
// Every test builds its case from the small helpers below: a row that fired, a coin's calls, a snapshot of the
// reader's file, a market as the engine shows it, and a book state.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import {
  HeatLane, decideCall, decideHeat, emptyHeatState, heatCallKey, heatStake, heatWeight,
  type HeatDecideInput, type HeatLaneState, type HeatPositionView, type HeatWindows,
} from '../bot/heat/heatLane';
import type { HeatCallRow, HeatCoinCalls, HeatConfig, HeatContext, HeatMarketView, HeatOpen, HeatSnapshot } from '../bot/heat/types';
import { tmpDir } from './helpers';

const S = 1000, MIN = 60 * S;
/** A bar closed at T0 (a minute boundary, 10:00 AM EST / 15:00 UTC); the engine looks five seconds later. */
const T0 = Date.UTC(2026, 10, 11, 15, 0, 0);
const NOW = T0 + 5 * S;

/** The lane's settings at their defaults (HEAT_* in the spec). */
const DEFAULTS = {
  enabled: true, callsFile: '', assets: ['BTC', 'ETH', 'SOL', 'XRP'], horizons: [15, 60], topN: 10, maxAgeSec: 90, entryLagSec: 45,
  sizing: true, context: 'size', contextBoost: 0.25, maxOpen: 2, maxPerCoin: 1, cooldownSec: 60, reenterAfterLoss: false,
  flatTrips: 30, pilotLossUsd: 15, feeNetCheck: false, perps: 'entry', pairConflict: 'skip',
};
const settings = (o: Partial<HeatConfig> = {}): HeatConfig => ({ ...DEFAULTS, ...o }) as HeatConfig;
/** The engine's default windows: 15-minute contracts 840..300 s before close, hourly 3300..600 s and 10c..90c. */
const WINDOWS: HeatWindows = { entryWindowUpdown: [840, 300], entryWindowHourly: [3300, 600], hourlyMidBand: [0.1, 0.9] };

/** A row that fired at T0: a 15-minute UP call, the coin's hottest, unless the test says otherwise. */
const row = (o: Partial<HeatCallRow> = {}): HeatCallRow => ({ key: '1m:RSI14=very low', kind: 'single', tf: 1, h: 15, dir: 1, rank: 1, of: 40, heat: 100, share: 0.53, odds: 3, barClose: T0, ...o });
/** The hour's call: a 60-minute row. */
const hourRow = (o: Partial<HeatCallRow> = {}): HeatCallRow => row({ key: '1m:ADX14=high', h: 60, ...o });
const coin = (calls: HeatCallRow[], o: Partial<HeatCoinCalls> = {}): HeatCoinCalls => ({ asOf: T0, tableSha: 'table', ok: true, calls, ...o });
/** The reader's file, written two seconds after the bar closed. A coin given as a list of rows is a healthy coin. */
const snap = (coins: Record<string, HeatCallRow[] | HeatCoinCalls>, o: Partial<HeatSnapshot> = {}): HeatSnapshot => ({
  source: 'oracle-heat', run: 'R1', packSha: 'pack', writtenAt: T0 + 2 * S,
  coins: new Map(Object.entries(coins).map(([k, v]) => [k, Array.isArray(v) ? coin(v) : v])), ...o,
});
/** The reader's file for a later bar: the same rows, fired at the bar that closed at `t`. */
const snapAt = (t: number, coins: Record<string, HeatCallRow[]>): HeatSnapshot => snap(
  Object.fromEntries(Object.entries(coins).map(([k, rows]) => [k, coin(rows.map((r) => ({ ...r, barClose: t })), { asOf: t })])),
  { writtenAt: t + 2 * S },
);

/** A coin's 15-minute contract, ten minutes from its close, quoted 49c bid / 51c ask, flat. */
const m15 = (asset = 'BTC', o: Partial<HeatMarketView> = {}): HeatMarketView => ({
  ticker: `KX${asset}15M-1015`, asset, kind: '15m', closeTs: NOW + 600 * S, openTs: NOW - 300 * S, yesBid: 0.49, yesAsk: 0.51, position: 0, working: 0, ...o,
});
/** An hourly strike half an hour from its close, quoted one cent either side of `mid`. */
const hourly = (strike: string, mid: number, o: Partial<HeatMarketView> = {}): HeatMarketView => ({
  ticker: `KXBTCH-${strike}`, asset: 'BTC', kind: 'hourly', closeTs: NOW + 1800 * S,
  yesBid: Math.round((mid - 0.01) * 100) / 100, yesAsk: Math.round((mid + 0.01) * 100) / 100, position: 0, working: 0, ...o,
});

const book = (o: Partial<HeatLaneState> = {}): HeatLaneState => ({ ...emptyHeatState(), ...o });
/** A book past its flat phase (decision 11), so the heat size and the second slot are in play. */
const seasoned = (o: Partial<HeatLaneState> = {}): HeatLaneState => book({ trips: 30, ...o });
const openPos = (asset: string, o: Partial<HeatOpen> = {}): HeatOpen => ({
  ticker: `KX${asset}15M-1015`, asset, kind: '15m', side: 'yes', ruleId: 'heat:R1', h: 15, sentAt: NOW - MIN, openedAt: NOW - MIN, stakeUsd: 10, closeTs: NOW + 600 * S, cash0: 0, fees0: 0, ...o,
});
const hourUp = (o: Partial<HeatContext> = {}): HeatContext => ({ asset: 'BTC', dir: 1, key: '1m:ADX14=high', rank: 2, of: 40, heat: 90, barClose: T0 - 10 * MIN, until: T0 + 50 * MIN, ...o });

/** One decision in paper with a $10..$20 order band, a seasoned book, and whatever the test changes. */
const decide = (o: Partial<HeatDecideInput> = {}) => decideHeat({
  now: NOW, cfg: settings(), snapshot: undefined, markets: [], state: seasoned(), orderMin: 10, orderMax: 20, minSide: 0.1, live: false, windows: WINDOWS, ...o,
});
/** BTC's hottest 15-minute row fired UP and its 15-minute contract is open: the plain case most tests start from. */
const btc15 = (o: Partial<HeatDecideInput> = {}, r: Partial<HeatCallRow> = {}) => decide({ snapshot: snap({ BTC: [row(r)] }), markets: [m15()], ...o });
const reasons = (r: { skips: Array<{ reason: string }> }) => r.skips.map((s) => s.reason);

// ---- The decided call ----

test('decided call: the hottest firing row, with the rows that fired and how many called the other side', () => {
  const d = decideCall('BTC', 15, [row({ key: 'b', rank: 4 }), row({ key: 'a', rank: 2 }), row({ key: 'c', rank: 7, dir: -1 })])!;
  assert.equal(d.row.key, 'a');
  assert.deepEqual([d.fired, d.against], [3, 1]);
});

test('decided call: a firing pair replaces the single it refines, even at a colder rank', () => {
  const single = row({ key: '1m:RSI14=very low', rank: 1 });
  const pair = row({ key: '1m:RSI14=very low+1h:ADX14=high', kind: 'pair', trig: '1m:RSI14=very low', rank: 6, dir: -1 });
  const d = decideCall('BTC', 15, [single, pair])!;
  assert.equal(d.row.key, pair.key);
  assert.equal(d.row.dir, -1, 'the pair speaks alone: nothing is averaged with the single');
  assert.deepEqual([d.fired, d.against], [2, 1]);
});

test('decided call: a triple replaces before a pair', () => {
  const single = row({ key: 's', rank: 1 });
  const pair = row({ key: 's+p', kind: 'pair', trig: 's', rank: 2 });
  const triple = row({ key: 's+p+t', kind: 'triple', trig: 's', rank: 9 });
  assert.equal(decideCall('BTC', 15, [single, pair, triple])!.row.key, 's+p+t');
});

test('decided call: a pair built on another single replaces nothing', () => {
  const other = row({ key: 'x+p', kind: 'pair', trig: 'x', rank: 5 });
  assert.equal(decideCall('BTC', 15, [row({ key: 's', rank: 1 }), other])!.row.key, 's');
});

test('decided call: an alias is the same event, never a second row and never against', () => {
  const rsi = row({ key: '1m:RSI14=high', aliases: ['1m:CMO14=high'], rank: 2, dir: -1 });
  const cmo = row({ key: '1m:CMO14=high', aliases: ['1m:RSI14=high'], rank: 3, dir: 1 });
  const d = decideCall('BTC', 15, [rsi, cmo])!;
  assert.equal(d.row.key, '1m:RSI14=high');
  assert.deepEqual([d.fired, d.against], [1, 0]);
});

// ---- Pairs and triples (Addendum 2) ----

/** A pair that refines BTC's hottest 15-minute single, ranked `rank` on the single ladder. */
const pairOf = (trig: string, o: Partial<HeatCallRow> = {}): HeatCallRow => row({ key: `${trig}+1h:ADX14=high`, kind: 'pair', trig, rank: 25, heat: 60, ...o });

test('pairs: a refining pair replaces the decided single even ranked beyond HEAT_TOP_N, and keeps the single\'s rank', () => {
  const single = row({ key: 's', rank: 3 });
  const d = decideCall('BTC', 15, [single, pairOf('s', { rank: 25 })], 10)!;
  assert.equal(d.row.key, 's+1h:ADX14=high');
  assert.equal(d.row.rank, 3, 'rank = min(single 3, pair 25)');
  assert.equal(d.single?.key, 's');
  assert.deepEqual([d.fired, d.against], [2, 0], 'the pair beyond the batch counts as a row that fired');
  // Through the lane: it trades the pair's key at the single's weight.
  const [p] = decide({ snapshot: snap({ BTC: [single, pairOf('s', { rank: 25 })] }), markets: [m15()] }).plans;
  assert.equal(p.ruleId, 'heat:R1:BTC:h15:s+1h:ADX14=high');
  assert.equal(p.weight, 0.7778, 'the weight of rank 3 in a batch of 10');
  // A pair hotter than its single keeps its own rank.
  assert.equal(decideCall('BTC', 15, [single, pairOf('s', { rank: 1 })], 10)!.row.rank, 1);
});

test('pairs: the trigger may be one of the single\'s aliases', () => {
  const single = row({ key: '1m:RSI14=high', aliases: ['1m:CMO14=high'], rank: 2 });
  const d = decideCall('BTC', 15, [single, pairOf('1m:CMO14=high')], 10)!;
  assert.equal(d.row.key, '1m:CMO14=high+1h:ADX14=high');
});

test('pairs: a triple replaces before a pair, then the higher heat', () => {
  const single = row({ key: 's', rank: 1 });
  const rows = [single, pairOf('s', { key: 'p1', heat: 90 }), pairOf('s', { key: 'p2', heat: 95 }), pairOf('s', { key: 't', kind: 'triple', heat: 10, rank: 40 })];
  assert.equal(decideCall('BTC', 15, rows, 10)!.row.key, 't');
  assert.equal(decideCall('BTC', 15, rows.slice(0, 3), 10)!.row.key, 'p2', 'two pairs: the hotter');
});

test('pairs: against its single, HEAT_PAIR_CONFLICT=skip (default) gives no entry and no hour context', () => {
  const single = row({ key: 's', rank: 2 });
  const down = pairOf('s', { dir: -1 });
  const r = decide({ snapshot: snap({ BTC: [single, down] }), markets: [m15()] });
  assert.equal(r.plans.length, 0);
  assert.equal(r.decided.length, 1, 'still ruled on, once');
  assert.match(reasons(r)[0], /^pair against single: s\+1h:ADX14=high calls down, its single s up/);
  // The hour's call in conflict sets no context and is never what the perps side sees.
  const hr = decide({ snapshot: snap({ BTC: [hourRow({ key: 'h', rank: 2 }), pairOf('h', { h: 60, dir: -1 })] }) });
  assert.deepEqual([hr.contexts, hr.calls], [[], []]);
  const lane = new HeatLane(settings());
  lane.decide(NOW, snap({ BTC: [hourRow({ key: 'h', rank: 2 }), pairOf('h', { h: 60, dir: -1 })] }), [], { orderMin: 10, orderMax: 20, minSide: 0.1, live: false, windows: WINDOWS });
  assert.equal(lane.fired('BTC', 60, NOW), undefined);
  assert.equal(lane.hour('BTC', NOW), undefined);
});

test('pairs: HEAT_PAIR_CONFLICT=pair trades the pair\'s side', () => {
  const r = decide({ cfg: settings({ pairConflict: 'pair' }), snapshot: snap({ BTC: [row({ key: 's', rank: 2 }), pairOf('s', { dir: -1 })] }), markets: [m15()] });
  assert.deepEqual(r.plans.map((p) => [p.side, p.row.key, p.row.rank]), [['no', 's+1h:ADX14=high', 2]]);
  assert.equal(r.decided[0].against, 1, 'the single counts against the pair');
});

test('pairs: a pair whose trigger is not the decided single trades on its own only inside HEAT_TOP_N', () => {
  // Its trigger did not fire at all.
  assert.equal(decideCall('BTC', 15, [pairOf('x', { rank: 11 })], 10), undefined);
  assert.equal(decideCall('BTC', 15, [pairOf('x', { rank: 7 })], 10)!.row.key, 'x+1h:ADX14=high');
  // Its trigger fired beyond the batch: that single is not the decided one, so the pair stands alone.
  assert.equal(decideCall('BTC', 15, [row({ key: 'x', rank: 12 }), pairOf('x', { rank: 30 })], 10), undefined);
  // Beside a decided single: the hotter of the two.
  const d = decideCall('BTC', 15, [row({ key: 's', rank: 5 }), pairOf('x', { rank: 4 })], 10)!;
  assert.equal(d.row.key, 'x+1h:ADX14=high');
  assert.equal(d.single, undefined, 'it replaced nothing');
  assert.equal(decideCall('BTC', 15, [row({ key: 's', rank: 3 }), pairOf('x', { rank: 4 })], 10)!.row.key, 's');
});

test('pairs: an alias of a pair is the same event, never a second row', () => {
  const p = pairOf('s', { key: 'a', aliases: ['b'] });
  const twin = pairOf('s', { key: 'b', aliases: ['a'], dir: -1 });
  const d = decideCall('BTC', 15, [row({ key: 's', rank: 1 }), p, twin], 10)!;
  assert.deepEqual([d.fired, d.against], [2, 0]);
});

test('fired rows: only inside the entry lag after the bar closed', () => {
  const at = (now: number) => btc15({ now, markets: [m15('BTC', { closeTs: now + 600 * S })] }).plans.length;
  assert.equal(at(T0), 1, 'the moment the bar closed');
  assert.equal(at(T0 + 45 * S), 1, 'the last second of the lag');
  assert.equal(at(T0 + 46 * S), 0, 'too late');
  assert.equal(at(T0 - S), 0, 'a bar that has not closed yet');
});

test('fired rows: a row ranked past HEAT_TOP_N does not trade, and 0 takes every row of the pack', () => {
  assert.equal(btc15({}, { rank: 11 }).decided.length, 0);
  assert.equal(btc15({ cfg: settings({ topN: 0 }) }, { rank: 11 }).plans.length, 1);
});

test('fired rows: each horizon decides from its own rows', () => {
  const r = decide({ snapshot: snap({ BTC: [row({ key: 'five', h: 5, rank: 1 }), row({ key: 'fifteen', rank: 3 })] }), markets: [m15()] });
  assert.deepEqual(r.decided.map((d) => [d.h, d.row.key]), [[15, 'fifteen']]);
});

// ---- When the calls cannot be trusted ----

test('no calls file: nothing is decided and the status text says so', () => {
  const r = decide({ markets: [m15()] });
  assert.deepEqual([r.decided, r.plans, r.skips], [[], [], []]);
  assert.match(r.notes.join(), /no calls file/);
});

test('stale file: one written more than twice HEAT_MAX_AGE_SEC ago is ignored altogether', () => {
  const r = btc15({ snapshot: snap({ BTC: [row()] }, { writtenAt: NOW - 181 * S }) });
  assert.deepEqual([r.decided, r.plans, r.skips, r.calls], [[], [], [], []]);
  assert.match(r.notes.join(), /calls file ignored/);
});

test('stale coin: last closed minute older than HEAT_MAX_AGE_SEC gives a skip with the reason, no entry, no context', () => {
  const r = decide({ snapshot: snap({ BTC: coin([row(), hourRow()], { asOf: NOW - 91 * S }) }), markets: [m15()] });
  assert.equal(r.plans.length, 0);
  assert.equal(r.contexts.length, 0);
  assert.deepEqual(r.decided.map((d) => d.h), [15, 60]);
  for (const reason of reasons(r)) assert.match(reason, /calls stale/);
});

test('coin not ok: the reader cannot vouch for it, so its calls are skipped with the reader\'s reason', () => {
  const r = decide({ snapshot: snap({ BTC: coin([row()], { ok: false, why: 'minute gap' }), ETH: [row()] }), markets: [m15('BTC'), m15('ETH')] });
  assert.deepEqual(r.plans.map((p) => p.asset), ['ETH']);
  assert.deepEqual(r.skips.map((s) => [s.asset, s.reason]), [['BTC', 'reader not ok: minute gap']]);
});

test('DOGE is refused even when the settings list it', () => {
  const r = decide({ cfg: settings({ assets: ['DOGE', 'BTC'] }), snapshot: snap({ DOGE: [row()], BTC: [row()] }), markets: [m15('DOGE'), m15('BTC')] });
  assert.deepEqual(r.decided.map((d) => d.asset), ['BTC']);
  assert.deepEqual(r.plans.map((p) => p.asset), ['BTC']);
  assert.match(r.notes.join(), /DOGE/);
});

test('a coin the settings do not list is not traded', () => {
  const r = decide({ cfg: settings({ assets: ['ETH'] }), snapshot: snap({ BTC: [row()] }), markets: [m15()] });
  assert.equal(r.decided.length, 0);
});

// ---- The 15-minute contract ----

test('15-minute contract: UP buys YES at the ask', () => {
  const [p] = btc15().plans;
  assert.deepEqual([p.ticker, p.kind, p.h, p.side, p.price, p.sideCost], ['KXBTC15M-1015', '15m', 15, 'yes', 0.51, 0.51]);
  assert.equal(p.ruleId, 'heat:R1:BTC:h15:1m:RSI14=very low');
  assert.equal(p.why, 'heat BTC 15m up 1m:RSI14=very low rank 1/10 ctx none');
  assert.equal(p.fair, 0.53, 'YES mid 0.50 moved 3 points toward the called side');
});

test('15-minute contract: DOWN buys NO at the bid', () => {
  const [p] = btc15({}, { dir: -1 }).plans;
  assert.deepEqual([p.side, p.price, p.sideCost, p.fair], ['no', 0.49, 0.51, 0.47]);
  assert.match(p.why, /^heat BTC 15m down /);
});

test('15-minute contract: only inside the entry window', () => {
  const closingIn = (sec: number) => btc15({ markets: [m15('BTC', { closeTs: NOW + sec * S })] });
  assert.equal(closingIn(841).plans.length, 0);
  assert.equal(closingIn(840).plans.length, 1);
  assert.equal(closingIn(300).plans.length, 1);
  assert.match(reasons(closingIn(299))[0], /no BTC 15m market inside the entry window/);
});

test('fair value stays inside 1c..99c', () => {
  const [p] = btc15({ markets: [m15('BTC', { yesBid: 0.86, yesAsk: 0.88 })] }, { odds: 40 }).plans;
  assert.equal(p.fair, 0.99);
});

// ---- The hour as context ----

test('context agree: the hour calls the same side, the weight gets the boost (never above 1)', () => {
  const r = btc15({ state: seasoned({ context: { BTC: hourUp() } }) }, { rank: 4 });
  assert.deepEqual([r.plans[0].context, r.plans[0].weight], ['agree', 0.9167]);
  assert.equal(btc15({ state: seasoned({ context: { BTC: hourUp() } }) }, { rank: 2 }).plans[0].weight, 1);
});

test('context against: the hour calls the other side, the entry goes at ORDER_USD_MIN', () => {
  const [p] = btc15({ state: seasoned({ context: { BTC: hourUp({ dir: -1 }) } }) }).plans;
  assert.deepEqual([p.context, p.weight, p.stakeUsd], ['against', 0, 10]);
});

test('context block: with HEAT_CONTEXT=block an entry against the hour is not made', () => {
  const r = btc15({ cfg: settings({ context: 'block' }), state: seasoned({ context: { BTC: hourUp({ dir: -1 }) } }) });
  assert.equal(r.plans.length, 0);
  assert.match(reasons(r)[0], /hour's direction is against it/);
});

test('context none: no hour call, the weight is the rank\'s own', () => {
  const [p] = btc15({}, { rank: 4 }).plans;
  assert.deepEqual([p.context, p.weight], ['none', 0.6667]);
});

test('context off: the hour is not consulted', () => {
  const [p] = btc15({ cfg: settings({ context: 'off' }), state: seasoned({ context: { BTC: hourUp({ dir: -1 }) } }) }).plans;
  assert.deepEqual([p.context, p.weight], ['n/a', 1]);
});

test('a context is used only until its hour is over', () => {
  const [p] = btc15({ state: seasoned({ context: { BTC: hourUp({ dir: -1, until: NOW }) } }) }).plans;
  assert.equal(p.context, 'none');
});

test('the hour call of the same minute is the context of the 15-minute call', () => {
  const r = decide({ cfg: settings({ horizons: [15] }), snapshot: snap({ BTC: [row({ rank: 4 }), hourRow({ rank: 2 })] }), markets: [m15()] });
  assert.equal(r.plans[0].context, 'agree');
});

test('hour context: every decided 60-minute call is recorded for an hour, traded or not', () => {
  const r = decide({ snapshot: snap({ BTC: [hourRow({ rank: 2, heat: 88, dir: -1 })] }) });
  assert.equal(r.plans.length, 0, 'no hourly market to trade');
  assert.deepEqual(r.contexts, [{ asset: 'BTC', dir: -1, key: '1m:ADX14=high', rank: 2, of: 40, heat: 88, barClose: T0, until: T0 + 60 * MIN }]);
});

test('a 60-minute call outside HEAT_HORIZONS is context only: recorded, skipped with that reason', () => {
  const r = decide({ cfg: settings({ horizons: [15] }), snapshot: snap({ BTC: [hourRow()] }), markets: [hourly('A', 0.5)] });
  assert.equal(r.contexts.length, 1);
  assert.match(reasons(r)[0], /context only/);
});

test('a horizon no contract trades is skipped with that reason', () => {
  const r = decide({ cfg: settings({ horizons: [15, 30] }), snapshot: snap({ BTC: [row({ h: 30 })] }), markets: [m15()] });
  assert.deepEqual(reasons(r), ['no contract trades the 30-minute horizon']);
});

// ---- The hourly contract ----

test('hourly contract: the strike whose YES mid is nearest 50c', () => {
  const r = decide({ snapshot: snap({ BTC: [hourRow()] }), markets: [hourly('A', 0.3), hourly('B', 0.46), hourly('C', 0.7)] });
  const [p] = r.plans;
  assert.deepEqual([p.ticker, p.kind, p.h, p.side, p.price, p.context], ['KXBTCH-B', 'hourly', 60, 'yes', 0.47, 'n/a']);
});

test('hourly contract: equally near 50c, the nearer close wins, then the ticker order', () => {
  const pick = (markets: HeatMarketView[]) => decide({ snapshot: snap({ BTC: [hourRow()] }), markets }).plans[0].ticker;
  assert.equal(pick([hourly('Z', 0.45), hourly('Y', 0.55, { closeTs: NOW + 1200 * S })]), 'KXBTCH-Y');
  assert.equal(pick([hourly('Z', 0.45), hourly('Y', 0.55)]), 'KXBTCH-Y');
});

test('hourly contract: strikes outside the window, outside the mid band or without a two-sided book are not picked', () => {
  const r = decide({
    snapshot: snap({ BTC: [hourRow()] }),
    markets: [hourly('LATE', 0.5, { closeTs: NOW + 599 * S }), hourly('EARLY', 0.5, { closeTs: NOW + 3301 * S }), hourly('ONE', 0.5, { yesAsk: undefined }), hourly('FAR', 0.95), hourly('OK', 0.8)],
  });
  assert.deepEqual(r.plans.map((p) => p.ticker), ['KXBTCH-OK']);
});

test('hourly contract: no strike fits, the call is skipped with the reason', () => {
  const r = decide({ snapshot: snap({ BTC: [hourRow()] }), markets: [hourly('FAR', 0.95)] });
  assert.match(reasons(r)[0], /no BTC hourly market with a two-sided book and a mid inside 0\.10\.\.0\.90/);
});

// ---- A market qualifies only if ----

test('qualify: a 15-minute contract without a two-sided book is not entered', () => {
  assert.deepEqual(reasons(btc15({ markets: [m15('BTC', { yesBid: undefined })] })), ['no two-sided book']);
});

test('qualify: the called side must cost between RISK_MIN_SIDE_PRICE and one minus it', () => {
  const cheapNo = btc15({ markets: [m15('BTC', { yesBid: 0.92, yesAsk: 0.94 })] }, { dir: -1 });
  assert.match(reasons(cheapNo)[0], /no side costs 0\.08, outside 0\.10\.\.0\.90/);
  const dearYes = btc15({ markets: [m15('BTC', { yesBid: 0.9, yesAsk: 0.92 })] });
  assert.match(reasons(dearYes)[0], /yes side costs 0\.92/);
  assert.equal(btc15({ markets: [m15('BTC', { yesBid: 0.88, yesAsk: 0.9 })] }).plans.length, 1, 'exactly at the limit is in');
});

test('qualify: a position of any lane blocks, on either side', () => {
  assert.match(reasons(btc15({ markets: [m15('BTC', { position: 3 })] }))[0], /already holds a position/);
  assert.match(reasons(btc15({ markets: [m15('BTC', { position: -3 })] }))[0], /already holds a position/);
});

test('qualify: resting orders of ours do not block (the engine cancels them first)', () => {
  assert.equal(btc15({ markets: [m15('BTC', { working: 2 })] }).plans.length, 1);
});

test('qualify: the engine\'s block reason is passed on as the skip reason', () => {
  const r = btc15({ markets: [m15('BTC', { blocked: 'fee schedule unverified' })] });
  assert.deepEqual(r.skips, [{ asset: 'BTC', h: 15, ticker: 'KXBTC15M-1015', key: '1m:RSI14=very low', reason: 'fee schedule unverified' }]);
});

test('loss ticker: a contract the lane left at a loss is not entered again', () => {
  const lost = { lossTickers: { 'KXBTC15M-1015': NOW + 600 * S } };
  assert.match(reasons(btc15({ state: seasoned(lost) }))[0], /left this contract at a loss/);
  assert.equal(btc15({ state: seasoned(lost), cfg: settings({ reenterAfterLoss: true }) }).plans.length, 1, 'unless HEAT_REENTER_AFTER_LOSS');
});

test('re-entry: a contract already traded is entered again only while more than half of its window is left', () => {
  const again = (secToClose: number) => btc15({
    state: seasoned({ traded: { 'KXBTC15M-1015': NOW + secToClose * S } }),
    markets: [m15('BTC', { closeTs: NOW + secToClose * S, openTs: NOW + (secToClose - 900) * S })],
  });
  assert.equal(again(451).plans.length, 1);
  assert.match(reasons(again(450))[0], /already traded this contract/);
});

// ---- Limits ----

test('per-coin limit: a coin with an open heat position gets no entry', () => {
  const r = btc15({ state: seasoned({ open: [openPos('BTC', { ticker: 'KXBTCH-A', kind: 'hourly', h: 60 })] }) });
  assert.deepEqual(reasons(r), ['BTC already has an open heat position']);
});

test('per-coin limit: the 15-minute and the hourly call both qualify, the higher weight wins', () => {
  const r = decide({ snapshot: snap({ BTC: [row({ rank: 6 }), hourRow({ rank: 2, dir: -1 })] }), markets: [m15(), hourly('A', 0.5)], cfg: settings({ context: 'off' }) });
  assert.deepEqual(r.plans.map((p) => p.kind), ['hourly']);
  assert.deepEqual(r.skips.map((s) => [s.h, s.reason]), [[15, 'BTC has a hotter call this minute (one entry per coin)']]);
});

test('per-coin limit: equal weights, the 15-minute contract wins', () => {
  const r = decide({ snapshot: snap({ BTC: [hourRow({ rank: 3 }), row({ rank: 3 })] }), markets: [m15(), hourly('A', 0.5)], cfg: settings({ context: 'off' }) });
  assert.deepEqual(r.plans.map((p) => p.kind), ['15m']);
  assert.deepEqual(r.skips.map((s) => s.h), [60]);
});

test('per-coin limit of two: the hourly contract may open beside the coin\'s 15-minute position, as slot 2', () => {
  const r = decide({ cfg: settings({ maxPerCoin: 2 }), snapshot: snap({ BTC: [hourRow()] }), markets: [hourly('A', 0.5)], state: seasoned({ open: [openPos('BTC')] }) });
  assert.deepEqual(r.plans.map((p) => [p.kind, p.slot, p.stakeUsd]), [['hourly', 2, 10]]);
});

test('per-coin limit of two: never a second entry on a contract whose first is still out', () => {
  const r = btc15({ cfg: settings({ maxPerCoin: 2 }), state: seasoned({ open: [openPos('BTC', { openedAt: undefined })] }) });
  assert.deepEqual(reasons(r), ['a heat entry on this contract is already out']);
});

test('cooldown: no entry on a coin within HEAT_COOLDOWN_SEC of its last heat exit', () => {
  assert.match(reasons(btc15({ state: seasoned({ lastExit: { BTC: NOW - 59 * S } }) }))[0], /cooldown/);
  assert.equal(btc15({ state: seasoned({ lastExit: { BTC: NOW - 60 * S } }) }).plans.length, 1);
  assert.equal(btc15({ state: seasoned({ lastExit: { ETH: NOW - S } }) }).plans.length, 1, 'another coin\'s exit does not count');
});

test('once per call: a call already claimed is never ruled on again', () => {
  const first = btc15();
  assert.deepEqual(first.acted, { [heatCallKey('BTC', 15, T0)]: T0 });
  const second = btc15({ now: NOW + S, state: seasoned({ acted: first.acted }) });
  assert.deepEqual([second.decided, second.plans, second.skips, second.acted], [[], [], [], {}]);
  assert.equal(second.calls.length, 1, 'still firing, for the perps side to read');
});

test('once per call: a skipped call is claimed too', () => {
  const r = btc15({ markets: [] });
  assert.equal(r.skips.length, 1);
  assert.deepEqual(Object.keys(r.acted), ['BTC:15:' + T0]);
});

/** Three coins fire in the same minute at ranks 1, 4 and 7, each with its 15-minute contract open. */
const threeCoins = (o: Partial<HeatDecideInput> = {}) => decide({
  snapshot: snap({ SOL: [row({ rank: 7 })], BTC: [row({ rank: 1 })], ETH: [row({ rank: 4 })] }),
  markets: [m15('BTC'), m15('ETH'), m15('SOL')], ...o,
});

test('decision 8, nothing open: the hottest is slot 1 at heat size, the next slot 2 at ORDER_USD_MIN, no third', () => {
  const r = threeCoins();
  assert.deepEqual(r.plans.map((p) => [p.asset, p.slot, p.stakeUsd]), [['BTC', 1, 20], ['ETH', 2, 10]]);
  assert.deepEqual(r.skips.map((s) => s.asset), ['SOL']);
  assert.match(reasons(r)[0], /no slot left/);
});

test('decision 8, one open: the only plan is slot 2', () => {
  const r = threeCoins({ state: seasoned({ open: [openPos('XRP')] }) });
  assert.deepEqual(r.plans.map((p) => [p.asset, p.slot, p.stakeUsd]), [['BTC', 2, 10]]);
  assert.equal(r.skips.length, 2);
});

test('decision 8, two open: no entry, and an hourly position counts', () => {
  const r = threeCoins({ state: seasoned({ open: [openPos('XRP'), openPos('XRP', { ticker: 'KXXRPH-A', kind: 'hourly', h: 60 })] }) });
  assert.equal(r.plans.length, 0);
  assert.deepEqual(reasons(r), Array(3).fill('2 heat positions open (HEAT_MAX_OPEN 2)'));
});

test('decision 8: equal weights go by the better rank, then by the order the coins are listed in', () => {
  // ETH at rank 1 and BTC at rank 3 with the hour agreeing both weigh 1: the better rank goes first.
  const byRank = decide({ snapshot: snap({ BTC: [row({ rank: 3 })], ETH: [row({ rank: 1 })] }), markets: [m15('BTC'), m15('ETH')], state: seasoned({ context: { BTC: hourUp() } }) });
  assert.deepEqual(byRank.plans.map((p) => [p.asset, p.weight]), [['ETH', 1], ['BTC', 1]]);
  const byList = decide({ snapshot: snap({ ETH: [row({ rank: 3 })], BTC: [row({ rank: 3 })] }), markets: [m15('ETH'), m15('BTC')] });
  assert.deepEqual(byList.plans.map((p) => p.asset), ['BTC', 'ETH']);
});

test('flat phase (decision 11): before HEAT_FLAT_TRIPS trips, one position at a time and every stake ORDER_USD_MIN', () => {
  const r = threeCoins({ state: book({ trips: 29 }) });
  assert.deepEqual(r.plans.map((p) => [p.asset, p.slot, p.stakeUsd, p.weight]), [['BTC', 1, 10, 1]]);
  assert.match(reasons(r)[0], /flat phase \(29 of 30 trips done\)/);
  assert.equal(threeCoins({ state: book({ trips: 29, open: [openPos('XRP')] }) }).plans.length, 0);
});

test('pilot budget: in live no heat entry once the heat P&L is down HEAT_PILOT_LOSS_USD', () => {
  const r = btc15({ live: true, state: seasoned({ pnl: -15 }) });
  assert.equal(r.plans.length, 0);
  assert.match(reasons(r)[0], /pilot budget spent: heat P&L -15\.00, limit -15\.00/);
  assert.equal(btc15({ live: true, state: seasoned({ pnl: -14.99 }) }).plans.length, 1);
});

test('pilot budget: paper never stops on it, and 0 turns it off in live', () => {
  assert.equal(btc15({ live: false, state: seasoned({ pnl: -40 }) }).plans.length, 1);
  assert.equal(btc15({ live: true, state: seasoned({ pnl: -40 }), cfg: settings({ pilotLossUsd: 0 }) }).plans.length, 1);
});

test('entries blocked: every decided call becomes a skip with that reason, and the hour context is still kept', () => {
  const r = decide({ snapshot: snap({ BTC: [row(), hourRow()], ETH: [row()] }), markets: [m15('BTC'), m15('ETH'), hourly('A', 0.5)], entriesBlocked: 'no exit owner' });
  assert.equal(r.plans.length, 0);
  assert.deepEqual(r.skips.map((s) => [s.asset, s.h, s.reason]), [['BTC', 15, 'no exit owner'], ['BTC', 60, 'no exit owner'], ['ETH', 15, 'no exit owner']]);
  assert.equal(r.contexts.length, 1);
});

test('lane off: no entry is planned, the calls are still recorded', () => {
  const r = btc15({ cfg: settings({ enabled: false }) });
  assert.deepEqual([r.plans.length, reasons(r)], [0, ['heat lane off (HEAT_LANE)']]);
});

test('every decided call yields exactly one plan or one skip', () => {
  const r = decide({
    snapshot: snap({ BTC: [row(), hourRow({ rank: 5 })], ETH: [row({ rank: 2 })], SOL: [row({ rank: 3 })], XRP: coin([row()], { ok: false }) }),
    markets: [m15('BTC'), hourly('A', 0.5), m15('ETH'), m15('SOL', { position: 1 })],
  });
  assert.equal(r.decided.length, 5);
  const ruled = [...r.plans, ...r.skips].map((x) => `${x.asset}:${x.h}`).sort();
  assert.deepEqual(ruled, r.decided.map((d) => `${d.asset}:${d.h}`).sort());
});

test('decideHeat is pure: the book state it is given is not changed', () => {
  const state = seasoned({ context: { BTC: hourUp() } });
  const before = structuredClone(state);
  decide({ snapshot: snap({ BTC: [row(), hourRow()] }), markets: [m15(), hourly('A', 0.5)], state });
  assert.deepEqual(state, before);
});

// ---- Weight and stake (E07) ----

test('weight: 1 at rank 1, 0 at the last row of the batch and beyond it', () => {
  assert.equal(heatWeight(1, 40, 10), 1);
  assert.equal(heatWeight(10, 40, 10), 0);
  assert.equal(heatWeight(12, 40, 10), 0, 'a row past the batch never weighs below 0');
  assert.equal(heatWeight(5.5, 40, 10), 0.5);
});

test('weight: the hottest tenth of the batch is the peak, and the batch is never larger than the pack lists', () => {
  assert.deepEqual([1, 4, 5, 40, 45].map((rank) => heatWeight(rank, 40, 0)), [1, 1, 35 / 36, 0, 0], 'no HEAT_TOP_N: the 40 the pack lists, peak 4');
  assert.equal(heatWeight(3, 30, 0), 1, 'a batch of 30 has a peak of 3, not 4');
  assert.equal(heatWeight(5, 5, 10), 0, 'the pack lists 5: rank 5 is its last row');
  assert.equal(heatWeight(1, 1, 10), 1, 'a batch of one is all peak');
});

test('stake: heat size only for slot 1 past the flat phase with HEAT_SIZING on, else ORDER_USD_MIN', () => {
  const cfg = { sizing: true, flatTrips: 30 };
  assert.equal(heatStake(0.5, 1, 30, cfg, 10, 20), 15);
  assert.equal(heatStake(0.5, 2, 30, cfg, 10, 20), 10);
  assert.equal(heatStake(0.5, 1, 29, cfg, 10, 20), 10);
  assert.equal(heatStake(0.5, 1, 30, { sizing: false, flatTrips: 30 }, 10, 20), 10);
});

test('whole contracts: the stake buys as many as fit at the touch, never a fraction', () => {
  assert.equal(btc15().plans[0].count, 39, '$20 at 51c');
  assert.equal(btc15({}, { rank: 10 }).plans[0].count, 19, '$10 at 51c');
  assert.equal(btc15({ markets: [m15('BTC', { yesBid: 0.6, yesAsk: 0.62 })] }, { dir: -1, rank: 8 }).plans[0].count, 30, '$12.22 of NO at 40c');
});

test('whole contracts: at least one, even when the stake is below the price', () => {
  assert.equal(btc15({ orderMin: 0.3, orderMax: 0.3 }).plans[0].count, 1);
});

// ---- The lane: claims, contexts and the perps side ----

/** A stand-in for the position book: the lane only ever looks a market's row up by ticker. */
const positions = (rows: Record<string, HeatPositionView> = {}) => (ticker: string) => rows[ticker];
const OPTS = { orderMin: 10, orderMax: 20, minSide: 0.1, live: false, windows: WINDOWS };
const TICKER = 'KXBTC15M-1015';
/** A lane that has just sent BTC's 15-minute entry (19 YES at 51c, the flat phase's $10). */
function entered(lane = new HeatLane(settings())): HeatLane {
  const { plans } = lane.decide(NOW, snap({ BTC: [row()] }), [m15()], OPTS);
  lane.sent(plans[0], NOW, 0, 0);
  return lane;
}
/** The position book's row once the entry filled: 19 YES bought at 51c with a 17c fee. */
const FILLED: HeatPositionView = { yes: 19, netCash: -9.69, fees: 0.17 };
/** The lane with that entry seen open. */
function holding(lane = entered()): HeatLane {
  lane.sync(NOW + S, positions({ [TICKER]: FILLED }));
  return lane;
}

test('lane: a call is acted on once, however often the engine ticks', () => {
  const lane = new HeatLane(settings());
  const first = lane.decide(NOW, snap({ BTC: [row()] }), [m15()], OPTS);
  const second = lane.decide(NOW + S, snap({ BTC: [row()] }), [m15()], OPTS);
  assert.deepEqual([first.plans.length, second.decided.length, second.plans.length], [1, 0, 0]);
});

test('lane: the next bar\'s call is a new call', () => {
  const lane = new HeatLane(settings());
  lane.decide(NOW, snap({ BTC: [row()] }), [], OPTS);
  const next = lane.decide(NOW + MIN, snapAt(T0 + MIN, { BTC: [row()] }), [], OPTS);
  assert.equal(next.decided.length, 1);
});

test('lane: pending shows the calls not ruled on yet without claiming them', () => {
  const lane = new HeatLane(settings());
  const file = snap({ BTC: [row()] });
  assert.equal(lane.pending(NOW, file).length, 1);
  assert.equal(lane.pending(NOW, file).length, 1, 'looking claims nothing');
  lane.decide(NOW, file, [m15()], OPTS);
  assert.equal(lane.pending(NOW + S, file).length, 0);
});

test('perps side: hour() is the latest decided 60-minute call until its hour is over', () => {
  const lane = new HeatLane(settings());
  lane.decide(NOW, snap({ BTC: [hourRow({ dir: -1 })] }), [], { ...OPTS, entriesBlocked: 'soft pause' });
  assert.equal(lane.direction.hour('BTC', NOW)?.dir, -1);
  assert.equal(lane.direction.hour('BTC', T0 + 60 * MIN - 1)?.key, '1m:ADX14=high');
  assert.equal(lane.direction.hour('BTC', T0 + 60 * MIN), undefined);
  assert.equal(lane.direction.hour('ETH', NOW), undefined);
});

test('perps side: fired() returns the decided call inside the entry lag, after the engine has claimed it too', () => {
  const lane = new HeatLane(settings());
  lane.decide(NOW, snap({ BTC: [hourRow()] }), [hourly('A', 0.5)], OPTS);
  assert.equal(lane.direction.fired('BTC', 60, NOW + S)?.row.key, '1m:ADX14=high');
  assert.equal(lane.direction.fired('BTC', 60, T0 + 45 * S)?.row.dir, 1);
  assert.equal(lane.direction.fired('BTC', 60, T0 + 46 * S), undefined, 'the lag is over');
  assert.equal(lane.direction.fired('BTC', 15, NOW), undefined, 'no 15-minute call fired');
});

test('perps side: reading fired() does not consume the engine\'s claim', () => {
  const lane = new HeatLane(settings());
  const file = snap({ BTC: [hourRow()] });
  lane.pending(NOW, file);
  assert.ok(lane.direction.fired('BTC', 60, NOW));
  assert.equal(lane.decide(NOW, file, [hourly('A', 0.5)], OPTS).plans.length, 1);
});

test('perps side: there is no daily direction yet', () => {
  assert.equal(entered().direction.day('BTC', NOW), undefined);
});

// ---- The lane: the book ----

test('book: the lane holds a ticker from the moment its entry is sent', () => {
  const lane = new HeatLane(settings());
  assert.equal(lane.holds(TICKER), false);
  entered(lane);
  assert.equal(lane.holds(TICKER), true);
  assert.deepEqual(lane.status(NOW).open.map((o) => [o.ticker, o.side, o.sentAt, o.openedAt, o.closeTs]), [[TICKER, 'yes', NOW, undefined, NOW + 600 * S]]);
});

test('book: the entry is open once the position book shows the position', () => {
  const lane = entered();
  assert.deepEqual(lane.sync(NOW + S, positions({ [TICKER]: FILLED })), { opened: [TICKER], closed: [], dropped: [] });
  assert.equal(lane.status(NOW).open[0].openedAt, NOW + S);
  assert.deepEqual(lane.sync(NOW + 2 * S, positions({ [TICKER]: FILLED })).opened, [], 'reported once');
});

test('book: an entry never seen open within 30 s is dropped, and sync names it so its tag comes off', () => {
  const lane = entered();
  const flat = positions({ [TICKER]: { yes: 0, netCash: 0, fees: 0 } });
  assert.deepEqual(lane.sync(NOW + 30 * S, flat).dropped, [], 'still inside the 30 s');
  assert.deepEqual(lane.sync(NOW + 31 * S, flat), { opened: [], closed: [], dropped: [TICKER] });
  assert.equal(lane.holds(TICKER), false);
  assert.equal(lane.status(NOW).trips, 0, 'not a round trip');
});

test('book: an entry the book has no row for is dropped the same way', () => {
  const lane = entered();
  assert.deepEqual(lane.sync(NOW + 31 * S, positions()).dropped, [TICKER]);
});

test('book: drop() lets go of a rejected entry at once', () => {
  const lane = entered();
  assert.equal(lane.drop(TICKER), true);
  assert.equal(lane.holds(TICKER), false);
  assert.equal(lane.drop(TICKER), false, 'nothing left to drop');
});

test('book: drop() never lets go of a position already seen open', () => {
  const lane = holding();
  assert.equal(lane.drop(TICKER), false);
  assert.equal(lane.holds(TICKER), true);
});

test('book: flat again closes the round trip with the change in cash less the change in fees', () => {
  const lane = holding();
  // Sold 19 at 56c with another 17c fee.
  const res = lane.sync(NOW + 3 * MIN, positions({ [TICKER]: { yes: 0, netCash: 0.95, fees: 0.34 } }));
  assert.deepEqual(res.closed.map((c) => [c.ticker, c.pnl, c.settled]), [[TICKER, 0.61, false]]);
  const st = lane.status(NOW + 3 * MIN);
  assert.deepEqual([st.trips, st.wins, st.pnl, st.open.length], [1, 1, 0.61, 0]);
  assert.equal(lane.holds(TICKER), false);
});

test('book: the result is measured from the market\'s cash and fees when the entry was sent', () => {
  const lane = new HeatLane(settings());
  const { plans } = lane.decide(NOW, snap({ BTC: [row()] }), [m15()], OPTS);
  lane.sent(plans[0], NOW, 2, 0.5);
  lane.sync(NOW + S, positions({ [TICKER]: { yes: 19, netCash: 2 - 9.69, fees: 0.67 } }));
  const res = lane.sync(NOW + MIN, positions({ [TICKER]: { yes: 0, netCash: 2.95, fees: 0.84 } }));
  assert.equal(res.closed[0].pnl, 0.61);
});

test('book: a loss counts no win and marks the contract until its close', () => {
  const lane = holding();
  // Sold 19 at 45c.
  const res = lane.sync(NOW + 3 * MIN, positions({ [TICKER]: { yes: 0, netCash: -1.14, fees: 0.34 } }));
  assert.equal(res.closed[0].pnl, -1.48);
  const st = lane.status(NOW + 3 * MIN);
  assert.deepEqual([st.trips, st.wins, st.pnl], [1, 0, -1.48]);
  const again = lane.decide(NOW + 4 * MIN, snapAt(T0 + 4 * MIN, { BTC: [row()] }), [m15()], OPTS);
  assert.match(again.skips[0].reason, /left this contract at a loss/);
});

test('book: an exit starts the coin\'s cooldown', () => {
  const lane = holding();
  lane.sync(NOW + 3 * MIN, positions({ [TICKER]: { yes: 0, netCash: 0.95, fees: 0.34 } }));
  const soon = lane.decide(NOW + 3 * MIN + 30 * S, snapAt(T0 + 3 * MIN + 30 * S, { BTC: [row()] }), [m15()], OPTS);
  assert.match(soon.skips[0].reason, /cooldown/);
});

test('book: a settled market closes the round trip with the position book\'s realized figure', () => {
  const lane = holding();
  const res = lane.sync(NOW + 11 * MIN, positions({ [TICKER]: { yes: 0, netCash: -9.69, fees: 0.17, settled: true, realized: 9.14 } }));
  assert.deepEqual(res.closed.map((c) => [c.pnl, c.settled]), [[9.14, true]]);
  assert.deepEqual([lane.status(NOW).trips, lane.status(NOW).wins], [1, 1]);
});

test('book: a settled market without a realized figure uses its cash less its fees', () => {
  const lane = holding();
  const res = lane.sync(NOW + 11 * MIN, positions({ [TICKER]: { yes: 0, netCash: -9.69, fees: 0.17, settled: true } }));
  assert.equal(res.closed[0].pnl, -9.86);
});

test('book: an entry that filled and was sold between two looks is a round trip, not a drop', () => {
  const lane = entered();
  const res = lane.sync(NOW + S, positions({ [TICKER]: { yes: 0, netCash: 0.95, fees: 0.34 } }));
  assert.deepEqual([res.opened, res.closed.map((c) => c.pnl), res.dropped], [[TICKER], [0.61], []]);
});

test('book: a partly sold position stays open', () => {
  const lane = holding();
  const res = lane.sync(NOW + MIN, positions({ [TICKER]: { yes: 9, netCash: -4.09, fees: 0.26 } }));
  assert.deepEqual(res, { opened: [], closed: [], dropped: [] });
  assert.equal(lane.holds(TICKER), true);
});

test('book: the state is saved on every change and loaded at start', () => {
  const file = path.join(tmpDir(), 'heat_state.json');
  const lane = new HeatLane(settings(), file);
  const { plans } = lane.decide(NOW, snap({ BTC: [row(), hourRow()] }), [m15()], OPTS);
  assert.deepEqual(Object.keys(JSON.parse(fs.readFileSync(file, 'utf8')).acted).sort(), ['BTC:15:' + T0, 'BTC:60:' + T0], 'claims are on disk before any order goes out');
  lane.sent(plans[0], NOW, 0, 0);
  const restarted = new HeatLane(settings(), file);
  assert.equal(restarted.holds('KXBTC15M-1015'), true);
  assert.equal(restarted.hour('BTC', NOW)?.dir, 1);
  assert.equal(restarted.decide(NOW + S, snap({ BTC: [row(), hourRow()] }), [m15()], OPTS).decided.length, 0, 'the claims survived the restart');
});

test('book: a finished round trip survives a restart', () => {
  const file = path.join(tmpDir(), 'heat_state.json');
  const lane = holding(entered(new HeatLane(settings(), file)));
  lane.sync(NOW + 3 * MIN, positions({ [TICKER]: { yes: 0, netCash: -1.14, fees: 0.34 } }));
  const st = new HeatLane(settings(), file).status(NOW + 3 * MIN);
  assert.deepEqual([st.trips, st.wins, st.pnl, st.open.length], [1, 0, -1.48, 0]);
});

test('book: a file that is not a heat state stops the start instead of resetting the pilot budget', () => {
  const file = path.join(tmpDir(), 'heat_state.json');
  fs.writeFileSync(file, JSON.stringify({ v: 2, trips: 3 }));
  assert.throws(() => new HeatLane(settings(), file), /not a heat lane state file/);
});

test('book: old claims, finished contracts and hours that are over are pruned', () => {
  const file = path.join(tmpDir(), 'heat_state.json');
  const lane = holding(entered(new HeatLane(settings(), file)));
  lane.decide(NOW, snap({ BTC: [hourRow()] }), [], OPTS);
  lane.sync(NOW + 3 * MIN, positions({ [TICKER]: { yes: 0, netCash: -1.14, fees: 0.34 } }));
  const saved = () => JSON.parse(fs.readFileSync(file, 'utf8')) as HeatLaneState;
  assert.deepEqual([Object.keys(saved().acted).length, Object.keys(saved().lossTickers), Object.keys(saved().context)], [2, [TICKER], ['BTC']]);
  lane.sync(T0 + 2 * 60 * MIN + S, positions());
  assert.deepEqual([saved().acted, saved().lossTickers, saved().traded, saved().context], [{}, {}, {}, {}]);
  assert.equal(saved().trips, 1, 'the results stay');
});

test('lane: a plan without its close time takes the one the lane decided it with', () => {
  const lane = new HeatLane(settings());
  const { plans } = lane.decide(NOW, snap({ BTC: [row()] }), [m15()], OPTS);
  const { closeTs: _dropped, ...bare } = plans[0];
  lane.sent(bare, NOW, 0, 0);
  assert.equal(lane.status(NOW).open[0].closeTs, NOW + 600 * S);
});

test('lane: one alert when the live pilot budget is found spent', () => {
  const lane = new HeatLane(settings({ flatTrips: 0 }));
  // A $16 loss on the first trip: 39 YES bought at 51c, sold at 10c.
  const { plans } = lane.decide(NOW, snap({ BTC: [row()] }), [m15()], { ...OPTS, live: true });
  lane.sent(plans[0], NOW, 0, 0);
  lane.sync(NOW + S, positions({ [TICKER]: { yes: 39, netCash: -19.89, fees: 0.35 } }));
  lane.sync(NOW + 2 * MIN, positions({ [TICKER]: { yes: 0, netCash: -15.99, fees: 0.5 } }));
  const at = (min: number) => lane.decide(NOW + min * MIN, snapAt(T0 + min * MIN, { ETH: [row()] }), [m15('ETH')], { ...OPTS, live: true });
  const first = at(3);
  assert.match(first.skips[0].reason, /pilot budget spent/);
  assert.equal(first.alerts.length, 1);
  assert.deepEqual(at(4).alerts, [], 'said once');
  assert.deepEqual(lane.status(NOW).pilot, { lossUsd: 15, left: 0, spent: true, enforced: true });
});

test('status: the book, the flat phase, the pilot budget left, the hour contexts and the last calls', () => {
  const lane = entered();
  lane.decide(NOW + S, snap({ ETH: coin([hourRow()], { ok: false, why: 'short window' }), BTC: [hourRow()] }), [], OPTS);
  const st = lane.status(NOW + S);
  assert.deepEqual(st.flat, { on: true, trips: 0, of: 30 });
  assert.deepEqual(st.pilot, { lossUsd: 15, left: 15, spent: false, enforced: false });
  assert.deepEqual(st.context.map((c) => [c.asset, c.dir]), [['BTC', 1]]);
  assert.deepEqual(st.lastCalls.map((c) => [c.asset, c.h, c.outcome, c.ticker ?? c.reason]), [
    ['BTC', 15, 'plan', TICKER],
    ['ETH', 60, 'skip', 'reader not ok: short window'],
    ['BTC', 60, 'skip', 'BTC already has an open heat position'],
  ]);
  assert.deepEqual(st.notes, ['ETH: reader not ok: short window', 'SOL: not in the calls file', 'XRP: not in the calls file']);
});
