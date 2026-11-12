// The perpetuals hook of the heat lane (bot/setups/setupTrader.ts `heat` dependency): the four HEAT_PERPS modes, the
// hourly gate, the hourly heat setup (at most one offer per coin per clock hour, never with an open trade), its own
// minimum weight, the re-read at the re-check, the carry through an hourly close, the optimal-f history, and a
// provider that throws. Then the 4-hour heat setup (240-minute calls, HEAT_PERP_HORIZONS): its 4h ATR stop and 4-hour
// hold, its carry, one heat entry per coin per clock hour across both horizons (the hotter weight, a tie to 4h), and
// the day's direction (1440-minute calls, HEAT_PERPS_DAILY): no offer and no entry against it, never a gate on charts. The harness is the one tests/setups.test.ts uses: synthetic candles, a candle set, a perp
// hub with one quote, a fake gateway that only knows the balance, and a rule-only setup model.
import './tmpScope'; // one temp folder per run, removed at exit
import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import type { Candle } from '../bot/ta/indicators';
import type { Timeframe } from '../bot/ta/knowledge';
import { CandleSet } from '../bot/ta/candleStore';
import { PerpHub } from '../bot/perps/perpData';
import { detectAt, heatSignal, setupSeries } from '../bot/setups/detectors';
import { LaneBook, minScoreFor, type LaneBookParams, type LaneParams } from '../bot/setups/lanes';
import { SETUP_FEATURES } from '../bot/setups/features';
import { SETUP_SCHEMA } from '../bot/setups/setupModel';
import { SetupTrader, defaultSetupParams, type HeatPerpsMode, type SetupHeatDeps, type SetupTraderDeps } from '../bot/setups/setupTrader';
import { HeatLane, heatWeight } from '../bot/heat/heatLane';
import type { HeatCallRow, HeatConfig, HeatContext, HeatDecided, HeatDirection, HeatSnapshot } from '../bot/heat/types';
import { DEFAULT_PROBATION, Probation, setProbation } from '../bot/risk/probation';

const MIN = 60_000, HOUR = 3_600_000;

/** A random walk with taker flow, long enough for every indicator (the same series tests/setups.test.ts uses). */
function walk(n: number, seed: number, step = 900_000): Candle[] {
  let x = seed >>> 0; const rnd = () => ((x = (x * 1664525 + 1013904223) >>> 0) / 2 ** 32);
  const out: Candle[] = []; let p = 100;
  for (let i = 0; i < n; i++) {
    const o = p; p *= Math.exp((rnd() - 0.5) * 0.02 + 0.004 * Math.sin(i / 30));
    const h = Math.max(o, p) * (1 + rnd() * 0.004), l = Math.min(o, p) * (1 - rnd() * 0.004), v = 1 + rnd();
    out.push({ ts: Date.UTC(2025, 0, 1) + i * step, o, h, l, c: p, v, tb: v * (p > o ? 0.5 + rnd() * 0.3 : 0.2 + rnd() * 0.3) });
  }
  return out;
}

/** Wilder ATR(14) as the trader computes it (setupTrader.ts atrOf), to check the stop rule against. */
function atrOf(cs: Candle[]): number {
  let a = 0;
  const tr = (i: number) => Math.max(cs[i].h - cs[i].l, Math.abs(cs[i].h - cs[i - 1].c), Math.abs(cs[i].l - cs[i - 1].c));
  const from = Math.max(1, cs.length - 200);
  for (let i = from; i < from + 14; i++) a += tr(i);
  a /= 14;
  for (let i = from + 14; i < cs.length; i++) a = (a * 13 + tr(i)) / 14;
  return a;
}

/** A fresh lane book per trader: the shared DEFAULT_LANES object is rewritten by every trader that loads a model. */
const lanes = (): LaneBookParams => ({
  fast: { maxPositions: 3, riskFrac: 0.004, ttlBars: 2, minScore: 0, refScore: 0.2, maxChaseR: 0.3 },
  slow: { maxPositions: 3, riskFrac: 0.006, ttlBars: 1, minScore: 0, refScore: 0.3, maxChaseR: 0.5 },
  maxLeverage: 3, maxAssetLeverage: 1.5,
});

/** The curve provider as the lane would be, in memory: `fire` is a decided 60-minute call (it also becomes the hour's
 *  direction, as in the lane), `fire4` a decided 240-minute call (it also becomes the 4 hours' direction), `daily` the
 *  day's direction; every question asked is written down. */
class FakeHeat implements HeatDirection {
  readonly ctx = new Map<string, HeatContext>();
  readonly ctx4 = new Map<string, HeatContext>();
  readonly ctxDay = new Map<string, HeatContext>();
  /** The latest call per coin and horizon (`asset:h`). */
  readonly calls = new Map<string, HeatDecided>();
  readonly asked: string[] = [];
  lagMs = 45_000;
  hour(asset: string, now: number): HeatContext | undefined {
    this.asked.push(`hour:${asset}`);
    const c = this.ctx.get(asset);
    return c && now < c.until ? c : undefined;
  }
  fired(asset: string, h: number, now: number): HeatDecided | undefined {
    this.asked.push(`fired:${asset}:${h}`);
    const d = this.calls.get(`${asset}:${h}`);
    return d && d.h === h && now - d.row.barClose >= 0 && now - d.row.barClose <= this.lagMs ? d : undefined;
  }
  four(asset: string, now: number): HeatContext | undefined {
    this.asked.push(`four:${asset}`);
    const c = this.ctx4.get(asset);
    return c && now < c.until ? c : undefined;
  }
  day(asset: string, now: number): HeatContext | undefined {
    this.asked.push(`day:${asset}`);
    const c = this.ctxDay.get(asset);
    return c && now < c.until ? c : undefined;
  }
  context(asset: string, dir: 1 | -1, barClose: number, rank = 1, of = 40): void {
    this.ctx.set(asset, { asset, dir, key: `1m:RSI14=${dir > 0 ? 'very low' : 'very high'}`, rank, of, heat: 50 - rank, barClose, until: barClose + HOUR });
  }
  fire(asset: string, dir: 1 | -1, barClose: number, rank = 1, of = 40): void {
    const key = `1m:RSI14=${dir > 0 ? 'very low' : 'very high'}`;
    this.calls.set(`${asset}:60`, { asset, h: 60, fired: 3, against: 0, row: { key, kind: 'single', tf: 1, h: 60, dir, rank, of, heat: 50 - rank, share: 0.56, odds: 6, barClose } });
    this.context(asset, dir, barClose, rank, of);
  }
  /** The 4 hours' direction: a 240-minute call's, valid for 4 hours from its bar close. */
  context4(asset: string, dir: 1 | -1, barClose: number, rank = 1, of = 40): void {
    this.ctx4.set(asset, { asset, dir, key: `5m:WAD=${dir > 0 ? 'low' : 'high'}`, rank, of, heat: 20 - rank / 10, barClose, until: barClose + 4 * HOUR });
  }
  fire4(asset: string, dir: 1 | -1, barClose: number, rank = 1, of = 40): void {
    const key = `5m:WAD=${dir > 0 ? 'low' : 'high'}`;
    this.calls.set(`${asset}:240`, { asset, h: 240, fired: 2, against: 0, row: { key, kind: 'single', tf: 5, h: 240, dir, rank, of, heat: 20 - rank / 10, share: 0.55, odds: 3.4, barClose } });
    this.context4(asset, dir, barClose, rank, of);
  }
  /** The day's direction: a 1440-minute call's, valid for a day from its bar close. */
  daily(asset: string, dir: 1 | -1, barClose: number): void {
    this.ctxDay.set(asset, { asset, dir, key: `15m:ASI=${dir > 0 ? 'high' : 'low'}`, rank: 1, of: 40, heat: 6.9, barClose, until: barClose + 24 * HOUR });
  }
}

interface Rig {
  trader: SetupTrader;
  heat: FakeHeat;
  set: CandleSet;
  hub: PerpHub;
  px: { v: number };
  signals: Array<Record<string, any>>;
  trades: Array<Record<string, any>>;
  audits: Array<{ kind: string; data: any }>;
  dir: string;
  /** One executor tick at `now` (the perp quote is refreshed at the spot price first). */
  tick(now: number, guards?: Record<string, unknown>): Promise<Array<{ asset: string; target: number; urgent: boolean; reason: string; stopPrice?: number }>>;
  btc(now: number, guards?: Record<string, unknown>): Promise<{ asset: string; target: number; urgent: boolean; reason: string; stopPrice?: number }>;
  again(): SetupTrader;
}

/** A trader on one candle set. `bars`: the closed candles per timeframe as of `now`; `px0`: the spot price. */
function rig(o: {
  bars: Partial<Record<Timeframe, Candle[]>>; now: number; px0: number; mode?: HeatPerpsMode | 'none'; heat?: Partial<SetupHeatDeps>; provider?: HeatDirection;
  fastModel?: Partial<LaneParams>; deps?: Partial<SetupTraderDeps>; assets?: string[];
}): Rig {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'heat-perps-'));
  const modelFile = path.join(dir, 'setup_model.json');
  const L = lanes();
  // Rule-only lanes with a positive average: every model-scored setup scores 1. The fast lane is validated.
  fs.writeFileSync(modelFile, JSON.stringify({
    version: 'test', schema: SETUP_SCHEMA, features: SETUP_FEATURES, lanes: { fast: { meanR: 0.4, trades: 1000 }, slow: { meanR: 0.4, trades: 100 } },
    book: { ...L, fast: { ...L.fast, minScore: 0.1, refScore: 0.4, ...o.fastModel } }, costs: {}, equityUsd: 10000,
    validation: { fast: { periods: {}, trials: 1, passed: true, reasons: [] } }, trainedAt: '', data: {},
  }));
  const set = new CandleSet('BTC');
  for (const [tf, cs] of Object.entries(o.bars)) set.add(tf as Timeframe, cs!.map((c) => ({ ...c })), o.now);
  const hub = new PerpHub();
  const px = { v: o.px0 };
  const assets = o.assets ?? ['BTC'];
  const quote = (now: number) => { for (const a of assets) hub.apply({ ticker: `${a}-PERP`, asset: a, ts: now, bid: px.v * 1.001 - 0.01, ask: px.v * 1.001 + 0.01, fractional: true }); };
  quote(o.now);
  const gateway = { name: 'fake', createOrder: async () => { throw new Error('no'); }, cancelOrder: async () => {}, getOpenOrders: async () => [], getPositions: async () => [], getBalance: async () => ({ equity: 10_000, available: 10_000 }) } as never;
  const heat = new FakeHeat();
  const signals: Array<Record<string, any>> = [], trades: Array<Record<string, any>> = [], audits: Array<{ kind: string; data: any }> = [];
  const make = () => new SetupTrader({
    params: defaultSetupParams({ book: lanes(), pilotMaxNotionalUsd: 1e9 }), hub, gateway, modelPath: modelFile, statePath: path.join(dir, 'state.json'),
    candles: () => set, spot: () => px.v,
    journal: { signal: (r) => { signals.push(r); }, trade: (r) => { trades.push(r); } },
    audit: { write: (kind: string, data: unknown) => { audits.push({ kind, data }); } } as never,
    ...(o.mode === 'none' ? {} : { heat: { dir: o.provider ?? heat, mode: o.mode ?? 'entry', ...o.heat } }),
    ...o.deps,
  });
  const trader = make();
  const tick: Rig['tick'] = async (now, guards = {}) => { quote(now); return trader.targets({ positions: new Map(), hedge: [], now }, guards as never) as never; };
  return { trader, heat, set, hub, px, signals, trades, audits, dir, tick, btc: async (now, guards) => (await tick(now, guards)).find((t) => t.asset === 'BTC')!, again: make };
}

/** A heat-only book: 120 hourly bars (too few for the chart detectors, enough for the 1h ATR), no other timeframe.
 *  H is the close of the last bar, an exact clock hour. */
function hourly(o: Omit<Parameters<typeof rig>[0], 'bars' | 'now' | 'px0'> = {}) {
  const h1 = walk(120, 5, HOUR);
  const H = h1[h1.length - 1].ts + HOUR;
  const r = rig({ bars: { '1h': h1 }, now: H + 5 * MIN + 5_000, px0: h1[h1.length - 1].c, ...o });
  /** The hourly candle that opens at `ts` arrives (flat at the spot price), as the candle poll would deliver it. */
  const closeHour = (ts: number) => { r.set.add('1h', [{ ts, o: r.px.v, h: r.px.v * 1.0005, l: r.px.v * 0.9995, c: r.px.v, v: 1 }], ts + HOUR + 1_000); };
  return { ...r, H, atr: atrOf(h1), closeHour };
}

/** A book whose last closed candle carries a chart setup of the fast or slow lane on `tf`. */
function chart(tf: '15m' | '1h' | '1d', seed: number, o: Omit<Parameters<typeof rig>[0], 'bars' | 'now' | 'px0'> = {}) {
  const step = tf === '15m' ? 900_000 : tf === '1h' ? HOUR : 86_400_000;
  const all = walk(3000, seed, step);
  const s = setupSeries(all, tf);
  let at = -1;
  for (let i = 1500; i < all.length - 50; i++) if (detectAt('BTC', tf, s, i)) { at = i; break; }
  assert.ok(at > 0, `a ${tf} setup exists`);
  const sig = detectAt('BTC', tf, s, at)!;
  const now = all[at].ts + step + 5_000;
  const upto = all.slice(0, at + 1);
  // The trader needs hourly bars to score anything. Under the detectors' 220-bar minimum they add no setup of their own.
  const bars: Partial<Record<Timeframe, Candle[]>> = tf === '15m' ? { '15m': upto.slice(-320), '1h': upto.filter((c) => c.ts % HOUR === 0).slice(-320) }
    : tf === '1h' ? { '1h': upto.slice(-320) }
    : { '1d': upto.slice(-320), '1h': Array.from({ length: 100 }, (_, i) => ({ ...all[at], ts: now - 5_000 - (100 - i) * HOUR })) };
  return { ...rig({ bars, now, px0: sig.ref, ...o }), sig, now };
}

test('heat setup signal: fast lane, 1h, the call\'s side, the perp stop rule, ends at the next hourly close', () => {
  const call = { dir: 1 as const, key: '1m:RSI14=very low', rank: 2, of: 40, heat: 31, barClose: Date.UTC(2026, 10, 11, 14, 7) };
  const s = heatSignal('BTC', call, 0.8, 100, 0.6, { atrMult: 2, minBps: 50 })!;
  assert.deepEqual([s.lane, s.kind, s.tf, s.dir, s.ref], ['fast', 'heat', '1h', 1, 100]);
  assert.ok(Math.abs(s.stop - 98.8) < 1e-9, '2 x the 1h ATR below the entry');
  assert.equal(s.ts + HOUR, call.barClose, 'known at the call\'s bar close');
  assert.deepEqual(s.plan, { trailAtr: 2, maxBars: 1 }, 'no target, one hourly bar');
  assert.deepEqual(s.heat, { key: call.key, rank: 2, of: 40, heat: 31, barClose: call.barClose, weight: 0.8 });
  // A quiet hour: the minimum in bps is the stop. Shorts mirror it.
  const q = heatSignal('BTC', { ...call, dir: -1 }, 0.8, 100, 0.1, { atrMult: 2, minBps: 50 })!;
  assert.ok(Math.abs(q.stop - 100.5) < 1e-9, 'never nearer than 50 bps');
  // No price or no ATR: no stop can be set, so no setup.
  assert.equal(heatSignal('BTC', call, 0.8, 100, NaN, { atrMult: 2, minBps: 50 }), undefined);
  assert.equal(heatSignal('BTC', call, 0.8, 0, 0.6, { atrMult: 2, minBps: 50 }), undefined);
});

test('lanes: a type with its own score has its own minimum in every validation mode, and a re-check can say why it drops', () => {
  const sig = (kind: string, tf = '1h') => ({ tf, kind });
  const base: LaneParams = { maxPositions: 3, riskFrac: 0.004, ttlBars: 2, minScore: 0.3, refScore: 0.2, maxChaseR: 0.3 };
  const own = { '1h heat': 0.25 };
  // No per-type list: the lane minimum for the chart types, the own minimum for heat.
  assert.equal(minScoreFor({ ...base, ownMinScore: own }, sig('heat')), 0.25);
  assert.equal(minScoreFor({ ...base, ownMinScore: own }, sig('burst')), 0.3);
  // A per-type list that does not know heat, validation enforced (no unlisted minimum): heat still has its minimum.
  const listed = { ...base, minScoreByKind: { '1h burst': 0.9 } };
  assert.equal(minScoreFor(listed, sig('heat')), undefined, 'without the own minimum the type is never traded');
  assert.equal(minScoreFor({ ...listed, ownMinScore: own }, sig('heat')), 0.25);
  // The same list on probation (unlisted types trade from 0): heat is not let in at any score.
  assert.equal(minScoreFor({ ...listed, unlistedMinScore: 0 }, sig('heat')), 0, 'without the own minimum it trades at any score');
  assert.equal(minScoreFor({ ...listed, unlistedMinScore: 0, ownMinScore: own }, sig('heat')), 0.25);
  assert.equal(minScoreFor({ ...listed, unlistedMinScore: 0, ownMinScore: own }, sig('fade')), 0, 'other types are untouched');
  assert.equal(minScoreFor({ ...listed, ownMinScore: own }, sig('heat', '15m')), undefined, 'the key is the type on its timeframe');

  const P: LaneBookParams = { ...lanes(), fast: { ...lanes().fast, ownMinScore: { '1h heat': 0 } } };
  const heat = heatSignal('BTC', { dir: 1, key: 'k', rank: 1, of: 40, heat: 9, barClose: HOUR }, 1, 100, 0.5, { atrMult: 2, minBps: 50 })!;
  const b = new LaneBook(P);
  assert.equal(b.offer(heat, 1, HOUR), true);
  assert.equal(b.select(HOUR + 1, 10_000, () => 'heat: the hour turned').length, 0);
  assert.equal(b.lastSkips[0].reason, 'heat: the hour turned');
  assert.equal(b.queues.fast.length, 0, 'dropped, not kept');
  // Size by the heat weight: 1x sits halfway between the minimum (0) and 1, so weight 1 is 1.5x and weight 0.1 is 0.5x.
  const size = (w: number) => { const k = new LaneBook(P); k.offer(heat, w, HOUR); return k.select(HOUR + 1, 10_000, () => ({ px: 100, score: w }))[0].notional; };
  assert.ok(Math.abs(size(1) - (40 * 1.5) / 0.01) < 1e-6, `weight 1: ${size(1)}`);
  assert.ok(Math.abs(size(0.5) - 40 / 0.01) < 1e-6, `weight 0.5: ${size(0.5)}`);
  assert.ok(Math.abs(size(0.1) - (40 * 0.5) / 0.01) < 1e-6, `weight 0.1: ${size(0.1)}`);
});

test('mode off (and no dependency): the provider is never asked, nothing is journaled, a fired call opens nothing', async () => {
  for (const mode of ['off', 'none'] as const) {
    const r = hourly({ mode });
    r.heat.fire('BTC', 1, r.H + 5 * MIN);
    const t = await r.btc(r.H + 5 * MIN + 5_000);
    assert.equal(t.target, 0, mode);
    assert.equal(r.trader.book.positions.size, 0);
    assert.deepEqual(r.heat.asked, [], `${mode}: no call into the provider`);
    assert.equal(r.signals.length, 0);
    assert.equal(r.trader.status().inputs.heat?.mode ?? 'off', 'off');
  }
  // A chart setup's journal lines carry no heat fields when the curves are off.
  const c = chart('15m', 11, { mode: 'off' });
  c.heat.context('BTC', -c.sig.dir as 1 | -1, c.now - MIN);
  assert.notEqual((await c.btc(c.now)).target, 0);
  assert.equal(Object.keys(c.signals[0]).some((k) => k.startsWith('heat_')), false);
  assert.equal(Object.keys(c.trades[0]).some((k) => k.startsWith('heat_')), false);
});

test('mode log: the hour context is journaled beside every signal and open; nothing is gated and nothing is offered', async () => {
  const c = chart('1h', 7, { mode: 'log' });
  const against = -c.sig.dir as 1 | -1;
  c.heat.fire('BTC', against, c.now - 5_000, 3, 40);
  const t = await c.btc(c.now);
  assert.notEqual(t.target, 0, `a 1h setup against the hour still enters in log mode: ${t.reason}`);
  assert.equal(Math.sign(t.target), c.sig.dir);
  assert.equal(c.trader.book.positions.get('BTC')!.kind, c.sig.kind, 'the chart setup, not a heat setup');
  assert.equal(c.signals.length, 1, 'the fired call is not offered in log mode');
  const want = { heat_mode: 'log', heat_dir: against, heat_agree: -1, heat_key: c.heat.ctx.get('BTC')!.key, heat_rank: 3, heat_of: 40, heat_w: +heatWeight(3, 40, 10).toFixed(4), heat_bar_close: c.now - 5_000, heat_until: c.now - 5_000 + HOUR, heat_day_dir: null };
  for (const rec of [c.signals[0], c.trades[0]]) for (const [k, v] of Object.entries(want)) assert.equal(rec[k], v, `${rec.type ?? rec.event ?? 'signal'} ${k}`);
  assert.equal(c.trades[0].event, 'opened');
  assert.ok(c.heat.asked.includes('day:BTC'), 'the day is asked for too (no daily curve yet: journaled as null)');
  assert.equal(c.heat.asked.some((a) => a.startsWith('fired')), false, 'log mode never asks for a fired call');
  // No context: the fields are there and empty.
  const n = chart('1h', 7, { mode: 'log' });
  assert.notEqual((await n.btc(n.now)).target, 0);
  assert.deepEqual([n.signals[0].heat_mode, n.signals[0].heat_dir, n.signals[0].heat_agree, n.trades[0].heat_dir], ['log', null, null, null]);
});

test('mode gate: a 1h setup against a live hour context does not enter; no context, an expired one or the same side pass', async () => {
  // Against: dropped at the re-check, with the reason, and it stays dropped.
  const a = chart('1h', 7, { mode: 'gate' });
  a.heat.context('BTC', -a.sig.dir as 1 | -1, a.now - 10 * MIN, 2, 40);
  assert.equal((await a.btc(a.now)).target, 0);
  assert.equal(a.trader.book.positions.size, 0);
  assert.equal(a.signals[0].queued, true, 'the setup was detected and queued as usual');
  assert.match(a.trader.status().recentSkips[0].reason, /^heat gate: the hour's direction is (up|down) \(1m:RSI14=very (low|high), rank 2\/40\), against this (long|short)$/);
  assert.equal(a.audits.filter((x) => x.kind === 'setup_skip' && /^heat gate/.test(x.data.reason)).length, 1);
  assert.equal(a.trader.status().lanes.fast.queue.length, 0);
  // gate mode never offers a heat setup, whatever fires.
  a.heat.fire('BTC', a.sig.dir, a.now + MIN);
  assert.equal((await a.btc(a.now + MIN + 5_000)).target, 0);
  assert.equal(a.heat.asked.some((x) => x.startsWith('fired')), false);

  // Mode entry gates the same way (gate is part of entry); with no call firing it offers nothing of its own.
  const en = chart('1h', 7, { mode: 'entry' });
  en.heat.context('BTC', -en.sig.dir as 1 | -1, en.now - 10 * MIN, 2, 40);
  assert.equal((await en.btc(en.now)).target, 0);
  assert.match(en.trader.status().recentSkips[0].reason, /^heat gate: /);
  assert.equal(en.signals.length, 1, 'only the chart setup was seen');

  // No context: pass.
  const n = chart('1h', 7, { mode: 'gate' });
  assert.equal(Math.sign((await n.btc(n.now)).target), n.sig.dir);
  // A context past its hour is no context.
  const e = chart('1h', 7, { mode: 'gate' });
  e.heat.context('BTC', -e.sig.dir as 1 | -1, e.now - HOUR - MIN);
  assert.equal(Math.sign((await e.btc(e.now)).target), e.sig.dir);
  // The same side: pass, and the journal says the hour agreed.
  const s = chart('1h', 7, { mode: 'gate' });
  s.heat.context('BTC', s.sig.dir, s.now - 10 * MIN);
  assert.equal(Math.sign((await s.btc(s.now)).target), s.sig.dir);
  assert.equal(s.trades[0].heat_agree, 1);
});

test('mode gate: 15-minute and daily setups are not gated (the context is only journaled)', async () => {
  for (const [tf, seed] of [['15m', 11], ['1d', 7]] as const) {
    const c = chart(tf, seed, { mode: 'gate' });
    c.heat.context('BTC', -c.sig.dir as 1 | -1, c.now - 10 * MIN);
    const t = await c.btc(c.now);
    assert.equal(Math.sign(t.target), c.sig.dir, `${tf} ${c.sig.kind} entered against the hour: ${t.reason}`);
    assert.equal(c.trader.book.positions.get('BTC')!.tf, tf);
    assert.equal(c.trades[0].heat_agree, -1);
    assert.equal(c.trades[0].heat_day_dir, null);
  }
});

test('mode entry: a fired 60-minute call opens a fast-lane 1h heat trade with the perp stop, sized by the heat weight', async () => {
  const r = hourly({ heat: { topN: 10 } });
  const now = r.H + 5 * MIN + 5_000;
  r.heat.fire('BTC', 1, r.H + 5 * MIN, 1, 40);
  const t = await r.btc(now);
  assert.ok(t.target > 0, `long: ${t.reason}`);
  const p = r.trader.book.positions.get('BTC')!;
  assert.deepEqual([p.lane, p.kind, p.tf, p.dir, p.plan.maxBars, p.plan.target1, p.plan.target2], ['fast', 'heat', '1h', 1, 1, undefined, undefined]);
  const dist = Math.max(2 * r.atr, 0.005 * r.px.v);
  assert.ok(Math.abs(p.stop - (r.px.v - dist)) < 1e-9, 'stop: 2 x the 1h ATR, at least 50 bps');
  assert.ok(Math.abs(t.stopPrice! / (p.stop * 1.001) - 1) < 1e-3, 'the exchange stop is the trade\'s stop on the perp');
  assert.equal(p.score, 1, 'score = the heat weight (rank 1 of the top 10)');
  // Lane sizing unchanged: 0.4% of equity at risk, x1.5 at weight 1 (the 1x point is halfway between the minimum and 1).
  assert.ok(Math.abs(p.notional! - (10_000 * 0.004 * 1.5) / (dist / r.px.v)) < 1e-6, `notional ${p.notional}`);
  assert.deepEqual(p.heat, { key: '1m:RSI14=very low', rank: 1, of: 40, heat: 49, barClose: r.H + 5 * MIN, weight: 1, extended: 0 });
  assert.match(t.reason, /^fast 1h heat long from [\d.]+: stop [\d.]+, until the hourly close$/);
  // Journal: the call as a signal (queued), then the open, both with the hour context.
  assert.equal(r.signals.length, 1);
  const s = r.signals[0];
  assert.deepEqual([s.kind, s.tf, s.lane, s.dir, s.queued, s.score, s.at, s.why, s.call_rank, s.call_of, s.heat_dir, s.heat_agree], ['heat', '1h', 'fast', 1, true, 1, r.H + 5 * MIN, null, 1, 40, 1, 1]);
  assert.deepEqual([r.trades[0].event, r.trades[0].kind, r.trades[0].heat_mode, r.trades[0].heat_dir, r.trades[0].heat_agree], ['opened', 'heat', 'entry', 1, 1]);
  assert.equal(r.audits.filter((x) => x.kind === 'setup_signal' && x.data.kind === 'heat' && x.data.queued === true).length, 1);
  // A restarted trader resumes the heat trade from the saved book.
  assert.equal(r.again().book.positions.get('BTC')!.kind, 'heat');

  // A cooler call (rank 9 of 10: weight 1/9) trades too by default, at the small end of the lane's size; a short mirrors.
  const c = hourly();
  c.heat.fire('BTC', -1, c.H + 5 * MIN, 9, 40);
  assert.ok((await c.btc(c.H + 5 * MIN + 5_000)).target < 0);
  const q = c.trader.book.positions.get('BTC')!;
  assert.ok(Math.abs(q.stop - (c.px.v + dist)) < 1e-9);
  assert.ok(Math.abs(q.score! - 1 / 9) < 1e-12);
  assert.ok(Math.abs(q.notional! - (10_000 * 0.004 * 0.5) / (dist / c.px.v)) < 1e-6);

  // The stop multiple and floor come with the dependency (PERP_STOP_ATR_MULT, PERP_MIN_STOP_BPS).
  const w = hourly({ heat: { stopAtrMult: 0.01, minStopBps: 80 } });
  w.heat.fire('BTC', 1, w.H + 5 * MIN);
  assert.ok((await w.btc(w.H + 5 * MIN + 5_000)).target > 0);
  assert.ok(Math.abs(w.trader.book.positions.get('BTC')!.stop - w.px.v * (1 - 0.008)) < 1e-9);
});

test('mode entry: never DOGE, and the provider is not even asked about it', async () => {
  const r = hourly({ assets: ['BTC', 'DOGE'] });
  r.heat.fire('DOGE', 1, r.H + 5 * MIN);
  const out = await r.tick(r.H + 5 * MIN + 5_000);
  assert.deepEqual(out.map((t) => [t.asset, t.target]), [['BTC', 0], ['DOGE', 0]]);
  assert.equal(r.trader.book.positions.size, 0);
  assert.equal(r.signals.length, 0);
  assert.equal(r.heat.asked.some((a) => a.includes('DOGE')), false);
  assert.deepEqual(r.heat.asked.filter((a) => a.startsWith('fired')).sort(), ['fired:BTC:240', 'fired:BTC:60'], 'the 60- and 240-minute calls are asked for, nothing else');
});

test('mode entry: one offer per coin per clock hour, once per call, and never while the coin has an open trade', async () => {
  const r = hourly();
  const at = (min: number, sec = 5) => r.H + min * MIN + sec * 1000;
  r.heat.fire('BTC', 1, r.H + 5 * MIN);
  assert.ok((await r.btc(at(5))).target > 0);
  // The same call is seen again on the next executor ticks: ruled on once.
  await r.btc(at(5, 10)); await r.btc(at(5, 40));
  assert.equal(r.signals.length, 1);
  // A newer call while the trade is open: not offered, and it does not wait in the queue for the coin to free up.
  r.heat.fire('BTC', 1, r.H + 6 * MIN);
  await r.btc(at(6));
  assert.deepEqual([r.signals.length, r.signals[1].queued, r.signals[1].why], [2, false, 'the coin has an open 1h heat trade']);
  assert.equal(r.trader.status().lanes.fast.queue.length, 0);
  // Stopped out inside the hour.
  const p = r.trader.book.positions.get('BTC')!;
  const entry = r.px.v;
  r.px.v = p.stop - 0.001;
  const out = await r.btc(at(7));
  assert.deepEqual([out.target, out.urgent, out.reason], [0, true, 'exit: stop']);
  r.px.v = entry;
  // The calls keep firing in the same clock hour (1-minute readings): no second offer, either side.
  for (const [min, dir] of [[10, 1], [25, -1], [59, 1]] as const) {
    r.heat.fire('BTC', dir, r.H + min * MIN);
    assert.equal((await r.btc(at(min))).target, 0, `minute ${min}`);
  }
  assert.equal(r.trader.book.positions.size, 0);
  assert.deepEqual(r.signals.slice(2).map((s) => [s.queued, s.why]), Array(3).fill([false, 'a heat entry was already offered for this coin this clock hour']));
  assert.equal(r.trader.status().recentTrades.length, 1, 'one round trip this hour');
  // The next clock hour: its first call is offered again.
  r.heat.fire('BTC', -1, r.H + HOUR + 2 * MIN);
  assert.ok((await r.btc(at(62))).target < 0);
  assert.equal(r.signals[r.signals.length - 1].queued, true);

  // An open chart trade blocks the offer just the same, and the call does not use up the clock hour.
  const c = chart('15m', 11, { mode: 'entry' });
  assert.notEqual((await c.btc(c.now)).target, 0);
  const kind = c.trader.book.positions.get('BTC')!.kind;
  c.heat.fire('BTC', c.sig.dir, c.now + 55_000);
  await c.btc(c.now + MIN);
  const last = c.signals[c.signals.length - 1];
  assert.deepEqual([last.kind, last.queued, last.why], ['heat', false, `the coin has an open 15m ${kind} trade`]);
  assert.equal(c.trader.book.positions.get('BTC')!.kind, kind);
});

test('mode entry: the heat setup has its own minimum weight, with validation enforced and on probation alike', async () => {
  // The model lists its types (heat is not one of them). Enforced: an unlisted type never queues. On probation
  // (monitor): an unlisted type trades from score 0. Heat does neither: it queues by its own minimum.
  for (const mode of ['enforce', 'monitor'] as const) {
    setProbation(mode === 'monitor' ? new Probation({ ...DEFAULT_PROBATION, mode: 'monitor' }) : undefined);
    try {
      const r = hourly({ heat: { minWeight: 0.5 }, fastModel: { minScoreByKind: { '1h burst': 0.9 } } });
      // Rank 9 of the top 10: weight 1/9, under the minimum. Not queued, and the clock hour is not used up.
      r.heat.fire('BTC', 1, r.H + 5 * MIN, 9, 40);
      assert.equal((await r.btc(r.H + 5 * MIN + 5_000)).target, 0, mode);
      assert.deepEqual([r.signals[0].queued, r.signals[0].why], [false, 'heat weight 0.111 is under the minimum 0.5'], mode);
      // What an unlisted type faces in this mode: no minimum at all (never traded) or the lane's (0.1 here, which a
      // weight of 0.111 would clear). The heat type is held to its own 0.5 in both.
      assert.equal(r.trader.book.params.fast.unlistedMinScore, mode === 'monitor' ? 0.1 : undefined, mode);
      // A hotter call later the same hour: queued and entered.
      r.heat.fire('BTC', 1, r.H + 8 * MIN, 1, 40);
      assert.ok((await r.btc(r.H + 8 * MIN + 5_000)).target > 0, mode);
      assert.equal(r.trader.book.positions.get('BTC')!.kind, 'heat');
      assert.equal(r.trader.status().inputs.heat!.minWeight, 0.5);
    } finally { setProbation(undefined); }
  }
});

test('mode entry: at the re-check a heat candidate is dropped unless the hour context still has its side', async () => {
  const start = async () => {
    const r = hourly();
    r.heat.fire('BTC', 1, r.H + 5 * MIN);
    // Entries are paused: the call is queued (and uses the clock hour) but cannot enter yet.
    assert.equal((await r.btc(r.H + 5 * MIN + 5_000, { noEntry: 'paused' })).target, 0);
    assert.deepEqual(r.trader.status().lanes.fast.queue.map((c) => [c.kind, c.tf, c.dir, c.score]), [['heat', '1h', 1, 1]]);
    return r;
  };
  // The hour turned: a later call points down. The waiting long is dropped (and the down call is not offered: the
  // hour was used).
  const a = await start();
  a.heat.fire('BTC', -1, a.H + 7 * MIN, 2, 40);
  assert.equal((await a.btc(a.H + 7 * MIN + 5_000)).target, 0);
  assert.equal(a.trader.book.positions.size, 0);
  assert.equal(a.trader.status().recentSkips[0].reason, "heat: the hour's direction turned down (1m:RSI14=very high)");
  assert.equal(a.trader.status().lanes.fast.queue.length, 0);
  assert.equal(a.audits.filter((x) => x.kind === 'setup_skip' && x.data.kind === 'heat').length, 1);
  // No context left (the provider has nothing for the coin any more): dropped.
  const b = await start();
  b.heat.ctx.delete('BTC');
  assert.equal((await b.btc(b.H + 7 * MIN + 5_000)).target, 0);
  assert.equal(b.trader.status().recentSkips[0].reason, 'heat: no live hour direction left for this call');
  // Still the same side (a newer, cooler call): it enters, scored by the weight of the hour's direction now.
  const c = await start();
  c.heat.context('BTC', 1, c.H + 7 * MIN, 5, 40);
  assert.ok((await c.btc(c.H + 7 * MIN + 5_000)).target > 0);
  assert.ok(Math.abs(c.trader.book.positions.get('BTC')!.score! - heatWeight(5, 40, 10)) < 1e-12);
  // A heat candidate left in the queue is not entered once the mode is no longer entry.
  const d = await start();
  const off = rig({ bars: { '1h': d.set.bars['1h']! }, now: d.H + 6 * MIN, px0: d.px.v, mode: 'gate' });
  fs.copyFileSync(path.join(d.dir, 'state.json'), path.join(off.dir, 'state.json'));
  const restarted = off.again();
  assert.equal(restarted.book.queues.fast.length, 1, 'the saved queue came back');
  off.heat.context('BTC', 1, d.H + 5 * MIN);
  off.hub.apply({ ticker: 'BTC-PERP', asset: 'BTC', ts: d.H + 6 * MIN, bid: d.px.v * 1.001 - 0.01, ask: d.px.v * 1.001 + 0.01, fractional: true });
  const t = (await restarted.targets({ positions: new Map(), hedge: [], now: d.H + 6 * MIN }, {})).find((x) => x.asset === 'BTC')!;
  assert.equal(t.target, 0);
  assert.equal(restarted.status().recentSkips[0].reason, 'heat entries are off (HEAT_PERPS)');
});

test('mode entry: a heat candidate that waited past its clock hour is dropped, not entered next to the new hour', async () => {
  const r = hourly();
  r.heat.fire('BTC', 1, r.H + 5 * MIN);
  assert.equal((await r.btc(r.H + 5 * MIN + 5_000, { noEntry: 'paused' })).target, 0);
  assert.equal(r.trader.status().lanes.fast.queue.length, 1);
  // Still paused at the end of the hour: it keeps waiting.
  assert.equal((await r.btc(r.H + 59 * MIN, { noEntry: 'paused' })).target, 0);
  assert.equal(r.trader.status().lanes.fast.queue.length, 1);
  // Entries resume in the next clock hour, with the hour still pointing up: the old candidate is dropped.
  r.heat.context('BTC', 1, r.H + HOUR + MIN);
  assert.equal((await r.btc(r.H + HOUR + 2 * MIN)).target, 0);
  assert.equal(r.trader.book.positions.size, 0);
  assert.equal(r.trader.status().lanes.fast.queue.length, 0);
  assert.equal(r.trader.status().recentSkips[0].reason, 'heat: the clock hour it was offered in has passed');
});

test('mode entry: a heat trade ends at the next hourly close, unless the hour still points its way: then it is carried, not closed and re-opened', async () => {
  const start = async () => {
    const r = hourly();
    r.heat.fire('BTC', 1, r.H + 5 * MIN);
    assert.ok((await r.btc(r.H + 5 * MIN + 5_000)).target > 0);
    return r;
  };
  const C = (r: { H: number }) => r.H + HOUR; // the hourly close the trade is due to end at

  // Carried: the next hour's call (the reading at the close itself) is on the same side.
  const a = await start();
  const size = (await a.btc(a.H + 50 * MIN)).target;
  a.closeHour(a.H);
  a.heat.fire('BTC', 1, C(a), 4, 40);
  // Inside the wait after the close nothing is ruled on yet; the call itself is not offered (the coin has a trade).
  assert.equal((await a.btc(C(a) + 30_000)).target, size);
  assert.equal(a.trader.book.positions.get('BTC')!.bars, 0);
  assert.equal(a.signals[a.signals.length - 1].why, 'the coin has an open 1h heat trade');
  // After the wait: carried through the close. Same position, same size, no round trip.
  assert.equal((await a.btc(C(a) + 95_000)).target, size);
  const p = a.trader.book.positions.get('BTC')!;
  assert.deepEqual([p.bars, p.plan.maxBars, p.heat!.extended, p.heat!.barClose, p.heat!.rank], [1, 2, 1, C(a), 4]);
  assert.equal(a.trader.status().recentTrades.length, 0, 'nothing was closed');
  const ext = a.trades.filter((t) => t.event === 'extended');
  assert.deepEqual([ext.length, ext[0].close, ext[0].extended, ext[0].heat_dir, ext[0].entryTs], [1, C(a), 1, 1, p.entryTs]);
  assert.equal(a.audits.filter((x) => x.kind === 'setup_trade' && x.data.event === 'extended').length, 1);
  // The carried hour is that clock hour's heat entry: after a stop-out no new offer until the next clock hour.
  const entry = a.px.v;
  a.px.v = p.stop - 0.001;
  assert.equal((await a.btc(C(a) + 10 * MIN)).reason, 'exit: stop');
  a.px.v = entry;
  a.heat.fire('BTC', 1, C(a) + 20 * MIN);
  assert.equal((await a.btc(C(a) + 20 * MIN + 5_000)).target, 0);
  assert.equal(a.signals[a.signals.length - 1].why, 'a heat entry was already offered for this coin this clock hour');
  a.heat.fire('BTC', 1, C(a) + HOUR + 3 * MIN);
  assert.ok((await a.btc(C(a) + HOUR + 3 * MIN + 5_000)).target > 0, 'the next clock hour is open again');

  // Carried twice, then ended when the hour turns: closed on time at that hourly close.
  const b = await start();
  b.closeHour(b.H);
  b.heat.fire('BTC', 1, C(b) - 10 * MIN); // a call late in the hour covers most of the next one
  assert.notEqual((await b.btc(C(b) + 95_000)).target, 0);
  b.closeHour(C(b));
  b.heat.fire('BTC', 1, C(b) + 55 * MIN);
  assert.notEqual((await b.btc(C(b) + HOUR + 95_000)).target, 0);
  assert.deepEqual([b.trader.book.positions.get('BTC')!.bars, b.trader.book.positions.get('BTC')!.heat!.extended], [2, 2]);
  b.closeHour(C(b) + HOUR);
  b.heat.context('BTC', -1, C(b) + 2 * HOUR - 5 * MIN);
  const end = await b.btc(C(b) + 2 * HOUR + 95_000);
  assert.deepEqual([end.target, end.reason], [0, 'exit: time']);
  assert.deepEqual([b.trader.status().recentTrades[0].kind, b.trader.status().recentTrades[0].reason], ['heat', 'time']);
  const closed = b.trades[b.trades.length - 1];
  assert.deepEqual([closed.event, closed.kind, closed.reason, closed.extended], ['closed', 'heat', 'time', 2], 'the close says how many hours it was carried');

  // Not carried: no newer call (the entry's own call ends five minutes into the next hour), no context at all, or
  // the mode is no longer entry. Each ends on time at the first hourly close.
  for (const how of ['old call', 'no context', 'against'] as const) {
    const n = await start();
    n.closeHour(n.H);
    if (how === 'no context') n.heat.ctx.delete('BTC');
    if (how === 'against') n.heat.context('BTC', -1, C(n) - MIN);
    const out = await n.btc(C(n) + 95_000);
    assert.deepEqual([out.target, out.reason], [0, 'exit: time'], how);
    assert.equal(n.trades.filter((t) => t.event === 'extended').length, 0, how);
  }
});

test('heat trades stay out of the fast lane\'s optimal-f history; chart trades stay in', async () => {
  const optimalF = { enabled: true, quantile: 0.25, halfLifeDays: 180, liveMult: 5, minTradesSetups: 50, minTradesKalshi: 50, paperFloor: 0.25, paper: true };
  const stopOut = async (r: Rig, now: number) => {
    const p = r.trader.book.positions.get('BTC')!;
    const entry = r.px.v;
    r.px.v = p.stop - p.dir * 0.001;
    assert.equal((await r.btc(now)).reason, 'exit: stop');
    r.px.v = entry;
    await r.btc(now + 5_000); // the caps are recomputed when entries are next looked at
  };
  const h = hourly({ deps: { optimalF } });
  h.heat.fire('BTC', 1, h.H + 5 * MIN);
  assert.ok((await h.btc(h.H + 5 * MIN + 5_000)).target > 0);
  await stopOut(h, h.H + 6 * MIN);
  assert.equal(h.trader.status().recentTrades.length, 1);
  assert.equal(h.trader.capReports.fast!.liveTrades, 0, 'the closed heat trade is not in the lane\'s history');
  assert.equal(h.trader.status().today.trades, 1, 'it still counts as a trade of the day');
  // The same with a chart trade of the fast lane: it is counted.
  const c = chart('15m', 11, { mode: 'entry', deps: { optimalF } });
  assert.notEqual((await c.btc(c.now)).target, 0);
  await stopOut(c, c.now + MIN);
  assert.equal(c.trader.capReports.fast!.liveTrades, 1);
});

test('a provider that throws never breaks targets(): logged once, read as no call, the rest of the trader carries on', async () => {
  const boom: HeatDirection = {
    hour() { throw new Error('hour blew up'); },
    fired() { throw new Error('fired blew up'); },
    four() { throw new Error('four blew up'); },
    day() { throw new Error('day blew up'); },
  };
  const warns: string[] = [];
  const realError = console.error;
  console.error = (...a: unknown[]) => { warns.push(a.map(String).join(' ')); };
  try {
    for (const mode of ['log', 'gate', 'entry'] as const) {
      // A chart setup on 1h still enters: no call is no context, and no context passes the gate.
      const c = chart('1h', 7, { mode, provider: boom });
      const before = warns.length;
      const t = await c.btc(c.now);
      assert.equal(Math.sign(t.target), c.sig.dir, `${mode}: ${t.reason}`);
      for (let i = 1; i <= 3; i++) assert.equal((await c.tick(c.now + i * 5_000)).length, 1, `${mode}: targets() keeps answering`);
      const mine = warns.slice(before).filter((w) => w.includes('heat provider threw'));
      assert.equal(mine.length, 1, `${mode}: logged once, not on every tick`);
      assert.deepEqual([c.signals[0].heat_dir, c.trades[0].heat_dir, c.trades[0].heat_day_dir], [null, null, null], 'journaled as no call');
      const st = c.trader.status().inputs.heat!;
      assert.ok(st.throws > 1, `${mode}: every throw is counted (${st.throws})`);
      assert.match(st.error!, /blew up/);
    }
    // Heat only, entry mode: nothing to offer, nothing breaks, and an open heat trade is still managed to its close.
    const r = hourly();
    r.heat.fire('BTC', 1, r.H + 5 * MIN);
    assert.ok((await r.btc(r.H + 5 * MIN + 5_000)).target > 0);
    const broken = rig({ bars: { '1h': r.set.bars['1h']! }, now: r.H + 6 * MIN, px0: r.px.v, provider: boom });
    fs.copyFileSync(path.join(r.dir, 'state.json'), path.join(broken.dir, 'state.json'));
    const tr = broken.again();
    const run = async (now: number) => (await tr.targets({ positions: new Map(), hedge: [], now }, {})).find((x) => x.asset === 'BTC')!;
    broken.hub.apply({ ticker: 'BTC-PERP', asset: 'BTC', ts: r.H + 6 * MIN, bid: r.px.v * 1.001 - 0.01, ask: r.px.v * 1.001 + 0.01, fractional: true });
    assert.ok((await run(r.H + 6 * MIN)).target > 0, 'the open heat trade is held');
    broken.set.add('1h', [{ ts: r.H, o: r.px.v, h: r.px.v * 1.0005, l: r.px.v * 0.9995, c: r.px.v, v: 1 }], r.H + HOUR + 1_000);
    broken.hub.apply({ ticker: 'BTC-PERP', asset: 'BTC', ts: r.H + HOUR + 95_000, bid: r.px.v * 1.001 - 0.01, ask: r.px.v * 1.001 + 0.01, fractional: true });
    const end = await run(r.H + HOUR + 95_000);
    assert.deepEqual([end.target, end.reason], [0, 'exit: time'], 'no call at the hourly close: the trade ends on time');
  } finally { console.error = realError; }
});

// ---- The 4-hour heat setup (240-minute calls) and the day's direction (1440-minute calls) ----

/** The 4h ATR the trader sets a 4h heat stop with: the candle store's 4h bars, built from complete groups of four 1h bars. */
const atr4 = (r: { set: CandleSet }): number => atrOf(r.set.bars['4h']!);

test('heat setup signal on 4h: the timeframe\'s ATR, known at the call\'s bar close, ends at the next 4-hour close', () => {
  const call = { dir: -1 as const, key: '5m:WAD=high', rank: 1, of: 40, heat: 17.4, barClose: Date.UTC(2026, 10, 11, 18, 9) };
  const s = heatSignal('BTC', call, 1, 100, 1.5, { atrMult: 2, minBps: 50 }, '4h')!;
  assert.deepEqual([s.lane, s.kind, s.tf, s.dir, s.ref, s.atr], ['fast', 'heat', '4h', -1, 100, 1.5]);
  assert.ok(Math.abs(s.stop - 103) < 1e-9, '2 x the 4h ATR above the entry');
  assert.equal(s.ts + 4 * HOUR, call.barClose, 'known at the call\'s bar close');
  assert.deepEqual(s.plan, { trailAtr: 2, maxBars: 1 }, 'no target, one 4-hour bar');
  // Its own minimum is keyed by its own type: "4h heat".
  assert.equal(minScoreFor({ maxPositions: 3, riskFrac: 0.004, ttlBars: 2, minScore: 0.3, refScore: 0.2, maxChaseR: 0.3, ownMinScore: { '4h heat': 0.2 } }, s), 0.2);
});

test('the candle store builds the 4h bars the 4h heat setup needs from complete groups of four 1h bars', () => {
  const r = hourly();
  const h4 = r.set.bars['4h']!;
  assert.equal(h4.length, 30, '120 hourly bars, aligned to 00 UTC');
  assert.equal(h4[h4.length - 1].ts + 4 * HOUR, r.H, 'the last 4h bar closes at H');
  assert.ok(atr4(r) > r.atr, 'a 4h ATR is wider than the 1h ATR');
  r.closeHour(r.H); r.closeHour(r.H + HOUR); r.closeHour(r.H + 2 * HOUR);
  assert.equal(r.set.bars['4h']!.length, 30, 'three hours of the next 4h bar: not a bar yet');
  r.closeHour(r.H + 3 * HOUR);
  assert.equal(r.set.bars['4h']![30].ts, r.H, 'the fourth hour completes it');
});

test('mode entry: a fired 240-minute call opens a fast-lane 4h heat trade with the 4h ATR stop, held to the next 4-hour close', async () => {
  const r = hourly();
  const now = r.H + 5 * MIN + 5_000;
  r.heat.fire4('BTC', 1, r.H + 5 * MIN, 1, 40);
  const t = await r.btc(now);
  assert.ok(t.target > 0, `long: ${t.reason}`);
  const p = r.trader.book.positions.get('BTC')!;
  assert.deepEqual([p.lane, p.kind, p.tf, p.dir, p.plan.maxBars, p.plan.target1, p.plan.target2], ['fast', 'heat', '4h', 1, 1, undefined, undefined]);
  const dist = Math.max(2 * atr4(r), 0.005 * r.px.v);
  assert.ok(Math.abs(p.stop - (r.px.v - dist)) < 1e-9, 'stop: 2 x the 4h ATR, at least 50 bps');
  assert.equal(p.score, 1);
  assert.ok(Math.abs(p.notional! - (10_000 * 0.004 * 1.5) / (dist / r.px.v)) < 1e-6, `sized like any heat setup: ${p.notional}`);
  assert.deepEqual(p.heat, { key: '5m:WAD=low', rank: 1, of: 40, heat: 19.9, barClose: r.H + 5 * MIN, weight: 1, extended: 0 });
  assert.match(t.reason, /^fast 4h heat long from [\d.]+: stop [\d.]+, until the 4-hour close$/);
  const s = r.signals[0];
  assert.deepEqual([s.kind, s.tf, s.call_h, s.queued, s.score, s.why, s.heat_four_dir, s.heat_four_agree, s.heat_four_key], ['heat', '4h', 240, true, 1, null, 1, 1, '5m:WAD=low']);
  assert.deepEqual([r.trades[0].event, r.trades[0].tf, r.trades[0].heat_four_dir], ['opened', '4h', 1]);
  assert.equal(r.again().book.positions.get('BTC')!.tf, '4h', 'a restarted trader resumes the 4h heat trade');
  // Held through the hourly closes inside its 4 hours.
  for (let k = 0; k < 3; k++) {
    r.closeHour(r.H + k * HOUR);
    assert.equal(Math.sign((await r.btc(r.H + (k + 1) * HOUR + 95_000)).target), 1, `hour ${k + 1}`);
  }
  assert.equal(r.trader.book.positions.get('BTC')!.bars, 0);
  // The fourth hour completes the 4h bar: ruled on 90 s after the close, and ended on time (the entry's own call reaches
  // only 5 minutes into the next 4 hours, so it carries nothing).
  r.closeHour(r.H + 3 * HOUR);
  assert.ok((await r.btc(r.H + 4 * HOUR + 30_000)).target > 0, 'inside the wait after the close');
  const end = await r.btc(r.H + 4 * HOUR + 95_000);
  assert.deepEqual([end.target, end.reason], [0, 'exit: time']);
  assert.deepEqual([r.trader.status().recentTrades[0].kind, r.trader.status().recentTrades[0].tf, r.trader.status().recentTrades[0].reason], ['heat', '4h', 'time']);
});

test('mode entry: a 4h heat trade is carried through its 4-hour close while the 4 hours keep its side, never against the day', async () => {
  const start = async () => {
    const r = hourly();
    r.heat.fire4('BTC', 1, r.H + 5 * MIN);
    assert.ok((await r.btc(r.H + 5 * MIN + 5_000)).target > 0);
    for (let k = 0; k < 4; k++) r.closeHour(r.H + k * HOUR);
    return r;
  };
  const C = (r: { H: number }) => r.H + 4 * HOUR; // the 4-hour close the trade is due to end at
  // A 240-minute call in the last two hours of the bar, on the trade's side: it covers most of the next 4 hours.
  const a = await start();
  a.heat.fire4('BTC', 1, a.H + 3 * HOUR, 4, 40);
  await a.btc(a.H + 3 * HOUR + 5_000);
  assert.equal(a.signals[a.signals.length - 1].why, 'the coin has an open 4h heat trade');
  const size = (await a.btc(C(a) + 95_000)).target;
  assert.ok(size > 0);
  const p = a.trader.book.positions.get('BTC')!;
  assert.deepEqual([p.bars, p.plan.maxBars, p.heat!.extended, p.heat!.barClose, p.heat!.rank], [1, 2, 1, a.H + 3 * HOUR, 4]);
  assert.deepEqual(a.trades.filter((t) => t.event === 'extended').map((t) => [t.tf, t.close, t.extended]), [['4h', C(a), 1]]);
  // The next 4 hours turn: it ends on time at their close.
  for (let k = 0; k < 4; k++) a.closeHour(C(a) + k * HOUR);
  a.heat.context4('BTC', -1, C(a) + 3 * HOUR);
  const end = await a.btc(C(a) + 4 * HOUR + 95_000);
  assert.deepEqual([end.target, end.reason], [0, 'exit: time']);
  assert.equal(a.trades[a.trades.length - 1].extended, 1);

  // Not carried: the 4 hours point the other way, the call is too old (it covers less than half of the next bar), the day
  // points against the trade (a carry stands for a new entry), or the hour alone agrees (a 4h trade reads the 4 hours).
  for (const how of ['against', 'old call', 'day against', 'hour only'] as const) {
    const n = await start();
    if (how === 'against') n.heat.context4('BTC', -1, n.H + 3 * HOUR);
    if (how === 'old call') n.heat.context4('BTC', 1, n.H + 2 * HOUR - MIN);
    if (how === 'day against') { n.heat.context4('BTC', 1, n.H + 3 * HOUR); n.heat.daily('BTC', -1, n.H + 3 * HOUR); }
    if (how === 'hour only') { n.heat.ctx4.delete('BTC'); n.heat.context('BTC', 1, C(n) - MIN); }
    const out = await n.btc(C(n) + 95_000);
    assert.deepEqual([out.target, out.reason], [0, 'exit: time'], how);
    assert.equal(n.trades.filter((t) => t.event === 'extended').length, 0, how);
  }
});

test('mode entry: one heat entry per coin per clock hour across 1h and 4h; the same minute goes to the hotter weight, a tie to 4h', async () => {
  // rank 1 of the top 10 weighs 1, rank 5 weighs 5/9.
  for (const [rank60, rank240, want] of [[1, 5, '1h'], [5, 1, '4h'], [1, 1, '4h'], [3, 3, '4h']] as const) {
    const r = hourly();
    r.heat.fire('BTC', 1, r.H + 5 * MIN, rank60, 40);
    r.heat.fire4('BTC', 1, r.H + 5 * MIN, rank240, 40);
    assert.ok((await r.btc(r.H + 5 * MIN + 5_000)).target > 0);
    assert.equal(r.trader.book.positions.get('BTC')!.tf, want, `${rank60} vs ${rank240}`);
    const lose = want === '1h' ? '4h' : '1h';
    assert.deepEqual(r.signals.map((s) => [s.tf, s.queued, s.why]), [
      [want, true, null],
      [lose, false, `the ${want} heat call of this minute was offered (the hotter weight, a tie to 4h): one heat entry per coin per clock hour`],
    ], `${rank60} vs ${rank240}`);
    assert.equal(r.trader.status().lanes.fast.queue.length, 0);
  }

  // The hour used by a 1h heat entry is used for the 4h too: after a stop-out, a 4h call the same clock hour is not
  // offered; the next clock hour it is.
  const r = hourly();
  r.heat.fire('BTC', 1, r.H + 5 * MIN);
  assert.ok((await r.btc(r.H + 5 * MIN + 5_000)).target > 0);
  const p = r.trader.book.positions.get('BTC')!;
  const entry = r.px.v;
  r.px.v = p.stop - 0.001;
  assert.equal((await r.btc(r.H + 7 * MIN)).reason, 'exit: stop');
  r.px.v = entry;
  r.heat.fire4('BTC', 1, r.H + 20 * MIN);
  assert.equal((await r.btc(r.H + 20 * MIN + 5_000)).target, 0);
  assert.deepEqual([r.signals[1].tf, r.signals[1].queued, r.signals[1].why], ['4h', false, 'a heat entry was already offered for this coin this clock hour']);
  r.heat.fire4('BTC', -1, r.H + HOUR + 2 * MIN);
  assert.ok((await r.btc(r.H + HOUR + 2 * MIN + 5_000)).target < 0);
  assert.equal(r.trader.book.positions.get('BTC')!.tf, '4h');

  // When the hotter call cannot be offered for a reason that leaves the hour free (here: against the day), the other
  // horizon's call of the same minute still gets its turn.
  const d = hourly();
  d.heat.daily('BTC', -1, d.H - 2 * HOUR);
  d.heat.fire('BTC', 1, d.H + 5 * MIN, 1, 40);
  d.heat.fire4('BTC', -1, d.H + 5 * MIN, 5, 40);
  assert.ok((await d.btc(d.H + 5 * MIN + 5_000)).target < 0);
  assert.equal(d.trader.book.positions.get('BTC')!.tf, '4h');
  assert.deepEqual(d.signals.map((s) => [s.tf, s.queued, s.why]), [['1h', false, "against the day's direction (15m:ASI=low)"], ['4h', true, null]]);
});

test('daily context: a heat offer (1h or 4h) against the coin\'s live daily call is not made, and the clock hour stays open', async () => {
  const r = hourly();
  r.heat.daily('BTC', -1, r.H - 3 * HOUR);
  r.heat.fire('BTC', 1, r.H + 5 * MIN);
  assert.equal((await r.btc(r.H + 5 * MIN + 5_000)).target, 0);
  r.heat.fire4('BTC', 1, r.H + 6 * MIN);
  assert.equal((await r.btc(r.H + 6 * MIN + 5_000)).target, 0);
  assert.equal(r.trader.book.positions.size, 0);
  assert.deepEqual(r.signals.map((s) => [s.tf, s.queued, s.why, s.ref, s.heat_day_dir, s.heat_day_agree, s.heat_day_key]), [
    ['1h', false, "against the day's direction (15m:ASI=low)", null, -1, -1, '15m:ASI=low'],
    ['4h', false, "against the day's direction (15m:ASI=low)", null, -1, -1, '15m:ASI=low'],
  ]);
  assert.equal(r.audits.filter((x) => x.kind === 'setup_signal').length, 0, 'no setup was built');
  // A call on the day's side later the same clock hour: offered and entered (the refused calls did not use the hour).
  r.heat.fire('BTC', -1, r.H + 8 * MIN);
  assert.ok((await r.btc(r.H + 8 * MIN + 5_000)).target < 0);
  assert.equal(r.signals[2].heat_day_agree, 1);

  // A daily call whose day is over has no say; neither has the day with HEAT_PERPS_DAILY=off (it is not even asked).
  const e = hourly();
  e.heat.daily('BTC', -1, e.H + 5 * MIN - 24 * HOUR);
  e.heat.fire('BTC', 1, e.H + 5 * MIN);
  assert.ok((await e.btc(e.H + 5 * MIN + 5_000)).target > 0, 'expired');
  const o = hourly({ heat: { daily: 'off' } });
  o.heat.daily('BTC', -1, o.H - 3 * HOUR);
  o.heat.fire4('BTC', 1, o.H + 5 * MIN);
  assert.ok((await o.btc(o.H + 5 * MIN + 5_000)).target > 0, 'HEAT_PERPS_DAILY=off');
  assert.equal(o.heat.asked.some((a) => a.startsWith('day:')), false);
  assert.deepEqual([o.signals[0].heat_day_dir, o.trader.status().inputs.heat!.daily], [null, 'off']);
});

test('re-check: a waiting heat candidate is dropped once the day points against it; a 4h candidate is re-read against the 4 hours', async () => {
  const start = async (tf: '1h' | '4h') => {
    const r = hourly();
    if (tf === '4h') r.heat.fire4('BTC', 1, r.H + 5 * MIN); else r.heat.fire('BTC', 1, r.H + 5 * MIN);
    assert.equal((await r.btc(r.H + 5 * MIN + 5_000, { noEntry: 'paused' })).target, 0);
    assert.deepEqual(r.trader.status().lanes.fast.queue.map((c) => [c.kind, c.tf, c.dir]), [['heat', tf, 1]]);
    return r;
  };
  const resume = async (r: Rig & { H: number }, why: string) => {
    assert.equal((await r.btc(r.H + 7 * MIN + 5_000)).target, 0);
    assert.equal(r.trader.book.positions.size, 0);
    assert.equal(r.trader.status().recentSkips[0].reason, why);
    assert.equal(r.trader.status().lanes.fast.queue.length, 0);
    assert.equal(r.audits.filter((x) => x.kind === 'setup_skip' && x.data.reason === why).length, 1);
  };
  // The day turns against the waiting long, 1h and 4h alike.
  for (const tf of ['1h', '4h'] as const) {
    const a = await start(tf);
    a.heat.daily('BTC', -1, a.H + 6 * MIN);
    await resume(a, "heat: against the day's direction (15m:ASI=low)");
  }
  // A 4h candidate reads the 4 hours: turned, or gone.
  const b = await start('4h');
  b.heat.context4('BTC', -1, b.H + 6 * MIN, 2, 40);
  await resume(b, 'heat: the 4-hour direction turned down (5m:WAD=high)');
  const c = await start('4h');
  c.heat.ctx4.delete('BTC');
  await resume(c, 'heat: no live 4-hour direction left for this call');
  // The hour turning does not touch a 4h candidate, and a daily call on its side lets it through: it enters, scored by
  // the weight of the 4 hours' direction now.
  const d = await start('4h');
  d.heat.context('BTC', -1, d.H + 6 * MIN);
  d.heat.daily('BTC', 1, d.H + 6 * MIN);
  d.heat.context4('BTC', 1, d.H + 6 * MIN, 5, 40);
  assert.ok((await d.btc(d.H + 7 * MIN + 5_000)).target > 0);
  assert.deepEqual([d.trader.book.positions.get('BTC')!.tf, d.trader.book.positions.get('BTC')!.score], ['4h', heatWeight(5, 40, 10)]);
});

test('HEAT_PERP_HORIZONS: only the listed horizons are asked for and offered', async () => {
  const a = hourly({ heat: { horizons: [60] } });
  a.heat.fire4('BTC', 1, a.H + 5 * MIN);
  assert.equal((await a.btc(a.H + 5 * MIN + 5_000)).target, 0);
  assert.deepEqual([a.signals.length, a.heat.asked.filter((x) => x.startsWith('fired')), a.trader.status().inputs.heat!.horizons], [0, ['fired:BTC:60'], [60]]);
  const b = hourly({ heat: { horizons: [240] } });
  b.heat.fire('BTC', 1, b.H + 5 * MIN);
  assert.equal((await b.btc(b.H + 5 * MIN + 5_000)).target, 0);
  assert.deepEqual([b.signals.length, b.heat.asked.filter((x) => x.startsWith('fired'))], [0, ['fired:BTC:240']]);
  b.heat.fire4('BTC', 1, b.H + 6 * MIN);
  assert.ok((await b.btc(b.H + 6 * MIN + 5_000)).target > 0);
  // A 4h candidate left in the queue is not entered once 240 is no longer listed.
  const c = hourly();
  c.heat.fire4('BTC', 1, c.H + 5 * MIN);
  assert.equal((await c.btc(c.H + 5 * MIN + 5_000, { noEntry: 'paused' })).target, 0);
  const only60 = rig({ bars: { '1h': c.set.bars['1h']! }, now: c.H + 6 * MIN, px0: c.px.v, heat: { horizons: [60] } });
  fs.copyFileSync(path.join(c.dir, 'state.json'), path.join(only60.dir, 'state.json'));
  const restarted = only60.again();
  only60.heat.context4('BTC', 1, c.H + 5 * MIN);
  only60.hub.apply({ ticker: 'BTC-PERP', asset: 'BTC', ts: c.H + 6 * MIN, bid: c.px.v * 1.001 - 0.01, ask: c.px.v * 1.001 + 0.01, fractional: true });
  assert.equal((await restarted.targets({ positions: new Map(), hedge: [], now: c.H + 6 * MIN }, {})).find((x) => x.asset === 'BTC')!.target, 0);
  assert.equal(restarted.status().recentSkips[0].reason, 'heat: 4h heat entries are off (HEAT_PERP_HORIZONS)');
});

test('gate mode: the day gates nothing (only journaled); log mode journals the 4 hours and the day beside every setup', async () => {
  for (const mode of ['gate', 'log'] as const) {
    const g = chart('1h', 7, { mode });
    const against = -g.sig.dir as 1 | -1;
    g.heat.daily('BTC', against, g.now - HOUR);
    g.heat.context4('BTC', against, g.now - HOUR);
    const t = await g.btc(g.now);
    assert.equal(Math.sign(t.target), g.sig.dir, `${mode}: a 1h chart setup against the day and the 4 hours still enters: ${t.reason}`);
    for (const rec of [g.signals[0], g.trades[0]]) {
      assert.deepEqual([rec.heat_four_dir, rec.heat_four_agree, rec.heat_four_key, rec.heat_day_dir, rec.heat_day_agree, rec.heat_day_key],
        [against, -1, `5m:WAD=${against > 0 ? 'low' : 'high'}`, against, -1, `15m:ASI=${against > 0 ? 'high' : 'low'}`], mode);
    }
    assert.equal(g.heat.asked.some((a) => a.startsWith('fired')), false, `${mode} never asks for a fired call`);
  }
});

test('end to end with the lane: the reader\'s 240-minute row opens a 4h heat trade; its daily row against keeps it out', async () => {
  const cfg: HeatConfig = {
    enabled: true, callsFile: '', assets: ['BTC'], horizons: [15, 60], topN: 10, maxAgeSec: 90, entryLagSec: 45, sizing: true, context: 'size', contextBoost: 0.25,
    maxOpen: 2, maxPerCoin: 1, cooldownSec: 60, reentries15m: 3, reentriesHourly: 6, reentryLossStop: 0.5, flatTrips: 30, pilotLossUsd: 15, feeNetCheck: false, perps: 'entry',
    perpHorizons: [60, 240], perpsDaily: 'context', pairConflict: 'skip',
  };
  // Trimmed from the oracle's perp_pack.json at 52edf4c (BTC): the hottest 4-hour single (up) and the hottest daily single (down).
  const four = (barClose: number): HeatCallRow => ({ key: '1m:MFI14=very low', kind: 'single', tf: 1, h: 240, dir: 1, rank: 1, of: 40, heat: 18.013, share: 0.54442, odds: 3.4784, barClose });
  const day = (barClose: number): HeatCallRow => ({ key: '15m:ASI=high (rising in)', kind: 'single', tf: 15, h: 1440, dir: -1, rank: 1, of: 40, heat: 6.9474, share: 0.56695, odds: 8.2643, barClose });
  const snap = (t: number, calls: HeatCallRow[]): HeatSnapshot => ({ source: 'oracle-heat', run: 'R1', packSha: 'p', writtenAt: t + 2_000, coins: new Map([['BTC', { asOf: t, tableSha: 't', ok: true, calls }]]) });
  for (const withDay of [false, true]) {
    const lane = new HeatLane(cfg);
    const r = hourly({ provider: lane.direction });
    const t = r.H + 5 * MIN;
    // The daily row fired two hours earlier (the lane keeps it for a day), the 4-hour row now.
    if (withDay) lane.pending(t - 2 * HOUR + 5_000, snap(t - 2 * HOUR, [day(t - 2 * HOUR)]));
    lane.pending(t + 5_000, snap(t, [four(t)]));
    const out = await r.btc(t + 5_000);
    if (!withDay) {
      assert.ok(out.target > 0, out.reason);
      assert.deepEqual([r.trader.book.positions.get('BTC')!.tf, r.trader.book.positions.get('BTC')!.heat!.key], ['4h', '1m:MFI14=very low']);
    } else {
      assert.equal(out.target, 0);
      assert.deepEqual([r.signals[0].tf, r.signals[0].queued, r.signals[0].why], ['4h', false, "against the day's direction (15m:ASI=high (rising in))"]);
    }
  }
});

// ---- meta plan v2, D3: a heat setup skips the setup model's gates and its trained size weights ----

/** A heat entry on a fresh book; returns the trade's size, or the reason none opened. */
async function heatTrade(o: Omit<Parameters<typeof rig>[0], 'bars' | 'now' | 'px0'> = {}, before?: (r: ReturnType<typeof hourly>) => void) {
  const r = hourly({ heat: { topN: 10 }, ...o });
  before?.(r);
  r.heat.fire('BTC', 1, r.H + 5 * MIN, 1, 40);
  const t = await r.btc(r.H + 5 * MIN + 5_000);
  return { t, notional: t.target > 0 ? r.trader.book.positions.get('BTC')!.notional! : undefined, r };
}
const noModelFile = path.join(os.tmpdir(), 'heat-perps-no-such-model.json');

test('D3: a heat trade opens when the setup model file is missing', async () => {
  const x = await heatTrade({ deps: { modelPath: noModelFile } });
  assert.ok(x.t.target > 0, x.t.reason);
  assert.equal(x.r.trader.book.positions.get('BTC')!.kind, 'heat');
});

test('D3: a heat trade opens when validation is enforced and the setup model failed it', async () => {
  const params = defaultSetupParams({ book: lanes(), pilotMaxNotionalUsd: 1e9, requireValidation: true });
  setProbation(new Probation({ ...DEFAULT_PROBATION, mode: 'enforce' } as never));
  try {
    const failed = (r: ReturnType<typeof hourly>) => {
      const f = path.join(r.dir, 'setup_model.json');
      const m = JSON.parse(fs.readFileSync(f, 'utf8'));
      m.validation.fast.passed = false; m.validation.fast.reasons = ['test: failed']; m.trainedAt = 'x';
      fs.writeFileSync(f, JSON.stringify(m));
    };
    const x = await heatTrade({ deps: { params } }, failed);
    assert.ok(x.t.target > 0, x.t.reason);
  } finally { setProbation(undefined as never); }
});

test('D3: a heat trade opens when the setup SNN gate is on and leans against it', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'heat-perps-gate-'));
  const gateFile = path.join(dir, 'gate.json');
  fs.writeFileSync(gateFile, JSON.stringify({ enabled: true, minAgree: { fast: 0.4, slow: 0.4 } }));
  const x = await heatTrade({ deps: { snnGatePath: () => gateFile, snn: () => ({ up: { 60: 0.05, 240: 0.05 }, conf: {} }) as never } });
  assert.ok(x.t.target > 0, x.t.reason);
});

test('D3: a trained conviction multiplier and priority leave a heat trade\'s size alone', async () => {
  const plain = await heatTrade();
  const boosted = await heatTrade({ deps: { conviction: () => ({ mult: 3, priority: 9, why: 'test' }) } });
  assert.ok(plain.notional! > 0 && boosted.notional! > 0);
  assert.ok(Math.abs(boosted.notional! - plain.notional!) < 1e-6, `${boosted.notional} vs ${plain.notional}`);
});

test('D3: chart setups still need the setup model: without its file they do not enter', async () => {
  const r = chart('1h', 11, { deps: { modelPath: path.join(os.tmpdir(), 'heat-perps-no-such-model.json') } });
  const ts = await r.tick(r.now);
  assert.ok(ts.every((t) => t.target === 0), 'no chart trade without a setup model');
  assert.equal(r.trader.book.positions.size, 0);
});
