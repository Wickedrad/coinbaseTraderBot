import { openBankedUsd, openEntryFee, PositionBook } from '../bot/oms/positions';
import assert from 'node:assert/strict';
import fs from 'fs';
import path from 'path';
import { test } from 'node:test';
import { Alerter } from '../bot/alerts/alerter';
import { loadConfig } from '../bot/config';
import { Engine } from '../bot/engine';
import type { KalshiRest } from '../bot/kalshi/rest';
import type { MarketInfo } from '../bot/kalshi/types';
import { MarketData, Recorder } from '../bot/marketdata/marketData';
import { MetaModel } from '../bot/model/metaModel';
import { ModelHealth } from '../bot/model/modelHealth';
import { FEATURE_NAMES } from '../bot/model/features';
import { Oms } from '../bot/oms/oms';
import { PaperExchange } from '../bot/paper/paperExchange';
import { KillSwitch } from '../bot/risk/killSwitch';
import { RiskGateway, type RiskContext } from '../bot/risk/riskGateway';
import type { OrderIntent } from '../bot/oms/oms';
import { setMacro, type MacroService } from '../bot/macro/macroService';
import { Reconciler } from '../bot/recon/reconciler';
import { openExchange, tmpAudit, tmpDir } from './helpers';
import { Vault } from '../bot/vault/vault';
import { LiveLines, type LiveLineReading } from '../bot/strategy/liveLine';
import { ComponentTrials, DEFAULT_TRIALS, type TrialName } from '../bot/strategy/componentTrials';
import type { TaNetView } from '../bot/strategy/taConviction';
import { BalanceMonitor } from '../bot/vault/balanceMonitor';
import { SinuousEntryGate, type EntryVerdict } from '../bot/strategy/sinuousEntry';
import { AccuracyGate } from '../bot/strategy/accuracyGate';
import { SinuousExitGate, type CrossCheck } from '../bot/strategy/sinuousExit';
import { TakeProfitBench } from '../bot/strategy/takeProfitBench';
import { DEFAULT_PROBATION, Probation, setProbation } from '../bot/risk/probation';
import type { FillModel } from '../bot/tca/fillModel';
import { decide, type MarketView, type OrderPlan } from '../bot/strategy/fairValueStrategy';
import { ConfluenceRatchetExit } from '../bot/strategy/exitPolicies';
import type { HoldExits } from '../bot/strategy/holdExit';
import { exitOnlyPlan } from '../bot/strategy/exitOnlyLane';

async function setup(opts: { historySec?: number; askSize?: number; dailyLossUsd?: string; exitPolicy?: string; vault?: Vault; monitor?: BalanceMonitor; env?: Record<string, string>; trend?: number; curveExit?: SinuousExitGate; takeProfitBench?: TakeProfitBench; curveEntry?: SinuousEntryGate; accuracyGate?: AccuracyGate; liveLines?: LiveLines; trials?: ComponentTrials; model?: MetaModel; modelHealth?: ModelHealth; closeIn?: number; now?: () => number; openAgo?: number } = {}) {
  const dir = tmpDir();
  const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(40), DATA_DIR: dir, RISK_DAILY_LOSS_USD: opts.dailyLossUsd ?? '10', DOMINANCE_FEED: 'false', SPOT_FEED: 'false', EXIT_POLICY: opts.exitPolicy, STRATEGY_SERIES: 'KXBTC15M', SESSION_EDGE_NO_ENTRY: 'false', TENNIS_ENABLED: 'false', ...opts.env });
  const now = Date.now();
  const market: MarketInfo = { ticker: 'KXBTC15M-TEST', seriesTicker: 'KXBTC15M', status: 'open', openTime: now - (opts.openAgo ?? 300_000), closeTime: now + (opts.closeIn ?? 600_000), floorStrike: 60000, tickSize: 0.01 };
  const rest = {
    getSeriesFees: async () => ({ feeType: 'quadratic', multiplier: 1 }),
    getOpenMarkets: async () => [market],
    getMarket: async () => market,
  } as unknown as KalshiRest;
  const audit = tmpAudit();
  const md = new MarketData(cfg, rest, undefined, new Recorder(path.join(dir, 'rec')));
  await md.refreshCatalog(now);
  // Fresh book and a warmed-up index slightly above the strike.
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.45, size: 50 }], asks: [{ price: 0.6, size: opts.askSize ?? 50 }] }, now);
  const idx = md.index.get('BTC')!;
  let seed = 1;
  const rand = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
  let x = Math.log(60010);
  // historySec: seconds of index history before the test starts (60: just after a restart, the volatility still warming up).
  const span = opts.historySec ?? (opts.trend ? 1800 : 600);
  if (opts.trend) x -= opts.trend * span; // end just above the strike, as without a trend
  for (let s = span; s >= 0; s--) { x += (opts.trend ? 0.00004 : 0.0002) * (rand() - 0.5) + (opts.trend ?? 0); idx.add(Math.exp(x), now - s * 1000); }

  const paper = new PaperExchange(undefined, 200, (t) => md.books.get(t), () => ({ takerMultiplier: 1, makerMultiplier: 0 }));
  const kill = new KillSwitch(path.join(dir, 'kill.json'), audit);
  // A test that drives the engine's clock drives the OMS's too, as one clock runs both in the bot: the in-flight exit guard
  // compares an order's send time with the evaluation's.
  const oms = new Oms({ gateway: paper, audit, statePath: path.join(dir, 'oms.json'), feesFor: (t) => md.feesFor(t), sleep: async () => undefined, ...(opts.now ? { now: opts.now } : {}) });
  kill.bindCancelAll((r) => oms.cancelAll(r));
  paper.on('fill', (f) => oms.onFill(f));
  paper.on('order', (o) => oms.onExchangeOrder(o));
  const recon = new Reconciler({ gateway: paper, oms, audit, getMarket: rest.getMarket, onPersistentBreak: (r) => void kill.engage(r, 'recon') });
  const deps = { cfg, audit, alerter: new Alerter([], audit), md, gateway: paper, oms, risk: new RiskGateway(cfg.risk), kill, recon, model: opts.model ?? MetaModel.identity(), vault: opts.vault, balanceMonitor: opts.monitor, exchangeStatus: openExchange(), curveExit: opts.curveExit, takeProfitBench: opts.takeProfitBench, curveEntry: opts.curveEntry, accuracyGate: opts.accuracyGate, liveLines: opts.liveLines, trials: opts.trials, modelHealth: opts.modelHealth, now: opts.now };
  const engine = new Engine(deps);
  return { cfg, md, paper, oms, kill, recon, engine, market, audit, deps };
}

test('engine places risk-checked post-only quotes through the OMS and paper exchange', async () => {
  const { engine, recon, paper, oms, market, md } = await setup();
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  await engine.tick();
  const open = await paper.getOpenOrders();
  assert.ok(open.length >= 1, `status: ${JSON.stringify(engine.status.get(market.ticker))}`);
  for (const o of open) {
    const rec = oms.get(o.clientOrderId!)!;
    assert.equal(rec.postOnly, true);
    assert.ok(rec.expirationTime! <= Math.floor(market.closeTime / 1000));
    assert.ok(o.price > 0.45 - 1e-9 && o.price < 0.6 + 1e-9);
  }
  const st = engine.status.get(market.ticker)!;
  assert.ok(st.fairValue! > 0.5, 'spot above strike');
  // Every entry is put to the adversary; without TA / confluence evidence it keeps its normal size.
  assert.ok(st.adversary, 'adversary verdict recorded');
  assert.ok(st.adversary!.multiplier >= 1);
  // Stale index: quotes are pulled (fail closed), not left resting.
  md.index.get('BTC')!.add(60000, Date.now() - 1); // no-op: out of order
  const idx = md.index.get('BTC')!;
  (idx as any).points.forEach((p: { ts: number }) => { p.ts -= 60_000; });
  await engine.tick();
  assert.equal((await paper.getOpenOrders()).length, 0);
  assert.equal(engine.status.get(market.ticker)!.blocked, 'index stale');
});

/** An entry curve whose verdict the test sets: YES bids against it or not. */
class StubCurve extends SinuousEntryGate {
  againstYes = false;
  override verdict(_ticker: string, side: 'bid' | 'ask'): EntryVerdict {
    return side === 'bid' && this.againstYes ? { against: true, slope: -0.012 } : { against: false, slope: 0 };
  }
}

test('entry curve gate: no YES bid while the book runs against it, and a resting one is pulled; monitor only notes it', async () => {
  const quotes = (oms: Oms, ticker: string, side: 'bid' | 'ask') => oms.liveOrders().filter((o) => o.ticker === ticker && o.side === side && o.purpose === 'quote' && !o.cancelRequested);
  const gate = new StubCurve({ mode: 'gate', slope: 0.005 });
  const g = await setup({ curveEntry: gate });
  g.engine.balance = (await g.recon.run('startup'))!.balance;
  await g.engine.tick();
  assert.equal(quotes(g.oms, g.market.ticker, 'bid').length, 1, `with the curve the bid rests: ${JSON.stringify(g.engine.status.get(g.market.ticker)?.notes)}`);
  gate.againstYes = true;
  await g.engine.tick();
  assert.equal(quotes(g.oms, g.market.ticker, 'bid').length, 0, 'against it: pulled');
  assert.match(g.engine.status.get(g.market.ticker)!.notes.join(' | '), /entry curve holds the YES bid: the book runs 1\.20c a 10 s against it/);
  // Monitor mode: the same verdict is only a note; the bid goes out.
  const watch = new StubCurve({ mode: 'monitor', slope: 0.005 });
  watch.againstYes = true;
  const m = await setup({ curveEntry: watch });
  m.engine.balance = (await m.recon.run('startup'))!.balance;
  await m.engine.tick();
  assert.equal(quotes(m.oms, m.market.ticker, 'bid').length, 1);
  assert.match(m.engine.status.get(m.market.ticker)!.notes.join(' | '), /entry curve would hold the YES bid/);
  assert.equal(m.engine.curveEntryStatus()!.mode, 'monitor');
});

test('until a vol forecast is validated, fair value prices with the EWMA sigma x VOL_FALLBACK_MULT (1.15 by default)', async () => {
  for (const [env, mult] of [[{}, 1.15], [{ VOL_FALLBACK_MULT: '1' }, 1]] as const) {
    const { engine, recon, market } = await setup({ env });
    const r = await recon.run('startup');
    engine.balance = r!.balance;
    await engine.tick();
    const st = engine.status.get(market.ticker)!;
    assert.ok(Math.abs(st.sigmaPricing! / st.sigma! - mult) < 1e-9, `sigma ${st.sigma} priced at ${st.sigmaPricing}`);
    assert.equal(engine.guardStatus().volFallbackMult, mult);
  }
});

test('an order is funded from its market\'s exchange shard: no cash there, no order, and the refusal says where the cash is', async () => {
  const { engine, recon, paper, market, md, audit } = await setup();
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  // Crypto markets trade on shard 2; the account's cash sits on shard 0 (the Kalshi app moves it per order, the API does not).
  md.markets.get(market.ticker)!.exchangeIndex = 2;
  (paper as unknown as { shardBalances: () => Record<number, number> }).shardBalances = () => ({ 0: r!.balance!, 2: 0 });
  assert.equal(engine.freeCash(2), 0);
  assert.equal(engine.freeCash(), r!.balance);
  await engine.tick();
  assert.equal((await paper.getOpenOrders()).length, 0);
  const why = audit.tail(200, 'risk_reject').map((x) => JSON.stringify(x.data)).join('\n');
  assert.match(why, /free cash \$0\.00 on Kalshi exchange shard 2/);
  assert.match(why, /kalshi\.com\/account\/exchange-indexes/);
  // Cash on the market's shard: the quote goes out.
  const f = await setup();
  const r2 = await f.recon.run('startup');
  f.engine.balance = r2!.balance;
  f.md.markets.get(f.market.ticker)!.exchangeIndex = 2;
  (f.paper as unknown as { shardBalances: () => Record<number, number> }).shardBalances = () => ({ 0: 0, 2: r2!.balance! });
  await f.engine.tick();
  assert.ok((await f.paper.getOpenOrders()).length >= 1);
});

test('a location-attestation refusal on a tennis order pauses tennis only; on any other order, all new orders', async () => {
  const { engine, oms, cfg } = await setup();
  await engine.start();
  try {
    const msg = 'HTTP 403: {"error":{"code":"Your_location_attestation_for_API_trading_is_missing_or_expired."}}';
    oms.emit('account_blocked', msg, { ticker: `${cfg.tennis.series[0]}-26OCT22ABCDEF-ABC` });
    assert.match(engine.kalshiAccountStatus().sportsHalt ?? '', /tennis/);
    assert.ok(!engine.haltReasons().some((r) => /location/.test(r)), 'crypto keeps trading');
    oms.emit('account_blocked', msg, { ticker: 'KXBTC15M-TEST' });
    assert.ok(engine.haltReasons().some((r) => /location attestation/.test(r)));
  } finally { engine.stop(); }
});

test('paper training trades: with no edge anywhere, 1 contract is still traded on the model side, once per contract', async () => {
  const { engine, recon, oms, market, md } = await setup({ env: { STRATEGY_MIN_EDGE: '0.5', PAPER_EXPLORE: 'false', PAPER_TRAINING_TRADES_PER_HOUR: '12' } });
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.55, size: 50 }], asks: [{ price: 0.6, size: 50 }] }, Date.now());
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  await engine.tick();
  const entries = oms.allOrders().filter((o) => o.ticker === market.ticker && o.purpose === 'entry');
  assert.equal(entries.length, 1, `status: ${JSON.stringify(engine.status.get(market.ticker))}`);
  assert.equal(entries[0].count, 1);
  // Spot above the strike: the model favours YES, bought at the ask.
  assert.equal(entries[0].side, 'bid');
  assert.equal(entries[0].price, 0.6);
  // One per contract: a second pass does not add another.
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.55, size: 50 }], asks: [{ price: 0.6, size: 50 }] }, Date.now());
  await engine.tick();
  assert.equal(oms.allOrders().filter((o) => o.ticker === market.ticker && o.purpose === 'entry').length, 1);
});

test('paper (PAPER_OUTSIDE_PRICE_FALLBACK=true) prices from Coinbase spot when the Kalshi index is stale or too sparse for volatility', async () => {
  const { engine, recon, market, md } = await setup({ env: { PAPER_OUTSIDE_PRICE_FALLBACK: 'true' } });
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  const now = Date.now();
  (md.index.get('BTC') as any).points.forEach((p: { ts: number }) => { p.ts -= 120_000; });
  const spot = md.spot.get('BTC')!;
  let x = Math.log(60010);
  for (let sec = 600; sec >= 0; sec--) { x += 0.0001 * Math.sin(sec); spot.add(Math.exp(x), now - sec * 1000); }
  await engine.tick();
  const st = engine.status.get(market.ticker)!;
  assert.equal(st.blocked, undefined, JSON.stringify(st));
  assert.ok(Math.abs(st.spot! - 60010) < 50);
});

test('paper (PAPER_OUTSIDE_PRICE_FALLBACK=true) prices from Binance when both the Kalshi index and Coinbase are stale (sparse prints)', async () => {
  const { engine, recon, market, md } = await setup({ env: { PAPER_OUTSIDE_PRICE_FALLBACK: 'true' } });
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  const now = Date.now();
  (md.index.get('BTC') as any).points.forEach((p: { ts: number }) => { p.ts -= 120_000; });
  md.spot.get('BTC')!.add(59000, now - 90_000); // Coinbase quiet for 90 s
  const bn = md.binance.get('BTC')!;
  let x = Math.log(60020);
  for (let sec = 600; sec >= 0; sec--) { x += 0.0001 * Math.cos(sec); bn.add(Math.exp(x), now - sec * 1000); }
  await engine.tick();
  const st = engine.status.get(market.ticker)!;
  assert.equal(st.blocked, undefined, JSON.stringify(st));
  assert.ok(Math.abs(st.spot! - 60020) < 60, `priced from Binance (${st.spot})`);
  assert.ok(engine.feedHealth().BTC.binance!.points > 500);
});

test('market data: Binance prices are copied into their own series, new prints only', async () => {
  const { md } = await setup();
  const prices = new Map([['BTC', { price: 61000, ts: 1000 }]]);
  (md as any).dominance = { priceOf: (s: string) => prices.get(s) };
  md.pullBinance();
  md.pullBinance(); // same print: not duplicated
  assert.equal(md.binance.get('BTC')!.health(2000).points, 1);
  prices.set('BTC', { price: 61010, ts: 2000 });
  md.pullBinance();
  assert.equal(md.binance.get('BTC')!.latest()!.value, 61010);
});

test('paper (PAPER_OUTSIDE_PRICE_FALLBACK=true): an up/down strike comes from the Coinbase opening minute when the Kalshi index missed it', async () => {
  const { md, market } = await setup({ env: { PAPER_OUTSIDE_PRICE_FALLBACK: 'true' } });
  const am = md.markets.get(market.ticker)!;
  am.strike = undefined;
  (md.index.get('BTC') as any).points.length = 0;
  assert.equal(md.strikeFor(am), undefined);
  const spot = md.spot.get('BTC')!;
  for (let t = market.openTime - 90_000; t <= market.openTime + 5_000; t += 5_000) spot.add(60123, t);
  assert.equal(md.strikeFor(am), 60123);
  assert.equal(am.strikeSource, 'computed');
});

test('paper uses live\'s stale-data limits (a 5 s book, a 3 s index)', () => {
  const paper = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(40) });
  assert.equal(paper.risk.maxIndexAgeMs, 3000);
  assert.equal(paper.risk.maxBookAgeMs, 5000);
});

test('paper: an order live would not have sent is tagged at its first fill, for the live-equivalent P&L', async () => {
  // No probation is set in tests and the identity model has no validation report: with the model gating live orders
  // (LIVE_ALLOW_UNVALIDATED_MODEL=false), live would reject every entry.
  const { engine, recon, paper, market, audit } = await setup({ env: { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false', LIVE_ALLOW_UNVALIDATED_MODEL: 'false' } });
  engine.balance = (await recon.run('startup'))!.balance;
  await engine.tick();
  const o = (await paper.getOpenOrders())[0];
  assert.ok(o, 'a maker quote rests');
  assert.equal(audit.tail(50, 'paper_live_block').length, 0, 'nothing is written before a fill');
  // A taker trades through it.
  if (o.side === 'bid') paper.onTrade(market.ticker, +(o.price - 0.01).toFixed(2), 100, 'no');
  else paper.onTrade(market.ticker, +(o.price + 0.01).toFixed(2), 100, 'yes');
  const tags = audit.tail(50, 'paper_live_block').map((r) => r.data as { clientOrderId: string; reasons: string[] });
  assert.deepEqual(tags, [{ clientOrderId: o.clientOrderId, reasons: ['model not validated, probation benched'] }]);
});

test('paper: by default live sends what an unvalidated model wants, so nothing is tagged for it', async () => {
  const { engine, recon, paper, market, audit } = await setup({ env: { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false' } });
  engine.balance = (await recon.run('startup'))!.balance;
  await engine.tick();
  const o = (await paper.getOpenOrders())[0];
  assert.ok(o, 'a maker quote rests');
  if (o.side === 'bid') paper.onTrade(market.ticker, +(o.price - 0.01).toFixed(2), 100, 'no');
  else paper.onTrade(market.ticker, +(o.price + 0.01).toFixed(2), 100, 'yes');
  assert.equal(audit.tail(50, 'paper_live_block').length, 0);
});

test('paper, like live: no new entry in a series until its fee schedule is verified; an exit still goes out', async () => {
  const { engine, recon, paper, market, md, oms } = await setup();
  engine.balance = (await recon.run('startup'))!.balance;
  // The series reports a fee type the published schedule does not define as a formula.
  md.feeBook.setSeries(market.seriesTicker, { feeType: 'flat', multiplier: 1 }, Date.now());
  await engine.tick();
  assert.equal((await paper.getOpenOrders()).length, 0);
  const st = engine.status.get(market.ticker)!;
  assert.equal(st.blocked, undefined);
  assert.match(st.feeBlock ?? '', /fee type flat is not a formula the fee schedule defines/);
  // Long 10 NO bought at 0.40; the market bids NO 0.20, above the model's value: cutting the loser goes out.
  oms.onFill({ tradeId: 'fx1', orderId: '', ticker: market.ticker, side: 'ask', count: 10, price: 0.6, isTaker: true, fee: 0.17, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.78, size: 50 }], asks: [{ price: 0.8, size: 50 }] }, Date.now());
  await engine.tick();
  assert.equal(oms.allOrders(500).filter((o) => o.ticker === market.ticker && o.reduceOnly).length, 1, engine.status.get(market.ticker)!.notes.join(' | '));
});

test('no orders until reconciliation is clean and balance known', async () => {
  const { engine, paper } = await setup();
  await engine.tick();
  assert.equal((await paper.getOpenOrders()).length, 0);
});

test('daily loss limit trips the persistent kill switch and cancels everything', async () => {
  const { engine, recon, paper, kill, oms, market } = await setup({ dailyLossUsd: '0.5' });
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  await engine.tick();
  assert.ok((await paper.getOpenOrders()).length >= 1);
  // Simulate a realized loss today.
  oms.onFill({ tradeId: 'L', orderId: '', ticker: 'OTHER', side: 'bid', count: 2, price: 0.5, isTaker: true, fee: 0.02, ts: Date.now() }, { closeTs: Date.now() - 1, asset: 'BTC' });
  oms.settle('OTHER', 'no');
  await engine.tick();
  assert.equal(kill.engaged, true);
  assert.equal((await paper.getOpenOrders()).length, 0);
  assert.ok(engine.status.get(market.ticker));
});

/** A crypto position bought on the paper exchange (a reduce-only exit needs it there too), then the book moved to `book`. */
async function heldUnderKill(side: 'bid' | 'ask', price: number, count: number, book: [number, number], opts: { topSize?: number; source?: string; closeIn?: number; curveExit?: SinuousExitGate; accuracyGate?: AccuracyGate; trials?: ComponentTrials } = {}) {
  const g = await setup({ env: { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false' }, closeIn: opts.closeIn, curveExit: opts.curveExit, accuracyGate: opts.accuracyGate, trials: opts.trials });
  g.engine.balance = (await g.recon.run('startup'))!.balance;
  const t = g.market.ticker;
  g.md.book(t).applySnapshot(side === 'bid' ? { bids: [{ price: price - 0.02, size: 100 }], asks: [{ price, size: 100 }] } : { bids: [{ price, size: 100 }], asks: [{ price: price + 0.02, size: 100 }] }, Date.now());
  await g.oms.submit({ ticker: t, asset: 'BTC', windowCloseTs: g.market.closeTime, side, price, count, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'entry', fairValue: 0.5, modelId: 'm', decisionId: 'e' });
  assert.equal(g.oms.positions.position(t), side === 'bid' ? count : -count);
  g.md.book(t).applySnapshot({ bids: [{ price: book[0], size: opts.topSize ?? 50 }], asks: [{ price: book[1], size: opts.topSize ?? 50 }] }, Date.now());
  await g.kill.engage('5 consecutive order errors (test)', opts.source ?? 'oms');
  const sent = () => g.oms.allOrders(500).filter((o) => o.ticker === t && o.decisionId !== 'e');
  const killExits = () => g.audit.tail(500, 'decision').map((x) => x.data as Record<string, unknown>).filter((x) => x.leg === 'kill_exit');
  return { ...g, t, sent, killExits, notes: () => g.engine.status.get(t)?.notes.join(' | ') ?? 'not evaluated' };
}

test('kill switch engaged: a crypto YES position not in profit after fees is sold at the bid, once, reduce-only; no entry', async () => {
  // 30 YES bought at 0.60, the book now 0.20 / 0.25.
  const g = await heldUnderKill('bid', 0.6, 30, [0.2, 0.25]);
  assert.ok(g.engine.entryGuards().includes('kill switch engaged'), 'the kill switch is an entry guard');
  await g.engine.tick();
  await g.engine.tick();
  assert.deepEqual(g.sent().map((o) => [o.side, o.price, o.count, o.reduceOnly, o.timeInForce, o.purpose]), [['ask', 0.2, 30, true, 'immediate_or_cancel', 'exit']]);
  assert.equal(g.oms.positions.position(g.t), 0);
  assert.equal(g.killExits().length, 1);
  assert.match(String(g.killExits()[0].why), /^kill switch engaged: -\$12\.\d\d after fees at bid 0\.2, not in profit, not held to settlement$/);
  assert.equal(g.audit.tail(500, 'risk_reject').length, 0);
});

test('kill switch engaged: a crypto NO position not in profit is sold at its bid (YES bought at the ask); a thin bid retries after 30 s', async () => {
  // 30 NO bought at 0.40 (YES sold at 0.60); the book now 0.75 / 0.80, a NO bid of 0.20 for 10 contracts only.
  const g = await heldUnderKill('ask', 0.6, 30, [0.75, 0.8], { topSize: 10 });
  await g.engine.tick();
  assert.deepEqual(g.sent().map((o) => [o.side, o.price, o.count, o.reduceOnly, o.timeInForce]), [['bid', 0.8, 30, true, 'immediate_or_cancel']]);
  assert.equal(g.oms.positions.position(g.t), -20, 'the IOC took the 10 on offer');
  assert.match(String(g.killExits()[0].why), /^kill switch engaged: -\$\d+\.\d\d after fees at NO bid 0\.2, not in profit/);
  // At most one attempt per market every 30 s.
  await g.engine.tick();
  assert.equal(g.sent().length, 1);
  const stamps = (g.engine as unknown as { killExitTs: Map<string, number> }).killExitTs;
  stamps.set(g.t, stamps.get(g.t)! - 30_000);
  await g.engine.tick();
  assert.deepEqual(g.sent().map((o) => [o.side, o.price, o.count]).sort((x, y) => Number(y[2]) - Number(x[2])), [['bid', 0.8, 30], ['bid', 0.8, 20]]);
  assert.equal(g.audit.tail(500, 'risk_reject').length, 0);
});

/** An accuracy gate and component trials that count the evaluations fed to their scorecards. */
class CountingAccuracyGate extends AccuracyGate {
  observed = 0;
  override observe(ticker: string, tauSec: number, pYes: number, mid: number): void { this.observed++; super.observe(ticker, tauSec, pYes, mid); }
}
class CountingTrials extends ComponentTrials {
  recorded = 0;
  override record(): void { this.recorded++; }
}

test('kill switch engaged: a crypto winner is not dumped; its take-profit still sells it once it gives back a third of its best', async () => {
  // 10 YES bought at 0.40; at a 0.56 bid it is about +$1.25 after fees: held, the take-profit armed, nothing sent.
  const gate = new CountingAccuracyGate({ enabled: true, window: 150, minMarkets: 40 });
  const trials = new CountingTrials(DEFAULT_TRIALS);
  const g = await heldUnderKill('bid', 0.4, 10, [0.56, 0.58], { accuracyGate: gate, trials });
  await g.engine.tick();
  await g.engine.tick();
  assert.deepEqual(g.sent(), [], g.notes());
  assert.equal(g.oms.positions.position(g.t), 10);
  assert.equal(g.killExits().length, 0);
  assert.match(g.notes(), /take-profit armed/);
  assert.match(g.notes(), /kill switch engaged/);
  // Only winners are evaluated under the kill: they do not feed the accuracy gate's or the trials' scorecards (a sample
  // picked by the result).
  assert.deepEqual([gate.observed, trials.recorded], [0, 0]);
  // Back to 0.50 with only 4 bid: more than a third of the best gain given back. The take-profit sells the 4 on offer at
  // the bid, through the kill.
  g.md.book(g.t).applySnapshot({ bids: [{ price: 0.5, size: 4 }], asks: [{ price: 0.52, size: 50 }] }, Date.now());
  await g.engine.tick();
  assert.deepEqual(g.sent().map((o) => [o.side, o.price, o.count, o.reduceOnly, o.timeInForce]), [['ask', 0.5, 4, true, 'immediate_or_cancel']], g.notes());
  assert.equal(g.oms.positions.position(g.t), 6);
  // At most one attempt per market every 30 s, the winner's exits included.
  await g.engine.tick();
  assert.equal(g.sent().length, 1, g.notes());
  assert.match(g.notes(), /kill switch engaged: exit waits, one attempt per market every 30 s/);
  const stamps = (g.engine as unknown as { killExitTs: Map<string, number> }).killExitTs;
  stamps.set(g.t, stamps.get(g.t)! - 30_000);
  g.md.book(g.t).applySnapshot({ bids: [{ price: 0.5, size: 50 }], asks: [{ price: 0.52, size: 50 }] }, Date.now());
  await g.engine.tick();
  assert.deepEqual(g.sent().map((o) => [o.side, o.price, o.count]).sort((x, y) => Number(y[2]) - Number(x[2])), [['ask', 0.5, 6], ['ask', 0.5, 4]], g.notes());
  assert.equal(g.oms.positions.position(g.t), 0);
  const why = g.audit.tail(200, 'decision').flatMap((d) => ((d.data as { place?: Array<{ why: string }> }).place ?? []).map((p) => p.why));
  assert.ok(why.some((w) => w.startsWith('take-profit: ')), why.join(' | '));
  assert.equal(g.killExits().length, 0);
  assert.equal(g.audit.tail(500, 'risk_reject').length, 0);
  assert.deepEqual([gate.observed, trials.recorded], [0, 0]);
});

test('kill switch engaged: a crypto winner\'s resting sell (exit curve rest mode) waits for the reset; nothing is refused', async () => {
  // 10 YES bought at 0.40, bid 0.45: in profit after fees. Outside the kill the curve rests a sell at 0.55 (good till cancelled).
  const curveExit = new (class extends SinuousExitGate { override restTarget(): number | undefined { return 0.55; } })({ mode: 'rest', minNetProfit: 0.015 }, { minTrades: 20, t: 1, maxLossUsd: 25, window: 200 });
  const g = await heldUnderKill('bid', 0.4, 10, [0.45, 0.47], { curveExit });
  await g.engine.tick();
  assert.deepEqual(g.sent(), [], g.notes());
  assert.match(g.notes(), /kill switch engaged: resting orders wait for the reset/);
  assert.equal(g.audit.tail(500, 'risk_reject').length, 0);
  assert.equal(g.oms.positions.position(g.t), 10);
});

test('kill switch engaged: a crypto loser in the final seconds before the close rides to settlement, as outside the kill', async () => {
  // 30 YES bought at 0.60, book 0.20 / 0.25, the market closing in 45 s (inside STRATEGY_NO_EXIT_BEFORE_CLOSE_SEC, 60 s).
  const g = await heldUnderKill('bid', 0.6, 30, [0.2, 0.25], { closeIn: 45_000 });
  assert.ok(g.cfg.strategy.noExitBeforeCloseSec >= 45, String(g.cfg.strategy.noExitBeforeCloseSec));
  await g.engine.tick();
  assert.deepEqual(g.sent(), []);
  assert.equal(g.killExits().length, 0);
  assert.equal(g.oms.positions.position(g.t), 30);
});

test('kill switch engaged by STOP ALL (an operator): crypto positions are left alone, as before', async () => {
  const g = await heldUnderKill('bid', 0.6, 30, [0.2, 0.25], { source: 'api:127.0.0.1' });
  await g.engine.tick();
  assert.deepEqual(g.sent(), []);
  assert.equal(g.oms.positions.position(g.t), 30);
});

test('kill switch: STOP ALL pressed after an automatic trip also leaves crypto positions alone', async () => {
  // The order-error trip engaged the switch; the operator then presses STOP ALL (POST /api/kill).
  const g = await heldUnderKill('bid', 0.6, 30, [0.2, 0.25], { source: 'oms' });
  await g.kill.engage('operator STOP ALL', 'api:127.0.0.1');
  assert.equal(g.kill.status().source, 'oms', 'the first trip stays the recorded cause');
  assert.equal(g.kill.manual, true);
  await g.engine.tick();
  assert.deepEqual(g.sent(), []);
  assert.equal(g.killExits().length, 0);
  assert.equal(g.oms.positions.position(g.t), 30);
});

test('opt-in confluence ratchet runs in the engine and starts in fair-value mode', async () => {
  const { engine, recon, market, cfg } = await setup({ exitPolicy: 'confluence_ratchet' });
  assert.equal(cfg.strategy.exitPolicy, 'confluence_ratchet');
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  await engine.tick();
  // No position and no confluence data: normal fair-value behaviour, quotes still placed.
  assert.equal(engine.status.get(market.ticker)!.exitMode, 'fair_value');
});

test('a model hot swap keeps the hunt of a held position and drops the hunts of flat markets', async () => {
  const { engine, recon, market, oms } = await setup({ exitPolicy: 'confluence_ratchet' });
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  oms.onFill({ tradeId: 'h1', orderId: '', ticker: market.ticker, side: 'bid', count: 5, price: 0.45, isTaker: true, fee: 0.05, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
  await engine.tick();
  const hunts = (engine as unknown as { hunts: Map<string, unknown> }).hunts;
  const held = hunts.get(market.ticker);
  assert.ok(held, 'the held position has a hunt');
  hunts.set('FLAT-MARKET', {});
  engine.setModel(MetaModel.identity(4e-5));
  assert.equal(hunts.get(market.ticker), held, 'same hunt object: anchor, stop and lock judgement intact');
  assert.equal(hunts.has('FLAT-MARKET'), false);
});

test('a hunt that sits out drops itself once the market is flat (a later position starts a fresh hunt)', async () => {
  // Hunting is not allowed here (another exit policy: the same branch as a bench or an unvalidated hunt in live).
  const { engine, recon, market } = await setup({ exitPolicy: 'take_profit' });
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  const hunts = (engine as unknown as { hunts: Map<string, unknown> }).hunts;
  hunts.set(market.ticker, { stale: true }); // a hunt left from a position that closed while hunting sat out
  await engine.tick();
  assert.equal(hunts.has(market.ticker), false, 'flat while sitting out: the stale hunt is gone');
});

test('exit curve: a profitable fair-value exit waits for a spike above the curve', async () => {
  const curveExit = new SinuousExitGate({ mode: 'gate', minNetProfit: 0.015 }, { minTrades: 20, t: 1, maxLossUsd: 25, window: 200 });
  const { engine, recon, market, md, oms } = await setup({ curveExit });
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  // Long 10 NO bought at 0.05 (YES sold at 0.95). The model values NO near 0.01 while the market bids it 0.20:
  // the fair-value exit wants out, at a profit, so it waits for the curve.
  oms.onFill({ tradeId: 'e1', orderId: '', ticker: market.ticker, side: 'ask', count: 10, price: 0.95, isTaker: true, fee: 0.04, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.78, size: 50 }], asks: [{ price: 0.8, size: 50 }] }, Date.now());
  const exits = () => oms.allOrders(500).filter((o) => o.ticker === market.ticker && o.reduceOnly);
  await engine.tick();
  const st = engine.status.get(market.ticker)!;
  assert.equal(st.position, -10);
  assert.equal(exits().length, 0, `held: ${st.notes.join(' | ')}`);
  assert.equal(st.curve?.signal, false);
  assert.ok(st.notes.some((n) => /curve: holding the profit exit at 0.2 /.test(n)), st.notes.join(' | '));
  assert.deepEqual(curveExit.status().holding, [market.ticker]);
  // A sweep into NO (YES offered heavily lower): the NO micro-price jumps well above the curve, and the exit goes out.
  await new Promise((res) => setTimeout(res, 20));
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.6, size: 10 }], asks: [{ price: 0.62, size: 500 }] }, Date.now());
  await engine.tick();
  const st2 = engine.status.get(market.ticker)!;
  assert.equal(st2.curve?.reason, 'DEVIATION_SPIKE', JSON.stringify(st2.curve));
  assert.equal(exits().length, 1, st2.notes.join(' | '));
  assert.ok(st2.notes.some((n) => /curve DEVIATION_SPIKE: profit exit at 0.38/.test(n)), st2.notes.join(' | '));
  assert.deepEqual(curveExit.status().holding, []);
});

/** An exit curve in rest mode whose swing-top estimate the test sets. */
class StubRest extends SinuousExitGate {
  target: number | undefined = 0.55;
  override restTarget(): number | undefined { return this.target; }
}

test('exit curve rest mode: the held position rests its sell at the curve target; an exit crossing the book pulls it', async () => {
  const curveExit = new StubRest({ mode: 'rest', minNetProfit: 0.015 }, { minTrades: 20, t: 1, maxLossUsd: 25, window: 200 });
  const { engine, recon, market, md, oms, audit } = await setup({ curveExit, env: { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false' } });
  engine.balance = (await recon.run('startup'))!.balance;
  // Long 10 YES bought at 0.40 as a maker: the take-profit floor is 4c, so never below 0.44.
  oms.onFill({ tradeId: 'r1', orderId: '', ticker: market.ticker, side: 'bid', count: 10, price: 0.4, isTaker: false, fee: 0, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.45, size: 50 }], asks: [{ price: 0.6, size: 50 }] }, Date.now());
  const sells = () => oms.liveOrders().filter((o) => o.ticker === market.ticker && o.side === 'ask' && o.purpose === 'exit' && o.timeInForce === 'good_till_canceled' && !o.cancelRequested);
  await engine.tick();
  const notes = () => engine.status.get(market.ticker)!.notes.join(' | ');
  assert.deepEqual(sells().map((o) => [o.price, o.count, o.postOnly, o.reduceOnly]), [[0.55, 10, true, false]], notes());
  const why = audit.tail(50, 'decision').flatMap((d) => ((d.data as { place?: Array<{ why: string }> }).place ?? []).map((p) => p.why));
  assert.ok(why.some((w) => /^exit curve: rest 0\.55 \(\+0\.150 a contract net, swing top 0\.550\)/.test(w)), why.join(' | '));
  // The bid runs to 0.80 (a book jump without trades, so the resting sell is not filled here): the take-profit arms and
  // the winner runs.
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.8, size: 50 }], asks: [{ price: 0.82, size: 50 }] }, Date.now());
  await engine.tick();
  assert.equal(sells().length, 1, notes());
  // Back to 0.60, more than a third of the best gain given back: the take-profit crosses the book, and the resting sell
  // is pulled first so the two cannot sell more than is held.
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.6, size: 50 }], asks: [{ price: 0.62, size: 50 }] }, Date.now());
  await engine.tick();
  assert.equal(sells().length, 0, notes());
  assert.equal(oms.allOrders(500).filter((o) => o.ticker === market.ticker && o.reduceOnly && o.timeInForce === 'immediate_or_cancel').length, 1, notes());
});

/** An exit curve in rest mode whose cross the test arms: it records what the engine asked and sells on a turned spot. */
class StubCross extends StubRest {
  armed = false;
  asked: CrossCheck[] = [];
  override cross(_ticker: string, e: CrossCheck): { sell: boolean; why?: string } {
    this.asked.push(e);
    return this.armed && e.spot === 'against' ? { sell: true, why: `exit curve: cross ${e.sidePrice} (+0.010 a contract net, curve 0.5 under projection 0.6, spot against)` } : { sell: false };
  }
}

test('exit curve rest mode, the cross: a turned spot sells at the bid at once and pulls the resting sell', async () => {
  const curveExit = new StubCross({ mode: 'rest', minNetProfit: 0.015 }, { minTrades: 20, t: 1, maxLossUsd: 25, window: 200 });
  curveExit.target = 0.7;
  const { engine, recon, market, md, oms, audit } = await setup({ curveExit, env: { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false' } });
  engine.balance = (await recon.run('startup'))!.balance;
  oms.onFill({ tradeId: 'x1', orderId: '', ticker: market.ticker, side: 'bid', count: 10, price: 0.4, isTaker: false, fee: 0, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.45, size: 50 }], asks: [{ price: 0.6, size: 50 }] }, Date.now());
  const notes = () => engine.status.get(market.ticker)!.notes.join(' | ');
  const resting = () => oms.liveOrders().filter((o) => o.ticker === market.ticker && o.purpose === 'exit' && o.timeInForce === 'good_till_canceled' && !o.cancelRequested);
  await engine.tick();
  assert.deepEqual(resting().map((o) => o.price), [0.7], notes());
  // What the engine asked: the side's bid, the whole position (the bid holds 50), the take-profit floor (4c on a 40c
  // contract) and the time to close.
  const first = curveExit.asked.at(-1)!;
  assert.deepEqual([first.sidePrice, first.count], [0.45, 10]);
  assert.ok(Math.abs(first.floor - 0.04) < 1e-9, String(first.floor));
  assert.ok(first.tauSec > 500 && first.tauSec <= 600, String(first.tauSec));
  // BTC drops 0.015% in the last five seconds (a quarter of a 5 s standard deviation is the noise floor; a fast move
  // would be twice one): against a YES position on an up/down contract.
  const idx = md.index.get('BTC')!;
  const pts = (idx as unknown as { points: Array<{ ts: number; value: number }> }).points;
  const cut = Date.now() + 200 - 5000;
  const ref = [...pts].reverse().find((p) => p.ts <= cut)!.value;
  idx.add(ref * Math.exp(-1.5e-4), Date.now());
  curveExit.armed = true;
  await engine.tick();
  assert.equal(curveExit.asked.at(-1)!.spot, 'against', notes());
  const iocs = oms.allOrders(500).filter((o) => o.ticker === market.ticker && o.reduceOnly && o.timeInForce === 'immediate_or_cancel');
  assert.deepEqual(iocs.map((o) => [o.side, o.price, o.count]), [['ask', 0.45, 10]], notes());
  assert.equal(resting().length, 0, 'the resting sell is pulled');
  const why = audit.tail(50, 'decision').flatMap((d) => ((d.data as { place?: Array<{ why: string }> }).place ?? []).map((p) => p.why));
  assert.ok(why.some((w) => /^exit curve: cross 0\.45 /.test(w)), why.join(' | '));
});

/** An exit curve in cross mode (paper's default) whose cross the test arms; its swing-top estimate is the real one. */
class StubCrossOnly extends SinuousExitGate {
  armed = false;
  override cross(ticker: string, e: CrossCheck, now: number): { sell: boolean; why?: string } {
    return this.armed ? { sell: true, why: `exit curve: cross ${e.sidePrice} (+0.010 a contract net, curve 0.5 under projection 0.6, spot against)` } : super.cross(ticker, e, now);
  }
}

test('exit curve cross mode (the default, paper and live): no sell rests at the swing top; the cross still sells at the bid', async () => {
  const curveExit = new StubCrossOnly({ mode: 'cross', minNetProfit: 0.015 }, { minTrades: 20, t: 1, maxLossUsd: 25, window: 200 });
  const { engine, recon, market, md, oms } = await setup({ curveExit, env: { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false' } });
  engine.balance = (await recon.run('startup'))!.balance;
  // Long 10 YES bought at 0.40 on the (paper) exchange, so its sale can fill.
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.38, size: 50 }], asks: [{ price: 0.4, size: 50 }] }, Date.now());
  await oms.submit({ ticker: market.ticker, asset: 'BTC', windowCloseTs: market.closeTime, side: 'bid', price: 0.4, count: 10, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'entry', fairValue: 0.5, modelId: 'm', decisionId: 'e' });
  assert.equal(oms.positions.get(market.ticker)?.yes, 10);
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.45, size: 50 }], asks: [{ price: 0.6, size: 50 }] }, Date.now());
  const notes = () => engine.status.get(market.ticker)!.notes.join(' | ');
  const resting = () => oms.liveOrders().filter((o) => o.ticker === market.ticker && o.purpose === 'exit' && o.timeInForce === 'good_till_canceled' && !o.cancelRequested);
  for (let i = 0; i < 3; i++) await engine.tick();
  assert.deepEqual(resting(), [], notes());
  curveExit.armed = true;
  await engine.tick();
  const iocs = oms.allOrders(500).filter((o) => o.ticker === market.ticker && o.reduceOnly && o.timeInForce === 'immediate_or_cancel');
  assert.deepEqual(iocs.map((o) => [o.side, o.price, o.count]), [['ask', 0.45, 10]], notes());
  // Scored on its fill (10 sold at 0.45), paper and live alike: settled YES, holding would have paid $1 a contract.
  assert.equal(curveExit.status().crossesPending, 1);
  oms.settle(market.ticker, 'yes');
  const s = curveExit.status();
  assert.equal(s.scored, 1);
  assert.ok(s.netUsd < -5 && s.netUsd > -6, `(0.45 - fee - 1) x 10: ${s.netUsd}`);
});

test('exit curve on the live line: a break of the coin\'s line sells the held position at the bid', async () => {
  const curveExit = new SinuousExitGate({ mode: 'cross', minNetProfit: 0.015, crossSource: 'line' }, { minTrades: 20, t: 1, maxLossUsd: 25, window: 200 });
  class BrokenLine extends LiveLines {
    override read(_asset: string, orient: 1 | -1): LiveLineReading {
      return { price: 100, projected: 100.1, band: { lower: 100.04, upper: 100.16, k: 2, sec: 300 }, underSd: orient > 0 ? 2.6 : -2.6, slope: -0.4, breakSec: orient > 0 ? 2 : 0, broke: orient > 0 };
    }
  }
  const liveLines = new BrokenLine();
  const { engine, recon, market, md, oms, audit } = await setup({ curveExit, liveLines, env: { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false' } });
  engine.balance = (await recon.run('startup'))!.balance;
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.38, size: 50 }], asks: [{ price: 0.4, size: 50 }] }, Date.now());
  await oms.submit({ ticker: market.ticker, asset: 'BTC', windowCloseTs: market.closeTime, side: 'bid', price: 0.4, count: 10, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'entry', fairValue: 0.5, modelId: 'm', decisionId: 'e' });
  // Far enough in profit to clear the take-profit floor (+10% of the 0.417 cost): the bid is 0.52.
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.52, size: 50 }], asks: [{ price: 0.54, size: 50 }] }, Date.now());
  await engine.tick();
  const st = engine.status.get(market.ticker)!;
  assert.equal(st.line?.broke, true, JSON.stringify(st.line));
  const exits = oms.allOrders(500).filter((o) => o.ticker === market.ticker && o.reduceOnly && o.timeInForce === 'immediate_or_cancel');
  assert.ok(exits.length >= 1, st.notes.join(' | '));
  assert.deepEqual([exits[0].side, exits[0].price], ['ask', 0.52]);
  const why = audit.tail(50, 'decision').flatMap((d) => ((d.data as { place?: Array<{ why: string }> }).place ?? []).map((p) => p.why));
  assert.ok(why.some((w) => /^exit curve: cross 0\.52 \(\+0\.\d+ a contract net, live line outside its wiggle band for 2 s \(2\.6 sd, band \+-2 sd of 300 s since the open\)\)$/.test(w)), why.join(' | '));
  assert.equal(curveExit.status().crossesPending, 1, 'scored on its fill');
});

test('exit curve on the live line, the sell signal off (the default): a break is noted, nothing is sold on it', async () => {
  const curveExit = new SinuousExitGate({ mode: 'cross', minNetProfit: 0.015, crossSource: 'line', cross: false }, { minTrades: 20, t: 1, maxLossUsd: 25, window: 200 });
  class BrokenLine extends LiveLines {
    override read(): LiveLineReading { return { price: 100, projected: 100.1, band: { lower: 100.04, upper: 100.16, k: 2, sec: 300 }, underSd: 2.6, slope: -0.4, breakSec: 2, broke: true }; }
  }
  const { engine, recon, market, md, oms } = await setup({ curveExit, liveLines: new BrokenLine(), env: { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false' } });
  engine.balance = (await recon.run('startup'))!.balance;
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.38, size: 50 }], asks: [{ price: 0.4, size: 50 }] }, Date.now());
  await oms.submit({ ticker: market.ticker, asset: 'BTC', windowCloseTs: market.closeTime, side: 'bid', price: 0.4, count: 10, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'entry', fairValue: 0.5, modelId: 'm', decisionId: 'e' });
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.52, size: 50 }], asks: [{ price: 0.54, size: 50 }] }, Date.now());
  await engine.tick();
  const notes = engine.status.get(market.ticker)!.notes.join(' | ');
  assert.match(notes, /live line: outside its wiggle band for 2 s \(2\.6 sd; the cross would sell; it is off, SINUOUS_CROSS\)/);
  assert.equal(curveExit.status().crossesPending, 0, 'nothing sold on it');
});

test('exit curve: a cross whose order fills nothing is not scored', async () => {
  const curveExit = new StubCrossOnly({ mode: 'cross', minNetProfit: 0.015 }, { minTrades: 20, t: 1, maxLossUsd: 25, window: 200 });
  const { engine, recon, market, md, oms } = await setup({ curveExit, env: { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false' } });
  engine.balance = (await recon.run('startup'))!.balance;
  oms.onFill({ tradeId: 'k2', orderId: '', ticker: market.ticker, side: 'bid', count: 10, price: 0.4, isTaker: false, fee: 0, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.45, size: 50 }], asks: [{ price: 0.6, size: 50 }] }, Date.now());
  // The paper exchange holds no position here (the fill above went to the bot's books only): it refuses the
  // reduce-only sale, as Kalshi would, so the cross order fills nothing.
  curveExit.armed = true;
  await engine.tick();
  const sent = oms.allOrders(500).filter((o) => o.ticker === market.ticker && o.reduceOnly);
  assert.equal(sent.length, 1, 'the cross order was sent');
  assert.equal(sent[0].filledCount, 0, sent[0].state);
  assert.equal(curveExit.status().crossesPending, 0);
});

test('exit curve: an exit at a loss goes out at once', async () => {
  const curveExit = new SinuousExitGate({ mode: 'gate', minNetProfit: 0.015 }, { minTrades: 20, t: 1, maxLossUsd: 25, window: 200 });
  const { engine, recon, market, md, oms } = await setup({ curveExit });
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  // Long 10 NO bought at 0.40; the market bids NO 0.20, still above the model's value: cutting the loser never waits.
  oms.onFill({ tradeId: 'e2', orderId: '', ticker: market.ticker, side: 'ask', count: 10, price: 0.6, isTaker: true, fee: 0.17, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.78, size: 50 }], asks: [{ price: 0.8, size: 50 }] }, Date.now());
  await engine.tick();
  assert.equal(oms.allOrders(500).filter((o) => o.ticker === market.ticker && o.reduceOnly).length, 1, engine.status.get(market.ticker)!.notes.join(' | '));
  assert.deepEqual(curveExit.status().holding, []);
});

test('take-profit: a winner runs, then is sold once it gives back a third of its best gain', async () => {
  const { engine, recon, market, md, oms, audit } = await setup();
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  // Long 10 YES bought at 0.40 as a maker: the floor is 10% of the 0.40 cost, 4c. At a 0.56 bid it is +16c less the
  // 1.8c taker fee, +14.2c net: armed, and a winner at its best runs. Back at 0.50 (+8.2c, more than a third of the best
  // given back) it is sold.
  oms.onFill({ tradeId: 'p1', orderId: '', ticker: market.ticker, side: 'bid', count: 10, price: 0.4, isTaker: false, fee: 0, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
  const exits = () => oms.allOrders(500).filter((o) => o.ticker === market.ticker && o.reduceOnly);
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.56, size: 50 }], asks: [{ price: 0.58, size: 50 }] }, Date.now());
  await engine.tick();
  const st = engine.status.get(market.ticker)!;
  assert.equal(exits().length, 0, st.notes.join(' | '));
  assert.ok(st.notes.some((n) => /^take-profit armed: \+0\.142 now, best \+0\.142/.test(n)), st.notes.join(' | '));
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.5, size: 50 }], asks: [{ price: 0.52, size: 50 }] }, Date.now());
  await engine.tick();
  assert.equal(exits().length, 1, engine.status.get(market.ticker)!.notes.join(' | '));
  assert.deepEqual([exits()[0].side, exits()[0].price, exits()[0].count], ['ask', 0.5, 10]);
  const why = audit.tail(50, 'decision').flatMap((d) => ((d.data as { place?: Array<{ why: string }> }).place ?? []).map((p) => p.why));
  assert.ok(why.some((w) => /^take-profit: \+0\.082 a contract net of fees \(best \+0\.142, floor \+0\.040\)/.test(w)), why.join(' | '));
});

test('take-profit bench: a take-profit sale is scored on its fill against holding to settlement; benched, the take-profit sells nothing', async () => {
  const rule = { minTrades: 30, t: 2, maxLossUsd: 25, window: 200 };
  const run = async (bench: TakeProfitBench) => {
    const g = await setup({ takeProfitBench: bench, env: { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false' } });
    g.engine.balance = (await g.recon.run('startup'))!.balance;
    // Long 10 YES bought at 0.40 on the (paper) exchange, so the take-profit's sale can fill.
    g.md.book(g.market.ticker).applySnapshot({ bids: [{ price: 0.38, size: 50 }], asks: [{ price: 0.4, size: 50 }] }, Date.now());
    await g.oms.submit({ ticker: g.market.ticker, asset: 'BTC', windowCloseTs: g.market.closeTime, side: 'bid', price: 0.4, count: 10, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'entry', fairValue: 0.5, modelId: 'm', decisionId: 'e' });
    assert.equal(g.oms.positions.get(g.market.ticker)?.yes, 10);
    // Best 0.56, then back to 0.50: more than a third of the best gain given back.
    g.md.book(g.market.ticker).applySnapshot({ bids: [{ price: 0.56, size: 50 }], asks: [{ price: 0.58, size: 50 }] }, Date.now());
    await g.engine.tick();
    g.md.book(g.market.ticker).applySnapshot({ bids: [{ price: 0.5, size: 50 }], asks: [{ price: 0.52, size: 50 }] }, Date.now());
    await g.engine.tick();
    return { ...g, notes: () => g.engine.status.get(g.market.ticker)!.notes.join(' | '), exits: () => g.oms.allOrders(500).filter((o) => o.ticker === g.market.ticker && o.reduceOnly) };
  };
  const bench = new TakeProfitBench(true, rule);
  const g = await run(bench);
  assert.deepEqual(g.exits().map((o) => [o.side, o.price, o.count, o.filledCount]), [['ask', 0.5, 10, 10]], g.notes());
  assert.equal(bench.status().pending, 1);
  // Settled YES: holding would have paid $1 a contract; the sale got 0.50 less its taker fee.
  g.oms.settle(g.market.ticker, 'yes');
  const s = bench.status();
  assert.deepEqual([s.scored, s.pending], [1, 0]);
  assert.ok(s.netUsd < -5 && s.netUsd > -5.3, `(0.50 - fee - 1) x 10: ${s.netUsd}`);
  assert.equal(g.engine.takeProfitBenchStatus()?.scored, 1);
  // A bench already called (the take-profit cost $26 against holding): the same pull-back sells nothing.
  const benched = new TakeProfitBench(true, rule);
  for (let i = 0; i < 13; i++) { benched.filled(`M${i}`, 1, 0.81, 10, 0.01, i); benched.settled(`M${i}`, 'yes', i + 1); }
  const h = await run(benched);
  assert.equal(h.exits().length, 0, h.notes());
  assert.match(h.notes(), /take-profit benched: \+0\.\d+ now, best \+0\.\d+, not sold \(take-profit sales cost \$26\.00/);
  // The dashboard's reset lifts it.
  assert.equal(h.engine.resetTakeProfitBench(), true);
  assert.equal(benched.benched, undefined);
});

test('take-profit: the last tick above the floor goes out at once, the exit curve never holds it', async () => {
  const curveExit = new SinuousExitGate({ mode: 'gate', minNetProfit: 0.015 }, { minTrades: 20, t: 1, maxLossUsd: 25, window: 200 });
  const { engine, recon, market, md, oms } = await setup({ curveExit });
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  // Long 10 YES at 0.40 (floor 4c). Best 0.48 (+6.2c), then 0.46 (+4.2c): within a tick of the floor, sold to lock it in.
  oms.onFill({ tradeId: 'p3', orderId: '', ticker: market.ticker, side: 'bid', count: 10, price: 0.4, isTaker: false, fee: 0, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
  const exits = () => oms.allOrders(500).filter((o) => o.ticker === market.ticker && o.reduceOnly);
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.48, size: 50 }], asks: [{ price: 0.5, size: 50 }] }, Date.now());
  await engine.tick();
  assert.equal(exits().length, 0, engine.status.get(market.ticker)!.notes.join(' | '));
  await new Promise((res) => setTimeout(res, 20));
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.46, size: 50 }], asks: [{ price: 0.48, size: 50 }] }, Date.now());
  await engine.tick();
  assert.equal(exits().length, 1, engine.status.get(market.ticker)!.notes.join(' | '));
  assert.equal(exits()[0].price, 0.46);
  assert.deepEqual(curveExit.status().holding, []);
});

test('an exit never trades against the bot\'s own resting quote (self-trade prevention would cancel it): the quote is pulled first', async () => {
  // PROFIT_GIVE_BACK=0: the take-profit sells as soon as the floor is reached, so the exit is due on the tick under test.
  const { engine, recon, market, md, oms, audit } = await setup({ env: { PROFIT_GIVE_BACK: '0' } });
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  oms.onFill({ tradeId: 'p2', orderId: '', ticker: market.ticker, side: 'bid', count: 10, price: 0.5, isTaker: false, fee: 0, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.45, size: 50 }], asks: [{ price: 0.65, size: 50 }] }, Date.now());
  await engine.tick(); // the new position is evaluated: no exit at a loss of 5c
  // One of our quotes rests at 0.63, above where the exit will sell.
  const own = await oms.submit({ ticker: market.ticker, asset: 'BTC', windowCloseTs: market.closeTime, side: 'bid', price: 0.63, count: 2, timeInForce: 'good_till_canceled', postOnly: true, reduceOnly: false, purpose: 'quote', fairValue: 0.55, modelId: 'm', decisionId: 'd' });
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.62, size: 50 }], asks: [{ price: 0.65, size: 50 }] }, Date.now());
  await engine.tick();
  const exit = oms.allOrders(500).find((o) => o.ticker === market.ticker && o.reduceOnly);
  assert.ok(exit, engine.status.get(market.ticker)!.notes.join(' | '));
  assert.deepEqual([exit.side, exit.price], ['ask', 0.62]);
  const cancels = audit.tail(200, 'order_cancel_req').map((c) => c.data as { clientOrderId: string; reason: string });
  assert.ok(cancels.some((c) => c.clientOrderId === own.clientOrderId), `our 0.63 bid was pulled: ${JSON.stringify(cancels)}`);
  assert.ok(!['ACKED', 'PARTIALLY_FILLED'].includes(oms.get(own.clientOrderId)!.state), oms.get(own.clientOrderId)!.state);
  const seqOf = (kind: 'order_cancel_req' | 'order_new', pred: (d: Record<string, unknown>) => boolean) => audit.tail(400, kind).find((x) => pred(x.data as Record<string, unknown>))!.seq;
  assert.ok(seqOf('order_cancel_req', (d) => d.clientOrderId === own.clientOrderId) < seqOf('order_new', (d) => d.clientOrderId === exit.clientOrderId), 'pulled before the exit was sent');
});

test('vault and pocket are excluded from the tradable bankroll; wins feed the vault', async () => {
  // Live always keeps the vault out of the bankroll; paper does with VAULT_IN_PAPER (the same rule).
  const vault = new Vault({ enabled: true, quotaUsd: 100, winShare: 0.5, pocketShare: 0.1, quotaReset: 'session', dailyGoalUsd: 100 });
  const { engine, recon, oms } = await setup({ vault, monitor: new BalanceMonitor(), env: { VAULT_IN_PAPER: 'true' } });
  const r = await recon.run('startup');
  engine.onBalance(r!.balance!);
  assert.equal(engine.bankroll(), 200);
  // A settled win of $10 (fee-inclusive): $5 vaulted.
  oms.onFill({ tradeId: 'w', orderId: '', ticker: 'W', side: 'bid', count: 20, price: 0.5, isTaker: false, fee: 0, ts: Date.now() }, { closeTs: Date.now() - 1, asset: 'BTC' });
  oms.settle('W', 'yes');
  assert.equal(vault.vaultTotal, 5);
  assert.equal(engine.bankroll(), 195);
});

test('vault: a settled loss is won back before a later win is vaulted; the total starts at the account\'s net P&L', async () => {
  const vault = new Vault({ enabled: true, quotaUsd: 100, winShare: 0.5, pocketShare: 0.1, quotaReset: 'session', dailyGoalUsd: 100 });
  const { engine, recon, oms } = await setup({ vault, monitor: new BalanceMonitor(), env: { VAULT_IN_PAPER: 'true' } });
  const r = await recon.run('startup');
  engine.onBalance(r!.balance!);
  assert.equal(vault.status().realized?.total, 0, 'started at the first balance read (no break-even to be under)');
  // A $4 loss, then a $10 win: $6 of it is new profit, $3 vaulted.
  oms.onFill({ tradeId: 'l', orderId: '', ticker: 'L', side: 'bid', count: 8, price: 0.5, isTaker: false, fee: 0, ts: Date.now() }, { closeTs: Date.now() - 1, asset: 'BTC' });
  oms.settle('L', 'no');
  assert.equal(vault.status().realized?.total, -4);
  oms.onFill({ tradeId: 'w', orderId: '', ticker: 'W', side: 'bid', count: 20, price: 0.5, isTaker: false, fee: 0, ts: Date.now() }, { closeTs: Date.now() - 1, asset: 'BTC' });
  oms.settle('W', 'yes');
  assert.equal(vault.vaultTotal, 3);
  // A refilled paper pool (the training supervisor's noteCash) starts the total over.
  engine.noteCashFlow(50);
  assert.deepEqual([vault.status().realized?.total, vault.status().realized?.high], [0, 0]);
});

test('paper: the vault reserve leaves the bankroll, as in live (since Oct 28)', async () => {
  // The vault keeps half of every new realized high (before Oct 23's rule, half of every win and none of the losses:
  // by Oct 23 it held $343 of the $360 paper pool).
  const vault = new Vault({ enabled: true, quotaUsd: 100, winShare: 0.5, pocketShare: 0.1, quotaReset: 'session', dailyGoalUsd: 100 });
  const { engine, recon, oms } = await setup({ vault, monitor: new BalanceMonitor() });
  const r = await recon.run('startup');
  engine.onBalance(r!.balance!);
  oms.onFill({ tradeId: 'w', orderId: '', ticker: 'W', side: 'bid', count: 20, price: 0.5, isTaker: false, fee: 0, ts: Date.now() }, { closeTs: Date.now() - 1, asset: 'BTC' });
  oms.settle('W', 'yes');
  assert.equal(vault.vaultTotal, 5, 'still vaulted on the books');
  assert.equal(engine.bankroll(), 195, 'and not traded, in paper as in live');
});

test('paper size: by default the $10-$20 order band, as live; PAPER_ORDER_FRAC buys a share of the bankroll; PAPER_ORDER_FRAC=0 with PAPER_ORDER_USD a fixed amount; band off, paper sizes as live', async () => {
  const quote = (g: Awaited<ReturnType<typeof setup>>) => g.oms.liveOrders().find((o) => o.ticker === g.market.ticker && o.purpose === 'quote' && !o.cancelRequested && o.side === 'bid');
  const env = { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false' };
  const run = async (extra: Record<string, string>) => {
    const g = await setup({ env: { ...env, ...extra } });
    g.engine.balance = (await g.recon.run('startup'))!.balance;
    await g.engine.tick();
    return { g, q: quote(g)!, notes: g.engine.status.get(g.market.ticker)?.notes ?? [] };
  };
  const near = (q: { count: number; price: number }, usd: number) => { const v = q.count * q.price; return v > usd - q.price - 0.05 && v <= usd + 1e-9; };
  // PAPER_ORDER_FRAC=0.1: 10% of the $200 account, $20 an order.
  const frac = await run({ PAPER_ORDER_FRAC: '0.1' });
  assert.ok(frac.q, JSON.stringify(frac.notes));
  assert.ok(near(frac.q, 20), `${frac.q.count} at ${frac.q.price}`);
  assert.match(frac.notes.join(' | '), /paper size: \$20\.00 an order \(10% of the bankroll, PAPER_ORDER_FRAC\)/);
  assert.equal(frac.g.engine.guardStatus().paperOrderFrac, 0.1);
  // The share follows the bankroll: 2.5% of $200 is $5; the account shrinking to $100 halves the order the same way.
  const half = await run({ PAPER_ORDER_FRAC: '0.025' });
  assert.ok(near(half.q, 5), `${half.q.count} at ${half.q.price}`);
  assert.equal(frac.g.engine.paperOrderUsd(100), 10);
  // PAPER_ORDER_FRAC=0: the fixed PAPER_ORDER_USD, whatever the account.
  const fixed = await run({ PAPER_ORDER_FRAC: '0', PAPER_ORDER_USD: '8' });
  assert.ok(near(fixed.q, 8), `${fixed.q.count} at ${fixed.q.price}`);
  assert.match(fixed.notes.join(' | '), /paper size: \$8 an order \(PAPER_ORDER_USD\)/);
  assert.equal(fixed.g.engine.paperOrderUsd(100), 8);
  // Both off (the default since Oct 28: paper sizes like live) and the band off: the tier and break-even sizing of a $200
  // account, a few dollars at most.
  const sized = await run({ ORDER_USD_MIN: '0' });
  assert.equal(sized.g.engine.paperOrderUsd(100), 0);
  assert.equal(sized.g.engine.guardStatus().orderBandUsd, null);
  assert.ok(sized.q.count * sized.q.price < 5, `${sized.q.count} at ${sized.q.price}`);
  assert.ok(sized.q.count < frac.q.count);
  // The default since Oct 30 (Steven): the order band, $10-$20 an order (paper and live alike).
  const band = await run({});
  assert.ok(band.q, JSON.stringify(band.notes));
  assert.ok(band.q.count * band.q.price > 9.4 && band.q.count * band.q.price <= 20, `${band.q.count} at ${band.q.price}`);
  assert.match(band.notes.join(' | '), /order band: \$10-\$20 an order \(ORDER_USD_MIN\/MAX\)/);
  assert.deepEqual(band.g.engine.guardStatus().orderBandUsd, { min: 10, max: 20 });
});

test('accuracy gate (ACCURACY_GATE=true): no new quote in a time-to-close bucket where the market mid called results better; off by default, it keeps scoring and blocks nothing', async () => {
  const quote = (g: Awaited<ReturnType<typeof setup>>) => g.oms.liveOrders().find((o) => o.ticker === g.market.ticker && o.purpose === 'quote' && !o.cancelRequested);
  const env = { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false' };
  // 50 settled 15-minute markets per bucket around 10 minutes out, where the mid leaned the right way and the bot sat at 0.5.
  const scorecard = (cfg: { enabled: boolean; window: number; minMarkets: number }) => {
    const gate = new AccuracyGate(cfg);
    for (let i = 0; i < 50; i++) for (const tau of [700, 520]) {
      const t = `KXETH15M-M${i}-${tau}`;
      gate.observe(t, tau, 0.5, i % 2 ? 0.65 : 0.35);
      gate.settle(t, i % 2 ? 'yes' : 'no');
    }
    return gate;
  };
  const g = await setup({ env: { ...env, ACCURACY_GATE: 'true' }, accuracyGate: scorecard({ enabled: true, window: 150, minMarkets: 40 }) });
  g.engine.balance = (await g.recon.run('startup'))!.balance;
  await g.engine.tick();
  assert.equal(quote(g), undefined);
  const why = Object.keys(g.engine.entryDiagnosis().reasons);
  assert.ok(why.some((r) => /accuracy gate: the market has called results better (450-600|600-840) s before the close/.test(r)), why.join(' | '));
  assert.equal(g.engine.guardStatus().accuracyGate?.enforced, true);
  // The default (ACCURACY_GATE unset, off since Nov 11, paper and live alike): the same losing scorecard, built from the
  // default settings as bot/main.ts builds it, blocks nothing; the quote goes out and the market is still scored.
  const offGate = scorecard(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(40) }).strategy.accuracyGate);
  const off = await setup({ env, accuracyGate: offGate });
  off.engine.balance = (await off.recon.run('startup'))!.balance;
  await off.engine.tick();
  assert.ok(quote(off), JSON.stringify(off.engine.status.get(off.market.ticker)?.notes));
  assert.equal(off.engine.status.get(off.market.ticker)?.accuracyBlock, undefined);
  const ag = off.engine.guardStatus().accuracyGate;
  assert.equal(ag?.enforced, false);
  assert.equal(ag?.enabled, false);
  assert.equal(ag?.groups.updown15m.buckets.filter((b) => !b.open).length, 2, 'the scorecard still reports the buckets the market called better');
  assert.equal(offGate.status().pending, 1, 'the evaluation fed the scorecard with the gate off');
  offGate.settle(off.market.ticker, 'yes');
  assert.equal(offGate.status().groups.updown15m.buckets.reduce((a, b) => a + b.n, 0), 101, 'and its result is scored');
});

test('a manually recorded withdrawal is not counted again by the detector', async () => {
  const vault = new Vault({ enabled: true, quotaUsd: 100, winShare: 0.5, pocketShare: 0.1, quotaReset: 'session', dailyGoalUsd: 100 });
  const monitor = new BalanceMonitor();
  const { engine } = await setup({ vault, monitor });
  engine.onBalance(200);
  engine.recordWithdrawal(30, 'test');
  // Kalshi now reports the lower balance on consecutive checks: nothing new is booked.
  engine.onBalance(170);
  engine.onBalance(170);
  assert.equal(vault.status().withdrawnTotal, 30);
});

test('model-health halt is off by default in paper and live: a model worse than the market is reported, entries stay open', async () => {
  // A model confidently wrong for 60 settlement windows: significantly worse than the market, so the score says halt.
  const worse = () => {
    const h = new ModelHealth({ minWindows: 50 });
    for (let w = 0; w < 60; w++) { const y = w % 2 ? 'yes' : 'no'; h.record(`A${w}`, y === 'yes' ? 0.3 : 0.7, 0.5, w); h.onResult(`A${w}`, y); }
    return h;
  };
  const key = path.join(tmpDir(), 'k.pem');
  fs.writeFileSync(key, 'x', { mode: 0o600 });
  const live = { TRADING_MODE: 'live', KALSHI_KEY_ID: 'id', KALSHI_PRIVATE_KEY_PATH: key, KALSHI_ENV: 'prod', LIVE_TRADING_ACKNOWLEDGED: 'I_ACCEPT_REAL_MONEY_RISK' };
  const halted = (e: Engine) => e.entryGuards().some((r) => /model log loss significantly worse/.test(r));
  for (const env of [{}, live]) {
    const { engine, cfg } = await setup({ env, modelHealth: worse() });
    assert.equal(cfg.strategy.modelHealthHalt, false, `${cfg.mode}: MODEL_HEALTH_HALT defaults to false`);
    assert.equal(engine.guardStatus().modelHealth?.halt, true, `${cfg.mode}: the score is still computed and reported`);
    assert.equal(halted(engine), false, `${cfg.mode}: no entry halt from it`);
    // MODEL_HEALTH_HALT=true still turns the old halt on (no kill-switch override here).
    const on = await setup({ env: { ...env, MODEL_HEALTH_HALT: 'true' }, modelHealth: worse() });
    assert.equal(halted(on.engine), true, `${cfg.mode}: MODEL_HEALTH_HALT=true halts new entries`);
  }
});

test('no new risk below the $10 hard floor; $20 trades on the aggressive tier', async () => {
  const { engine, recon, paper } = await setup();
  await recon.run('startup');
  engine.balance = 8;
  assert.ok(engine.haltReasons().some((r) => r.includes('below the $10 minimum')));
  await engine.tick();
  assert.equal((await paper.getOpenOrders()).length, 0);
  engine.balance = 18; // e.g. $20 after one $2 loss: still trading
  assert.ok(!engine.haltReasons().some((r) => r.includes('minimum')));
  engine.balance = 20;
  const g = engine.guardStatus();
  assert.equal(g.tier.name, 'aggressive');
  assert.equal(g.tier.orderRiskUsd, 2);
  assert.equal(g.tier.dailyLossLimitUsd, 4);
});

test('conviction: every evaluation records the TA overlay; the altcoin risk-on rule boosts a long entry 2.5x', async () => {
  // NON_ALTCOINS empty: the test market (BTC) counts as an altcoin.
  const base = await setup({ env: { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false' } });
  let r = await base.recon.run('startup');
  base.engine.balance = r!.balance;
  await base.engine.tick();
  const st0 = base.engine.status.get(base.market.ticker)!;
  assert.ok(st0.conviction, 'conviction recorded');
  assert.equal(st0.taShift, 0, 'no TA network loaded: fair value untouched');
  assert.equal(st0.conviction!.alt.active, false);
  assert.match(st0.conviction!.alt.why, /not an altcoin|USDT\.D|RSI/);

  // PAPER_ORDER_FRAC=0 and PAPER_ORDER_USD=0: a paper order size is never boosted, and this test is about the boost.
  const alt = await setup({ trend: 0.000002, env: { NON_ALTCOINS: 'NONE', PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false', ADVERSARIAL_BOOST: 'false', PAPER_ORDER_USD: '0', PAPER_ORDER_FRAC: '0' } });
  const now = Date.now();
  // USDT.D falling over the last 20 minutes (with some noise for its volatility); the index rising (RSI > 50).
  let u = 5.0;
  for (let s = 1800; s >= 0; s -= 10) { u *= 1 - 0.00002 + 0.00001 * Math.sin(s); alt.md.usdtd.add(u, now - s * 1000); }
  r = await alt.recon.run('startup');
  alt.engine.balance = r!.balance;
  await alt.engine.tick();
  const st = alt.engine.status.get(alt.market.ticker)!;
  assert.equal(st.conviction!.alt.active, true, JSON.stringify(st.conviction));
  assert.ok(st.conviction!.priority >= 10, 'altcoin risk-on is selected first');
  assert.ok(st.notes.some((n) => /altcoin risk-on: .* x2\.5/.test(n)), JSON.stringify({ fv: st.fairValue, q: st.q, bid: st.bestBid, ask: st.bestAsk, blocked: st.blocked, ew: st.entryWindow, notes: st.notes }));
  assert.ok(st.notes.some((n) => /conviction x2\.50 on the YES entry: [\d.]+ -> [\d.]+ contracts/.test(n)), st.notes.join(' | '));
});

test('conviction: the adversary vetoes the altcoin boost on an entry it breaks', async () => {
  // Ask-heavy book: the tape attack breaks a YES entry, so it keeps its normal size.
  const alt = await setup({ trend: 0.000002, askSize: 5000, env: { NON_ALTCOINS: 'NONE', PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false' } });
  const now = Date.now();
  let u = 5.0;
  for (let s = 1800; s >= 0; s -= 10) { u *= 1 - 0.00002 + 0.00001 * Math.sin(s); alt.md.usdtd.add(u, now - s * 1000); }
  const r = await alt.recon.run('startup');
  alt.engine.balance = r!.balance;
  await alt.engine.tick();
  const st = alt.engine.status.get(alt.market.ticker)!;
  assert.equal(st.conviction!.alt.active, true, JSON.stringify(st.conviction));
  assert.ok(st.notes.some((n) => /adversary vetoed the x2\.5 boost \(tape/.test(n)), st.notes.join(' | '));
  assert.ok(!st.notes.some((n) => /conviction x2\.50 on the YES/.test(n)), st.notes.join(' | '));
});

test('idle evaluation: a market the bot is not in is re-evaluated every EVAL_IDLE_SEC, not every tick', async () => {
  const { engine, recon, market, oms, paper } = await setup({ env: { EVAL_IDLE_SEC: '30', STRATEGY_STYLE: 'taker', STRATEGY_MIN_EDGE: '0.5', PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false' } });
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  await engine.tick();
  const first = engine.status.get(market.ticker)!.updatedTs;
  assert.equal((await paper.getOpenOrders()).length, 0, 'no order resting');
  assert.equal(oms.positions.position(market.ticker), 0);
  await new Promise((res) => setTimeout(res, 20));
  await engine.tick();
  assert.equal(engine.status.get(market.ticker)!.updatedTs, first, 'skipped: idle and evaluated moments ago');
});

test('contracts are priced on Kalshi data alone by default: a stale Kalshi index blocks, Coinbase does not stand in', async () => {
  const { engine, recon, market, md } = await setup();
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  const now = Date.now();
  (md.index.get('BTC') as any).points.forEach((p: { ts: number }) => { p.ts -= 120_000; });
  const spot = md.spot.get('BTC')!;
  for (let sec = 600; sec >= 0; sec--) spot.add(60010 + Math.sin(sec), now - sec * 1000);
  await engine.tick();
  assert.equal(engine.status.get(market.ticker)!.blocked, 'index stale');
});

test('optimal f on the Kalshi pool: settled trades in trades.jsonl cap the stake per order (paper floors it)', async () => {
  const { cfg, engine } = await setup();
  const now = Date.now();
  // 150 settled markets at 50c with a 30 % win rate: no edge, so the history supports no stake.
  const lines = Array.from({ length: 150 }, (_, i) => JSON.stringify({ ts: now - (150 - i) * 3_600_000, ticker: `KXBTC15M-T${i}`, book: 'crypto', q: 0.6, cost: 0.5, count: 2, won: i % 10 < 3 }));
  fs.writeFileSync(path.join(cfg.dataDir, 'trades.jsonl'), lines.join('\n') + '\n');
  const f = engine.kalshiOptimalF('crypto', now);
  assert.equal(f.rep?.n, 150);
  assert.equal(f.rep?.cap, 0);
  assert.ok(f.cap > 0 && Math.abs(f.cap - cfg.optimalF.paperFloor * engine.tier().orderFrac) < 1e-12, 'paper: floored at a quarter of the per-order fraction');
  assert.equal(engine.kalshiOptimalF('tennis', now).rep?.n, 0, 'books are separate');
  assert.equal(engine.kalshiOptimalF('tennis', now).cap, Infinity, 'too few trades: no cap');
});

test('Kalshi data arriving late: quotes are pulled and nothing is sent until it catches up (paper and live)', async () => {
  const { engine, recon, paper, md, market } = await setup();
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  await engine.tick();
  assert.ok((await paper.getOpenOrders()).length >= 1, 'quoting while the feed is current');
  let lag: number | undefined = 45_000;
  (md as any).kalshiFeedLagMs = () => lag;
  await engine.tick();
  assert.equal((await paper.getOpenOrders()).length, 0, 'resting quotes pulled');
  assert.match(engine.status.get(market.ticker)!.blocked!, /Kalshi data 45\.0 s behind/);
  assert.ok(engine.haltReasons().some((x) => /behind real time/.test(x)));
  lag = 40; // caught up
  // Time passes: an idle market is re-evaluated every EVAL_IDLE_SEC, and entries wait for the next cadence trigger.
  engine.status.get(market.ticker)!.updatedTs -= 10_000;
  (engine as any).cadence.forget(market.ticker);
  await engine.tick();
  assert.ok((await paper.getOpenOrders()).length >= 1, 'quoting again');
  assert.ok(!engine.haltReasons().some((x) => /behind real time/.test(x)));
});

test('paper: a balance move nobody made (a paper book started fresh) re-anchors the books without drawing the vault', async () => {
  const vault = new Vault({ enabled: true, quotaUsd: 100, winShare: 0.5, pocketShare: 0.1, quotaReset: 'session', dailyGoalUsd: 100 });
  const monitor = new BalanceMonitor();
  const { engine } = await setup({ vault, monitor });
  engine.onBalance(210.48);
  engine.onBalance(100);
  engine.onBalance(100);
  assert.equal(vault.status().withdrawnTotal, 0, 'not booked as a withdrawal');
  assert.equal(monitor.state.expected, 100, 'expected balance re-anchored');
});

test('component trials: a trial that passed moves the price in paper and live alike; every contract in its entry window is recorded', async () => {
  class Stub extends ComponentTrials {
    readonly onNames = new Set<TrialName>();
    readonly records: Array<[TrialName, string, number, number]> = [];
    override applied(name: TrialName): boolean { return this.onNames.has(name); }
    override record(name: TrialName, ticker: string, _asset: string, _close: number, pWith: number, pWithout: number): void { this.records.push([name, ticker, pWith, pWithout]); }
  }
  // The TA network's 1 h and 4 h calls, neither validated: outside their trial they do not move the price at all.
  const view: TaNetView = { up1: 0.62, up4: 0.6 };
  const run = async (env: Record<string, string>, on: TrialName[]) => {
    const trials = new Stub(DEFAULT_TRIALS);
    for (const n of on) trials.onNames.add(n);
    const s = await setup({ trials, env: { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false', ...env } });
    (s.engine as unknown as { taView: () => TaNetView }).taView = () => view;
    s.engine.balance = (await s.recon.run('startup'))!.balance;
    await s.engine.tick();
    return { st: s.engine.status.get(s.market.ticker)!, trials };
  };
  const off = await run({}, []);
  assert.ok(off.st.trials && off.st.trials.ta! > 0 && off.st.taShift === 0, `full ${off.st.trials?.ta}, today ${off.st.taShift}`);
  assert.deepEqual(off.st.trials!.applied, []);
  const rec = off.trials.records.filter(([n]) => n === 'ta');
  assert.ok(rec.length >= 1, 'the contract in its entry window is recorded');
  assert.ok(Math.abs(rec[0][3] - off.st.pModel!) < 1e-12 && Math.abs(rec[0][2] - (off.st.pModel! + off.st.trials!.ta!)) < 1e-4, 'scored with the full tilt against the meta-model\'s price');
  const on = await run({}, ['ta']);
  assert.ok(Math.abs(on.st.taShift! - on.st.trials!.ta!) < 1e-4 && on.st.taShift! > 0, `paper prices with the full-weight tilt once its trial passed: ${on.st.taShift}`);
  assert.deepEqual(on.st.trials!.applied, ['ta']);
  // Live: the same passing trial moves live's price the same way (the owner, Oct 28: paper behaves as live).
  const key = path.join(tmpDir(), 'k.pem');
  fs.writeFileSync(key, 'x', { mode: 0o600 });
  const live = await run({ TRADING_MODE: 'live', KALSHI_KEY_ID: 'id', KALSHI_PRIVATE_KEY_PATH: key, KALSHI_ENV: 'prod', LIVE_TRADING_ACKNOWLEDGED: 'I_ACCEPT_REAL_MONEY_RISK' }, ['ta']);
  assert.ok(Math.abs(live.st.taShift! - on.st.taShift!) < 1e-6, `live ${live.st.taShift} vs paper with the trial ${on.st.taShift}`);
  assert.deepEqual(live.st.trials!.applied, ['ta']);
});

test('component trials: the trained model comes out of the price when its trial says so, in paper and live alike', async () => {
  class Stub extends ComponentTrials {
    readonly onNames = new Set<TrialName>();
    readonly records: Array<[TrialName, number, number]> = [];
    override applied(name: TrialName): boolean { return this.onNames.has(name); }
    override record(name: TrialName, _t: string, _a: string, _c: number, pWith: number, pWithout: number): void { this.records.push([name, pWith, pWithout]); }
  }
  // A trained model that leans YES: logit(p) = logit(fair value) + 0.4.
  const n = FEATURE_NAMES.length;
  const model = MetaModel.fromJson(JSON.stringify({ version: 'lean', kind: 'mlp', features: [...FEATURE_NAMES], referenceSigma: 5e-5, normalization: { mean: new Array(n).fill(0), std: new Array(n).fill(1) },
    layers: [{ weights: [[1, ...new Array(n - 1).fill(0)]], bias: [0.4], activation: 'linear' }] }));
  const run = async (env: Record<string, string>, on: TrialName[]) => {
    const trials = new Stub(DEFAULT_TRIALS);
    for (const x of on) trials.onNames.add(x);
    const s = await setup({ trials, model, env: { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false', ...env } });
    s.engine.balance = (await s.recon.run('startup'))!.balance;
    await s.engine.tick();
    return { st: s.engine.status.get(s.market.ticker)!, trials };
  };
  const lean = (st: { pModel?: number; fairValue?: number }) => Math.log(st.pModel! / (1 - st.pModel!)) - Math.log(st.fairValue! / (1 - st.fairValue!));
  const kept = await run({}, ['mlp']);
  assert.ok(Math.abs(lean(kept.st) - 0.4) < 1e-6, `the trained model prices paper: ${kept.st.pModel} vs ${kept.st.fairValue}`);
  const mlp = kept.trials.records.find(([x]) => x === 'mlp')!;
  assert.ok(Math.abs(mlp[1] - kept.st.pModel!) < 1e-12 && Math.abs(mlp[2] - kept.st.fairValue!) < 1e-12, 'scored against the math fair value');
  const out = await run({}, []);
  assert.ok(Math.abs(out.st.pModel! - out.st.fairValue!) < 1e-12, 'out of paper\'s price: the fair value alone');
  const key = path.join(tmpDir(), 'k.pem');
  fs.writeFileSync(key, 'x', { mode: 0o600 });
  const live = await run({ TRADING_MODE: 'live', KALSHI_KEY_ID: 'id', KALSHI_PRIVATE_KEY_PATH: key, KALSHI_ENV: 'prod', LIVE_TRADING_ACKNOWLEDGED: 'I_ACCEPT_REAL_MONEY_RISK' }, []);
  assert.ok(Math.abs(live.st.pModel! - live.st.fairValue!) < 1e-12, 'out of live\'s price too');
});

test('the dashboard\'s snipe badge: the hour\'s target and the held position\'s profit after fees at the bid; pacer off, no target', async () => {
  for (const pacer of ['true', 'false']) {
    const { engine, recon, market, md, oms } = await setup({ env: { PACER: pacer } });
    const r = await recon.run('startup');
    engine.balance = r!.balance;
    md.book(market.ticker).applySnapshot({ bids: [{ price: 0.56, size: 50 }], asks: [{ price: 0.58, size: 50 }] }, Date.now());
    await engine.tick();
    assert.equal(engine.status.get(market.ticker)!.snipe, undefined, 'flat: no badge');
    // Long 10 YES bought at 0.40 as a maker: at a 0.56 bid it is +$1.60 less the $0.18 taker fee, +$1.42. A fresh pacer's
    // slice is the full $4.50, so it is not sniped yet.
    oms.onFill({ tradeId: 'p1', orderId: '', ticker: market.ticker, side: 'bid', count: 10, price: 0.4, isTaker: false, fee: 0, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
    await engine.tick();
    const s = engine.status.get(market.ticker)!.snipe!;
    assert.deepEqual({ ...s, nowUsd: Math.round(s.nowUsd! * 100) / 100 }, { atUsd: pacer === 'true' ? 4.5 : undefined, nowUsd: 1.42, rides: false, closed: false });
    // Half sold at 0.56 (fee 0.09): the badge measures the 5 still held at their own 0.40, +$0.80 less the $0.09 taker fee.
    // Net cash would put them at 0.22 and show the sold half's profit again (+$1.62).
    oms.onFill({ tradeId: 'p2', orderId: '', ticker: market.ticker, side: 'ask', count: 5, price: 0.56, isTaker: true, fee: 0.09, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
    await engine.tick();
    assert.equal(Math.round(engine.status.get(market.ticker)!.snipe!.nowUsd! * 100) / 100, 0.71);
  }
});

test('RISK_SIZE_CAPS off (default): the engine still sends the tennis budget and the armed waterfall total to the gateway', async () => {
  const g = await setup();
  assert.equal(g.cfg.risk.sizeCaps, false);
  g.engine.balance = (await g.recon.run('startup'))!.balance;
  const seen: Array<{ intent: OrderIntent; ctx: RiskContext }> = [];
  const real = new RiskGateway(g.cfg.risk);
  (g.engine as any).d.risk = { check: (intent: OrderIntent, ctx: RiskContext) => { seen.push({ intent, ctx }); return real.check(intent, ctx); } };
  const m = g.md.markets.get(g.market.ticker)!;
  const plan = { side: 'bid' as const, price: 0.5, count: 10, timeInForce: 'good_till_canceled' as const, postOnly: true, reduceOnly: false, purpose: 'entry' as const, edge: 0.1, why: 'test entry' };
  const over = (ctx: RiskContext, window: number, total: number) => real.check(seen[seen.length - 1].intent, { ...ctx, windowRisk: window, totalRisk: total });
  // Tennis: its own per-order / per-match / total budget holds with the crypto caps off.
  await (g.engine as any).placeChecked(m, plan, 0.6, 'd-tennis', { event: 'EVT' });
  const t = seen[seen.length - 1].ctx;
  assert.equal(t.limitOverrides?.sizeCaps, true, 'tennis overrides keep the caps on');
  assert.match(over(t, 1e6, 1e6).reasons.join(';'), /window risk.*total risk/);
  // Waterfall armed: Kalshi binaries held to its total share of the bank; order and window caps stay off.
  setMacro({ policy: () => ({ level: 'armed', tennisBlocked: true, kalshiBlocked: false, kalshiMaxFrac: 0.125, perpMult: () => 1, why: 'armed (test)' }) } as unknown as MacroService);
  try {
    await (g.engine as any).placeChecked(m, plan, 0.6, 'd-wf');
  } finally { setMacro(undefined); }
  const w = seen[seen.length - 1].ctx;
  assert.equal(w.limitOverrides?.sizeCaps, true);
  assert.equal(w.limitOverrides?.maxTotalRiskFrac, 0.125);
  assert.deepEqual(over(w, 1e6, 1e6).reasons.filter((r) => /risk \$/.test(r)).map((r) => r.split(' $')[0]), ['total risk']);
  // No waterfall, crypto: no size caps at all.
  await (g.engine as any).placeChecked(m, plan, 0.6, 'd-plain');
  const c = seen[seen.length - 1].ctx;
  assert.equal(over(c, 1e6, 1e6).reasons.filter((r) => /risk \$/.test(r)).length, 0);
});

test('probation score-only (default): the unvalidated fill model stays active while the Kalshi book would bench', async () => {
  const { engine } = await setup();
  engine.setFillModel({ validated: false } as FillModel);
  const p = new Probation(DEFAULT_PROBATION);
  try {
    setProbation(p);
    p.record('kalshi', -30);
    assert.equal(p.status().kalshi.wouldBench, true);
    assert.equal(engine.fillModelActive, true);
    const rows = engine.moduleLedger();
    assert.equal(rows.find((r) => r.module === 'fill model')?.state, 'on');
    const row = rows.find((r) => r.module === 'probation: kalshi')!;
    assert.equal(row.state, 'on');
    assert.deepEqual(row.flags, ['would bench (score-only, nothing turned off): iterate it']);
    // The owner's gate on: the same book is benched and the fill model goes back behind its gate.
    const gated = new Probation({ ...DEFAULT_PROBATION, bench: true });
    setProbation(gated);
    gated.record('kalshi', -30);
    assert.equal(engine.fillModelActive, false);
    assert.equal(engine.moduleLedger().find((r) => r.module === 'probation: kalshi')?.state, 'benched');
  } finally { setProbation(undefined); }
});

test('equity counts what resting orders hold at a read: only the opening part, and a cancel keeps it until the next read', async () => {
  const { engine, paper, oms, market } = await setup();
  const base = { ticker: market.ticker, asset: 'BTC', windowCloseTs: market.closeTime, timeInForce: 'good_till_canceled' as const, postOnly: true, reduceOnly: false, fairValue: 0.5, modelId: 'm', decisionId: 'e' };
  // Long 50 YES at 60c (lifts the 60c ask), then a resting ask that only closes it and a resting bid that opens.
  await oms.submit({ ...base, side: 'bid', price: 0.6, count: 50, timeInForce: 'immediate_or_cancel', postOnly: false, purpose: 'entry' });
  await oms.submit({ ...base, side: 'ask', price: 0.8, count: 50, purpose: 'quote' });
  const bid = await oms.submit({ ...base, side: 'bid', price: 0.4, count: 10, purpose: 'entry' });
  const cash = paper.cash();
  engine.onBalance(await paper.getBalance());
  const eq = cash + oms.positions.open().reduce((x, m) => x + PositionBook.maxLoss(m), 0);
  assert.ok(Math.abs(engine.equity()! - eq) < 1e-6, `equity ${engine.equity()} vs ${eq}: the closing ask holds nothing, the bid's $4 is added back`);
  // Canceled after the read: the stale balance has not got the $4 back, so equity holds still.
  await oms.cancel(bid.clientOrderId, 'test');
  assert.ok(Math.abs(engine.equity()! - eq) < 1e-6, `after the cancel ${engine.equity()}`);
  engine.onBalance(await paper.getBalance());
  assert.ok(Math.abs(engine.equity()! - eq) < 1e-6, `next read ${engine.equity()}`);
});

// ---- The exit-only lane (E06) ----------------------------------------------------------------------------------------
// With only 60 s of index history the volatility (120 one-second returns) is still warming up, as for about 2 minutes after
// every restart: the market cannot be priced, but a held position still gets the exits already armed that need no model.

test('exit-only lane: 60 s after a restart (volatility warming up), the armed take-profit sells a held YES bought at 0.40; the final minute still holds it', async () => {
  const { engine, recon, market, md, oms, audit } = await setup({ historySec: 60 });
  engine.balance = (await recon.run('startup'))!.balance;
  assert.equal(md.index.get('BTC')!.vol(), undefined, 'volatility still warming up');
  // Long 10 YES bought at 0.40 as a maker (take-profit floor 4c). At a 0.56 bid: +14.2c net, armed; a winner at its best runs.
  oms.onFill({ tradeId: 'l1', orderId: '', ticker: market.ticker, side: 'bid', count: 10, price: 0.4, isTaker: false, fee: 0, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
  const exits = () => oms.allOrders(500).filter((o) => o.ticker === market.ticker && o.reduceOnly);
  const notes = () => engine.status.get(market.ticker)!.notes.join(' | ');
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.56, size: 50 }], asks: [{ price: 0.58, size: 50 }] }, Date.now());
  await engine.tick();
  assert.equal(engine.status.get(market.ticker)!.blocked, 'volatility warming up');
  assert.equal(exits().length, 0, notes());
  assert.match(notes(), /^exit-only lane \(volatility warming up\): only exits already armed/);
  assert.match(notes(), /take-profit armed: \+0\.142 now, best \+0\.142/);
  // Back to 0.50 (more than a third of the best gain given back) inside the final minute: held to settlement, as always.
  const m = md.markets.get(market.ticker)!;
  const close = m.closeTime;
  m.closeTime = Date.now() + 30_000;
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.5, size: 50 }], asks: [{ price: 0.52, size: 50 }] }, Date.now());
  await engine.tick();
  assert.equal(exits().length, 0, notes());
  assert.match(notes(), /final minute: riding to settlement/);
  // Outside it the take-profit sells at the bid, the gateway judging the exit against the book's mid.
  m.closeTime = close;
  await engine.tick();
  assert.equal(exits().length, 1, notes());
  const x = exits()[0];
  assert.deepEqual([x.side, x.price, x.count, x.purpose, x.timeInForce], ['ask', 0.5, 10, 'exit', 'immediate_or_cancel']);
  assert.ok(Math.abs(x.fairValue - 0.51) < 1e-9, `fair value ${x.fairValue}`);
  const d = audit.tail(50, 'decision').map((r) => r.data as { lane?: string; blocked?: string; place?: Array<{ why: string }> }).find((r) => r.lane === 'exit_only');
  assert.equal(d?.blocked, 'volatility warming up');
  assert.match(d!.place![0].why, /^take-profit: \+0\.082 a contract net of fees \(best \+0\.142, floor \+0\.040\)/);
});

test('exit-only lane: the exit curve in gate mode holds a profit take-profit as in a full evaluation; its protective last tick goes out', async () => {
  const curveExit = new SinuousExitGate({ mode: 'gate', minNetProfit: 0.015 }, { minTrades: 20, t: 1, maxLossUsd: 25, window: 200 });
  const { engine, recon, market, md, oms } = await setup({ historySec: 60, curveExit });
  engine.balance = (await recon.run('startup'))!.balance;
  oms.onFill({ tradeId: 'l5', orderId: '', ticker: market.ticker, side: 'bid', count: 10, price: 0.4, isTaker: false, fee: 0, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
  const exits = () => oms.allOrders(500).filter((o) => o.ticker === market.ticker && o.reduceOnly);
  const notes = () => engine.status.get(market.ticker)!.notes.join(' | ');
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.56, size: 50 }], asks: [{ price: 0.58, size: 50 }] }, Date.now());
  await engine.tick();
  // 0.50: the take-profit sells +0.082 a contract, a profit exit: the gate holds it for the curve's signal.
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.5, size: 50 }], asks: [{ price: 0.52, size: 50 }] }, Date.now());
  await engine.tick();
  assert.equal(engine.status.get(market.ticker)!.blocked, 'volatility warming up');
  assert.equal(exits().length, 0, notes());
  assert.match(notes(), /curve: holding the profit exit at 0\.5 /);
  // 0.46: +0.042, the last tick above the 0.040 floor: protective, never held.
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.46, size: 50 }], asks: [{ price: 0.48, size: 50 }] }, Date.now());
  await engine.tick();
  assert.equal(exits().length, 1, notes());
  assert.deepEqual([exits()[0].side, exits()[0].price, exits()[0].count], ['ask', 0.46, 10]);
});

test('exit-only lane: no entry goes out through it; a flat market waits for its price, a held one gets reduce-only exits only', async () => {
  const { engine, recon, market, md, oms, cfg } = await setup({ historySec: 60 });
  engine.balance = (await recon.run('startup'))!.balance;
  const orders = () => oms.allOrders(500).filter((o) => o.ticker === market.ticker);
  await engine.tick();
  assert.equal(engine.status.get(market.ticker)!.blocked, 'volatility warming up');
  assert.equal(orders().length, 0, 'flat: nothing');
  // Held YES on the setup's 0.45 / 0.60 book (a full evaluation quotes here): no quote, no entry, no training trade.
  oms.onFill({ tradeId: 'l2', orderId: '', ticker: market.ticker, side: 'bid', count: 10, price: 0.4, isTaker: false, fee: 0, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
  await engine.tick();
  assert.equal(orders().length, 0, engine.status.get(market.ticker)!.notes.join(' | '));
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.56, size: 50 }], asks: [{ price: 0.58, size: 50 }] }, Date.now());
  await engine.tick();
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.5, size: 50 }], asks: [{ price: 0.52, size: 50 }] }, Date.now());
  await engine.tick();
  assert.equal(orders().length, 1);
  assert.ok(orders().every((o) => o.reduceOnly && o.purpose === 'exit'), JSON.stringify(orders().map((o) => [o.side, o.purpose, o.reduceOnly])));
  // That is end to end, and the lane's view has no order room either. The lane's plan itself (exitOnlyPlan, the engine's and
  // the replay's) on a view WITH order room: no entry or quote and no model exit, where a full decision has both (the model
  // values the YES at 0.20, so it would sell at the 0.45 bid and quote the NO).
  const view: MarketView = {
    ticker: market.ticker, pYes: 0.2, bestBid: { price: 0.45, size: 50 }, bestAsk: { price: 0.47, size: 50 }, position: 10, bankroll: 200,
    maxOrderRiskUsd: 20, maxContracts: 100, minSidePrice: cfg.risk.minSidePrice, tauSec: 600, noEntryBeforeCloseSec: cfg.risk.noEntryBeforeCloseSec, fastMove: false,
    tickSize: 0.01, fees: { takerMultiplier: 1, makerMultiplier: 0 }, nowSec: 1000, closeSec: 1600, entrySidePrice: 0.4, entryFeePerContract: 0,
  };
  const full = decide(view, cfg.strategy, {});
  assert.ok(full.place.some((p) => p.reduceOnly && p.why.startsWith('bid 0.45 - fee > q')), JSON.stringify(full.place));
  assert.ok(full.place.some((p) => !p.reduceOnly), JSON.stringify(full.place));
  assert.deepEqual(decide(view, cfg.strategy, { armedOnly: true }).place, []);
  assert.deepEqual(exitOnlyPlan(view, cfg.strategy, { why: 'test', exits: true }).plan.place, []);
  // With the take-profit armed (best bid 0.56 since the fill, 0.50 now) the lane sells, and only that.
  const armed = exitOnlyPlan({ ...view, bestBid: { price: 0.5, size: 50 }, bestAsk: { price: 0.52, size: 50 }, profitPeakSidePrice: 0.56 }, cfg.strategy, { why: 'test', exits: true }).plan.place;
  assert.deepEqual(armed.map((p) => [p.side, p.price, p.count, p.purpose, p.reduceOnly, p.timeInForce]), [['ask', 0.5, 10, 'exit', true, 'immediate_or_cancel']]);
  assert.match(armed[0].why, /^take-profit: \+0\.082/);
});

test('exit-only lane: the index goes stale mid-session; the quota floor armed earlier still sells the held position', async () => {
  // EXIT_POLICY=hold: no take-profit or model exit, the quota floor alone.
  const { engine, recon, market, md, oms } = await setup({ exitPolicy: 'hold' });
  engine.balance = (await recon.run('startup'))!.balance;
  oms.onFill({ tradeId: 'l3', orderId: '', ticker: market.ticker, side: 'bid', count: 10, price: 0.4, isTaker: false, fee: 0, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
  const exits = () => oms.allOrders(500).filter((o) => o.ticker === market.ticker && o.reduceOnly);
  const notes = () => engine.status.get(market.ticker)!.notes.join(' | ');
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.56, size: 50 }], asks: [{ price: 0.58, size: 50 }] }, Date.now());
  await engine.tick();
  assert.equal(engine.status.get(market.ticker)!.blocked, undefined, 'a full evaluation first');
  // A floor armed by an earlier evaluation: $2.00 on the 10 held (8 ticks of cushion: sold below $1.20 of profit).
  assert.equal((engine as unknown as { quotaFloors: { arm(t: string, p: number, usd: number): boolean } }).quotaFloors.arm(market.ticker, 10, 2), true);
  (md.index.get('BTC') as unknown as { points: Array<{ ts: number }> }).points.forEach((p) => { p.ts -= 60_000; });
  await engine.tick();
  assert.equal(engine.status.get(market.ticker)!.blocked, 'index stale');
  assert.equal(exits().length, 0, `+$1.42 at 0.56 holds: ${notes()}`);
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.5, size: 50 }], asks: [{ price: 0.52, size: 50 }] }, Date.now());
  await engine.tick();
  assert.equal(exits().length, 1, notes());
  assert.deepEqual([exits()[0].side, exits()[0].price, exits()[0].count], ['ask', 0.5, 10]);
});

test('exit-only lane: an armed hunt stop sells below its stop; the take-profit stays off while hunting; at the default lock sale the take-profit sells a dip through the stop', async () => {
  for (const c of ['off', 'defaults', 'hold'] as const) {
    const { engine, recon, market, md, oms, cfg, audit } = await setup({ historySec: 60 });
    engine.balance = (await recon.run('startup'))!.balance;
    oms.onFill({ tradeId: 'l4', orderId: '', ticker: market.ticker, side: 'bid', count: 10, price: 0.4, isTaker: false, fee: 0, ts: Date.now() }, { closeTs: market.closeTime, asset: 'BTC' });
    const exits = () => oms.allOrders(500).filter((o) => o.ticker === market.ticker && o.reduceOnly);
    const notes = () => engine.status.get(market.ticker)!.notes.join(' | ');
    // A hunt that activated in an earlier evaluation: entry value 0.45 + the 2c margin, its stop locked at 0.47. 'defaults': the
    // configured lock sale (HUNT_LOCK_SALE=fair_value, judged at the first dip, HUNT_LOCK_SALE_ELSE=exit); 'hold': the same
    // judgement with HUNT_LOCK_SALE_ELSE=hold.
    const S = cfg.strategy;
    const params = c === 'off' ? { lockSale: 'off' as const }
      : c === 'defaults' ? { lockSale: S.huntLockSale, lockSaleElse: S.huntLockSaleElse, lockSaleAt: S.huntLockSaleAt }
      : { lockSale: 'fair_value' as const, lockSaleElse: 'hold' as const };
    if (c === 'defaults') assert.deepEqual([S.huntLockSale, S.huntLockSaleElse, S.huntLockSaleAt], ['fair_value', 'exit', 'trigger']);
    const book = md.book(market.ticker);
    book.applySnapshot({ bids: [{ price: 0.5, size: 50 }], asks: [{ price: 0.52, size: 50 }] }, Date.now());
    const hunt = new ConfluenceRatchetExit({ targetMargin: 0.02, minConfluence: 2, ...params });
    const on = hunt.update({ position: 10, qSide: 0.45, sideBid: 0.5, confluence: 3, book, now: Date.now(), tick: 0.01, fees: md.feesFor(market.ticker) });
    assert.deepEqual([on.mode, on.stop], ['hunt', 0.47]);
    (engine as unknown as { hunts: Map<string, ConfluenceRatchetExit> }).hunts.set(market.ticker, hunt);
    await engine.tick();
    assert.equal(engine.status.get(market.ticker)!.blocked, 'volatility warming up');
    assert.equal(exits().length, 0, notes());
    assert.match(notes(), /hunting: stop 0\.47/);
    assert.doesNotMatch(notes(), /take-profit armed/);
    // 0.46: under the stop, within the 1-tick slippage.
    book.applySnapshot({ bids: [{ price: 0.46, size: 50 }], asks: [{ price: 0.48, size: 50 }] }, Date.now());
    await engine.tick();
    if (c === 'off') {
      assert.equal(exits().length, 1, notes());
      assert.deepEqual([exits()[0].side, exits()[0].price, exits()[0].count], ['ask', 0.46, 10]);
    } else if (c === 'defaults') {
      // The first dip is judged against the fair value: a hit sells at the bid, a miss hands the position to the normal exit,
      // whose take-profit sells here (+0.042 now against a best of +0.082, its last tick above the 0.040 floor). Either way that
      // sale stands, so the lane makes it; the judgement itself waits for the data and the hunt is left as it was.
      assert.equal(exits().length, 1, notes());
      assert.deepEqual([exits()[0].side, exits()[0].price, exits()[0].count], ['ask', 0.46, 10]);
      assert.match(notes(), /the lock sale's judgement waits for the fair value/);
      const d = audit.tail(50, 'decision').map((r) => r.data as { lane?: string; place?: Array<{ why: string }> }).find((r) => r.lane === 'exit_only');
      assert.match(d!.place![0].why, /^take-profit: \+0\.042 a contract net of fees \(best \+0\.082, floor \+0\.040\)/);
      assert.equal(hunt.active, true);
    } else {
      // A miss would hold to settlement: nothing sells until the judgement can be made.
      assert.equal(exits().length, 0, notes());
      assert.equal(hunt.active, true);
    }
  }
});

// ---- The hold exit and its re-entry rule (HOLD_EXIT, Steven Nov 11) ----------------------------------------------------
// The engine's clock steps a second an evaluation; the book and the index are refreshed at each step, as the feeds would.

function liveEnv(): Record<string, string> {
  const key = path.join(tmpDir(), 'k.pem');
  fs.writeFileSync(key, 'x', { mode: 0o600 });
  return { TRADING_MODE: 'live', KALSHI_KEY_ID: 'id', KALSHI_PRIVATE_KEY_PATH: key, KALSHI_ENV: 'prod', LIVE_TRADING_ACKNOWLEDGED: 'I_ACCEPT_REAL_MONEY_RISK' };
}

/** EXIT_POLICY=hold (no take-profit or model exit in the way): 10 YES bought at the 0.40 ask (a $0.17 taker fee). */
async function heldOnClock(env: Record<string, string>, closeIn: number, openAgo?: number, historySec?: number, extra: { curveExit?: SinuousExitGate; liveLines?: LiveLines } = {}) {
  const clock = { t: Date.now() };
  const s = await setup({ exitPolicy: 'hold', closeIn, now: () => clock.t, env, openAgo, historySec, ...extra });
  s.engine.balance = (await s.recon.run('startup'))!.balance;
  const t = s.market.ticker;
  const idx = s.md.index.get('BTC')!;
  /** One evaluation `o.ms` (1000) after the last, on a book bidding `bid` (`o.size` of it, 50 by default). */
  const step = async (bid: number, ask = Math.round((bid + 0.02) * 100) / 100, o: { size?: number; ms?: number } = {}) => {
    clock.t += o.ms ?? 1000;
    s.md.book(t).applySnapshot({ bids: [{ price: bid, size: o.size ?? 50 }], asks: [{ price: ask, size: 50 }] }, clock.t);
    idx.add(idx.latest()!.value, clock.t);
    await s.engine.tick();
  };
  s.md.book(t).applySnapshot({ bids: [{ price: 0.38, size: 50 }], asks: [{ price: 0.4, size: 50 }] }, clock.t);
  await s.oms.submit({ ticker: t, asset: 'BTC', windowCloseTs: s.market.closeTime, side: 'bid', price: 0.4, count: 10, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'entry', fairValue: 0.5, modelId: 'm', decisionId: 'e' });
  assert.equal(s.oms.positions.position(t), 10);
  const st = () => s.engine.status.get(t)!;
  const exits = () => s.oms.allOrders(500).filter((o) => o.ticker === t && o.reduceOnly);
  const pacer = (event: string) => s.audit.tail(500, 'pacer').map((r) => r.data as Record<string, unknown>).filter((d) => d.event === event);
  const placed = () => s.audit.tail(500, 'decision').flatMap((r) => (r.data as { place?: Array<{ why: string }> }).place ?? []).map((p) => p.why);
  return { ...s, t, clock, step, st, exits, pacer, placed };
}

test('hold exit: sold at the bid once +$1.50 after fees for 10 s in all (a dip pauses the count) and +$1.00 for the last 3 s in a row; audited; paper and live alike', async () => {
  // The profit ratchet off: the dip to 0.50 (+$0.65) is under the stop it arms at 0.59 and would sell (its own tests below).
  for (const env of [{ RATCHET: 'false' }, { ...liveEnv(), RATCHET: 'false' }]) {
    // 200 s to the close of a 500 s window: outside the entry window, so only exits trade.
    const { engine, oms, cfg, t, step, st, exits, pacer, placed } = await heldOnClock(env, 200_000);
    const notes = () => `${cfg.mode}: ${st().notes.join(' | ')}`;
    // At a 0.59 bid the 10 are up $1.90 less the $0.17 entry and $0.17 exit fees, +$1.56; at 0.50, +$0.65. A fresh pacer
    // needs $4.50: no snipe.
    for (let i = 0; i < 6; i++) await step(0.59);
    assert.deepEqual(st().hold, { fire: false, cumSec: 5, runSec: 5 }, notes());
    assert.match(notes(), /hold exit: 5\.0 of 10 s in all at \+\$1\.50 or more, 5\.0 of 3 s in a row at \+\$1\.00 or more/);
    await step(0.5);
    await step(0.5);
    assert.deepEqual(st().hold, { fire: false, cumSec: 5, runSec: 0 }, 'the dip keeps the count and ends the run');
    for (let i = 0; i < 5; i++) await step(0.59);
    assert.deepEqual(st().hold, { fire: false, cumSec: 9, runSec: 4 });
    assert.equal(exits().length, 0, notes());
    await step(0.59);
    assert.equal(exits().length, 1, notes());
    const x = exits()[0];
    assert.deepEqual([x.side, x.price, x.count, x.purpose, x.timeInForce], ['ask', 0.59, 10, 'exit', 'immediate_or_cancel']);
    assert.equal(oms.positions.position(t), 0, `${cfg.mode}: filled at the bid`);
    const why = 'hold exit: +$1.56 net on 10 at bid 0.59, 10.0 s in all at +$1.50 or more, the last 5.0 s in a row at +$1.00 or more';
    assert.ok(placed().includes(why), placed().join(' | '));
    assert.deepEqual(pacer('hold_exit'), [{ event: 'hold_exit', ticker: t, cumSec: 10, runSec: 5, netUsd: 1.56, count: 10, price: 0.59, why }]);
    assert.equal(pacer('snipe').length, 0);
    // The sale starts the re-entry rule on this contract (the next test shows it closing and opening the entry window).
    const rule = (engine as unknown as { holdExits: { reentryBlock(t: string, tauSec: number, windowSec: number): string | undefined } }).holdExits;
    assert.match(rule.reentryBlock(t, 185, 500) ?? '', /^re-entry after a hold exit or quota snipe: 185 s of the 500 s window left/);
    assert.equal(rule.reentryBlock(t, 251, 500), undefined);
    // Flat, and a same-side position reopened before the next evaluation (a resting YES bid filling just after the sale, 10 at
    // 0.61): never sampled flat, it starts from nothing and is not sold at its first +$1.09.
    await oms.submit({ ticker: t, asset: 'BTC', windowCloseTs: Date.now() + 200_000, side: 'bid', price: 0.61, count: 10, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'entry', fairValue: 0.5, modelId: 'm', decisionId: 'again' });
    assert.equal(oms.positions.position(t), 10);
    await step(0.75);
    assert.deepEqual(st().hold, { fire: false, cumSec: 0, runSec: 0 }, notes());
    assert.equal(exits().length, 1, notes());
  }
});

test('quota snipe unchanged beside the hold exit: sold at once at its target; then the contract is entered again only while more than half its window is left (paper and live)', async () => {
  for (const env of [{}, liveEnv()]) {
    for (const closeIn of [200_000, 600_000]) {
      // PACER_HOURLY_USD=1: the hour needs $1.00, so +$1.56 is sniped at the first evaluation. Entries open until 60 s before the
      // close. The window runs open to close: 500 s with 200 s left (not more than half), 900 s with 600 s left (more than half).
      const { cfg, oms, t, step, st, exits, pacer, engine, audit, market, clock } = await heldOnClock({ ...env, PACER_HOURLY_USD: '1', ENTRY_WINDOW_15M: '840,60' }, closeIn);
      const what = `${cfg.mode}, ${closeIn / 1000} s left`;
      // A maker ask resting from an earlier evaluation, sized with the position (it carries the unwind).
      const ask = await oms.submit({ ticker: t, asset: 'BTC', windowCloseTs: market.closeTime, side: 'ask', price: 0.7, count: 15, timeInForce: 'good_till_canceled', postOnly: true, reduceOnly: false, purpose: 'quote', fairValue: 0.5, modelId: 'm', decisionId: 'q' });
      const before = new Set(oms.allOrders(500).map((o) => o.clientOrderId));
      await step(0.59);
      assert.equal(exits().length, 1, what);
      // The sale's own evaluation sends nothing else (no quote sized with the position, no entry at half the window or less) and
      // pulls the resting ask, which would sell the position a second time once it fills.
      const added = oms.allOrders(500).filter((o) => o.ticker === t && !before.has(o.clientOrderId));
      assert.deepEqual(added.map((o) => [o.purpose, o.reduceOnly]), [['exit', true]], `${what}: ${JSON.stringify(added.map((o) => [o.side, o.price, o.count, o.purpose]))}`);
      assert.ok(!oms.liveOrders().some((o) => o.clientOrderId === ask.clientOrderId && !o.cancelRequested), `${what}: the resting ask is pulled`);
      const sent = audit.tail(50, 'decision').map((r) => r.data as { place?: Array<{ purpose: string }> }).filter((d) => d.place?.length).at(-1);
      assert.deepEqual(sent?.place?.map((x) => x.purpose), ['exit'], what);
      assert.match(String(pacer('snipe')[0]?.why), /^quota snipe: \+\$1\.56 net on 10 at bid 0\.59 covers the \$1\.00 the hour needs/, what);
      assert.deepEqual(st().hold, { fire: false, cumSec: 0, runSec: 0 }, 'no hold time needed');
      assert.equal(oms.positions.position(t), 0, what);
      // The setup's 0.45 / 0.60 book, where the strategy quotes.
      await step(0.45, 0.6);
      const resting = oms.liveOrders().filter((o) => o.ticker === t && !o.reduceOnly && !o.cancelRequested);
      if (closeIn === 200_000) {
        assert.match(st().reentryBlock ?? '', /^re-entry after a hold exit or quota snipe: 19\d s of the 500 s window left, not more than 50%/, what);
        assert.equal(st().entryWindow, false);
        assert.equal(resting.length, 0, `${what}: ${JSON.stringify(resting.map((o) => [o.side, o.price, o.purpose, o.state]))}`);
        assert.ok(Object.keys(engine.entryDiagnosis().reasons).some((k) => k.startsWith('re-entry after a hold exit or quota snipe')), what);
        // Nothing was left to cancel, so the next decision record is the half-minute one; it names the block.
        clock.t += 30_000;
        await step(0.45, 0.6);
        const blocks = audit.tail(50, 'decision').map((r) => (r.data as { entryBlock?: string }).entryBlock).filter(Boolean);
        assert.match(blocks.at(-1) ?? '', /^re-entry after a hold exit or quota snipe/, what);
      } else {
        assert.equal(st().reentryBlock, undefined, what);
        assert.equal(st().entryWindow, true, what);
        assert.ok(resting.some((o) => o.purpose === 'quote'), `${what}: the normal entry signal quotes again`);
      }
    }
  }
});

test('re-entry rule: a quota snipe the risk gateway refuses sold nothing and marks nothing; the one that fills does (paper and live)', async () => {
  for (const env of [{}, liveEnv()]) {
    const { engine, oms, t, step, st, exits, pacer, cfg } = await heldOnClock({ ...env, PACER_HOURLY_USD: '1', ENTRY_WINDOW_15M: '840,60' }, 200_000);
    const risk = (engine as unknown as { d: { risk: RiskGateway } }).d.risk;
    const check = risk.check.bind(risk);
    risk.check = (i: OrderIntent, c: RiskContext) => (i.reduceOnly ? { ok: false, reasons: ['order rate at limit'] } : check(i, c));
    await step(0.59);
    await step(0.59);
    assert.equal(pacer('snipe').length, 2, `${cfg.mode}: the snipe decided twice`);
    assert.equal(exits().length, 0, 'refused: nothing sent');
    assert.equal(oms.positions.position(t), 10);
    assert.equal(st().reentryBlock, undefined, `${cfg.mode}: no sale, no mark`);
    risk.check = check;
    await step(0.59);
    assert.equal(oms.positions.position(t), 0);
    await step(0.45, 0.6);
    assert.match(st().reentryBlock ?? '', /^re-entry after a hold exit or quota snipe/, cfg.mode);
  }
});

test('re-entry rule: the window is the contract\'s whole open to close, not the last-share rule\'s hour', async () => {
  // Listed 3 h before its close and sniped with 40 min left: 40 of 180 minutes is not more than half, so no entry opens, although
  // 40 minutes is more than half of an hour.
  const { t, step, st, oms } = await heldOnClock({ PACER_HOURLY_USD: '1', ENTRY_WINDOW_15M: '3000,60' }, 2_400_000, 8_400_000);
  await step(0.59);
  assert.equal(oms.positions.position(t), 0);
  await step(0.45, 0.6);
  assert.match(st().reentryBlock ?? '', /^re-entry after a hold exit or quota snipe: 239\d s of the 10800 s window left, not more than 50%/, st().notes.join(' | '));
});

test('hold exit held by the exit curve\'s gate: the hunt\'s protective stop that triggered on the same evaluation still goes out', async () => {
  const curveExit = new SinuousExitGate({ mode: 'gate', minNetProfit: 0.015 }, { minTrades: 20, t: 1, maxLossUsd: 25, window: 200 });
  const { engine, recon, market, md, oms, audit } = await setup({ exitPolicy: 'confluence_ratchet', curveExit, closeIn: 200_000 });
  engine.balance = (await recon.run('startup'))!.balance;
  const t = market.ticker;
  const now = Date.now();
  // Long 10 YES bought at 0.30 as a maker.
  oms.onFill({ tradeId: 'h8', orderId: '', ticker: t, side: 'bid', count: 10, price: 0.3, isTaker: false, fee: 0, ts: now }, { closeTs: market.closeTime, asset: 'BTC' });
  const book = md.book(t);
  book.applySnapshot({ bids: [{ price: 0.5, size: 50 }], asks: [{ price: 0.52, size: 50 }] }, now);
  // A hunt that activated earlier: entry value 0.45 + the 2c margin, its stop locked at 0.47.
  const hunt = new ConfluenceRatchetExit({ targetMargin: 0.02, minConfluence: 2, lockSale: 'off' });
  assert.equal(hunt.update({ position: 10, qSide: 0.45, sideBid: 0.5, confluence: 3, book, now, tick: 0.01, fees: md.feesFor(t) }).stop, 0.47);
  (engine as unknown as { hunts: Map<string, ConfluenceRatchetExit> }).hunts.set(t, hunt);
  // The hold exit's count: 12 s at +$2.00 up to a second ago.
  const holds = (engine as unknown as { holdExits: HoldExits }).holdExits;
  for (let k = 12; k >= 1; k--) holds.sample(t, 10, 2, Date.now() - k * 1000);
  // 0.46: the stop triggers (protective), and +$1.42 after fees keeps the hold exit's run: both sell on this evaluation. The
  // curve has no reading yet and holds the profit exit; the hunt's stop is not held.
  book.applySnapshot({ bids: [{ price: 0.46, size: 50 }], asks: [{ price: 0.48, size: 50 }] }, Date.now());
  await engine.tick();
  const st = engine.status.get(t)!;
  const notes = st.notes.join(' | ');
  assert.equal(st.hold?.fire, true, notes);
  assert.match(notes, /curve: holding the profit exit at 0\.46/);
  const exits = oms.allOrders(500).filter((o) => o.ticker === t && o.reduceOnly);
  assert.deepEqual(exits.map((o) => [o.side, o.price, o.count]), [['ask', 0.46, 10]], notes);
  const why = audit.tail(50, 'decision').flatMap((r) => (r.data as { place?: Array<{ why: string }> }).place ?? []).map((p) => p.why);
  assert.deepEqual(why, ['confluence ratchet stop 0.47'], notes);
});

test('HOLD_EXIT=false: today\'s behaviour, no hold exit and no re-entry limit after a quota snipe', async () => {
  const held = await heldOnClock({ HOLD_EXIT: 'false' }, 200_000);
  assert.equal(held.cfg.strategy.holdExit.enabled, false);
  for (let i = 0; i < 20; i++) await held.step(0.59);
  assert.equal(held.exits().length, 0, held.st().notes.join(' | '));
  assert.equal(held.st().hold, undefined);
  assert.ok(!held.st().notes.some((n) => n.startsWith('hold exit')));
  const sniped = await heldOnClock({ HOLD_EXIT: 'false', PACER_HOURLY_USD: '1', ENTRY_WINDOW_15M: '840,60' }, 200_000);
  await sniped.step(0.59);
  assert.equal(sniped.pacer('snipe').length, 1);
  await sniped.step(0.45, 0.6);
  assert.equal(sniped.st().reentryBlock, undefined);
  assert.equal(sniped.st().entryWindow, true);
});

// ---- The profit ratchet beside the hold exit (RATCHET, Steven Nov 11 8:53-8:58 AM EST / 13:53-13:58 UTC) -------------------
// 10 YES bought at 0.40 with the $0.17 taker fee: +$1.56 at a 0.59 bid, +$1.66 at 0.60, a cent a contract more each tick up to
// +$2.68 at 0.70 (the exit fee rounds), +$2.27 at 0.66, +$2.17 at 0.65.

const RUN = [0.59, 0.6, 0.61, 0.62, 0.63, 0.64, 0.65, 0.66, 0.67, 0.68, 0.69, 0.7];

test('profit ratchet: a runner setting new bests rides past the hold exit\'s 10 s; a $0.50 pullback from its best sells it, whole, at the bid; audited; paper and live alike', async () => {
  for (const env of [{}, liveEnv()]) {
    const { engine, oms, cfg, t, step, st, exits, pacer, placed } = await heldOnClock(env, 200_000);
    const notes = () => `${cfg.mode}: ${st().notes.join(' | ')}`;
    assert.deepEqual(cfg.strategy.profitRatchet, { enabled: true, armUsd: 1.5, stopMinUsd: 1, trailUsd: 0.5 });
    // 0.59 arms it (+$1.56, stop +$1.06); a new best every second to 0.70: 11 s at +$1.50 or more, and still climbing.
    for (const b of RUN) await step(b);
    assert.equal(exits().length, 0, notes());
    assert.deepEqual(st().hold, { fire: false, cumSec: 11, runSec: 11, climbing: true }, notes());
    assert.match(notes(), /hold exit: 11\.0 s in all at \+\$1\.50 or more and 11\.0 s in a row at \+\$1\.00 or more, but the profit set a new best in the last 3 s: it rides the profit ratchet/);
    assert.match(notes(), /profit ratchet armed: best \+\$2\.68, stop \+\$2\.18; sold at or under the stop/);
    assert.deepEqual([st().ratchet?.armed, st().ratchet?.best, st().ratchet?.stop, st().ratchet?.sell], [true, 2.68, 2.18, false]);
    assert.deepEqual(pacer('ratchet_arm'), [{ event: 'ratchet_arm', ticker: t, netUsd: 1.56, stop: 1.06, position: 10 }]);
    // 0.66: +$2.27, above the stop; the hold exit still stands aside (the best is a second old).
    await step(0.66);
    assert.equal(exits().length, 0, notes());
    // 0.65: +$2.17, at or under the +$2.18 stop: the whole position at the bid, reduce-only, immediate-or-cancel.
    await step(0.65);
    assert.deepEqual(exits().map((o) => [o.side, o.price, o.count, o.purpose, o.timeInForce]), [['ask', 0.65, 10, 'exit', 'immediate_or_cancel']], notes());
    assert.equal(oms.positions.position(t), 0, `${cfg.mode}: filled at the bid`);
    const why = 'profit ratchet: +$2.17 net on 10 at bid 0.65 is at or under its stop +$2.18 (best +$2.68)';
    assert.ok(placed().includes(why), placed().join(' | '));
    const sale = pacer('profit_ratchet');
    assert.equal(sale.length, 1);
    assert.deepEqual([sale[0].netUsd, sale[0].stop, sale[0].best, sale[0].rest, sale[0].count, sale[0].price, sale[0].why], [2.17, 2.18, 2.68, false, 10, 0.65, why]);
    assert.equal(pacer('hold_exit').length, 0, 'not the hold exit');
    // A profit ratchet sale alone does not start the re-entry rule: Steven's rule (Nov 11 8:42-8:45 AM EST / 13:42-13:45 UTC)
    // names the hold exit and the quota snipe.
    const rule = (engine as unknown as { holdExits: { reentryBlock(t: string, tauSec: number, windowSec: number): string | undefined } }).holdExits;
    assert.equal(rule.reentryBlock(t, 185, 500), undefined);
    // Flat: the ratchet starts from nothing.
    await step(0.65);
    assert.equal(st().ratchet, undefined, notes());
  }
});

test('profit ratchet: a position sitting at +$1.56 to +$1.66 sets no new best and is sold by the hold exit at 10 s, its ratchet armed; paper and live alike', async () => {
  for (const env of [{}, liveEnv()]) {
    const { cfg, oms, t, step, st, exits, pacer, placed } = await heldOnClock(env, 200_000);
    const notes = () => `${cfg.mode}: ${st().notes.join(' | ')}`;
    // 0.59, 0.60, 0.59, ...: the best (+$1.66) is set on the second evaluation, then never again; the stop is +$1.16.
    for (let i = 0; i < 10; i++) await step(i % 2 ? 0.6 : 0.59);
    assert.equal(exits().length, 0, notes());
    assert.deepEqual([st().ratchet?.armed, st().ratchet?.best, st().ratchet?.stop], [true, 1.66, 1.16]);
    assert.deepEqual(st().hold, { fire: false, cumSec: 9, runSec: 9 }, notes());
    await step(0.59);
    assert.deepEqual(exits().map((o) => [o.side, o.price, o.count, o.purpose]), [['ask', 0.59, 10, 'exit']], notes());
    assert.equal(oms.positions.position(t), 0);
    assert.ok(placed().includes('hold exit: +$1.56 net on 10 at bid 0.59, 10.0 s in all at +$1.50 or more, the last 10.0 s in a row at +$1.00 or more'), placed().join(' | '));
    assert.deepEqual([pacer('hold_exit').length, pacer('profit_ratchet').length], [1, 0]);
  }
});

test('RATCHET=false: phase 1\'s behaviour, the runner is sold by the hold exit at 10 s; no ratchet arms or sells, and the hold exit never stands aside', async () => {
  for (const env of [{ RATCHET: 'false' }, { ...liveEnv(), RATCHET: 'false' }]) {
    const { cfg, oms, t, step, st, exits, pacer, placed } = await heldOnClock(env, 200_000);
    const notes = () => `${cfg.mode}: ${st().notes.join(' | ')}`;
    assert.equal(cfg.strategy.profitRatchet.enabled, false);
    for (const b of RUN.slice(0, 10)) await step(b);
    assert.equal(exits().length, 0, notes());
    assert.deepEqual(st().hold, { fire: false, cumSec: 9, runSec: 9 }, notes());
    assert.equal(st().ratchet, undefined);
    assert.ok(!st().notes.some((n) => n.includes('profit ratchet')), notes());
    await step(0.69);
    assert.deepEqual(exits().map((o) => [o.side, o.price, o.count]), [['ask', 0.69, 10]], notes());
    assert.equal(oms.positions.position(t), 0);
    assert.ok(placed().some((w) => w.startsWith('hold exit: +$2.58 net on 10 at bid 0.69')), placed().join(' | '));
    assert.deepEqual([pacer('ratchet_arm').length, pacer('profit_ratchet').length], [0, 0]);
  }
  // A pullback from the best that the ratchet would sell is held, as before.
  const off = await heldOnClock({ RATCHET: 'false', HOLD_EXIT: 'false' }, 200_000);
  for (const b of [...RUN, 0.66, 0.65, 0.6]) await off.step(b);
  assert.equal(off.exits().length, 0, off.st().notes.join(' | '));
});

test('profit ratchet with HOLD_EXIT=false: it still arms, sells on the pullback and pulls the market\'s resting orders; nothing else goes out with it', async () => {
  const { oms, t, step, st, exits, market } = await heldOnClock({ HOLD_EXIT: 'false' }, 200_000);
  for (const b of RUN) await step(b);
  assert.equal(st().hold, undefined);
  const ask = await oms.submit({ ticker: t, asset: 'BTC', windowCloseTs: market.closeTime, side: 'ask', price: 0.8, count: 15, timeInForce: 'good_till_canceled', postOnly: true, reduceOnly: false, purpose: 'quote', fairValue: 0.5, modelId: 'm', decisionId: 'q' });
  await step(0.65);
  assert.deepEqual(exits().map((o) => [o.side, o.price, o.count]), [['ask', 0.65, 10]], st().notes.join(' | '));
  assert.equal(oms.positions.position(t), 0);
  assert.ok(!oms.liveOrders().some((o) => o.clientOrderId === ask.clientOrderId && !o.cancelRequested), 'the resting ask is pulled');
});

test('profit ratchet in the exit-only lane (the volatility warming up after a restart): it arms on the fresh book and its stop sells the position at the bid; the hold exit does not sell from the lane', async () => {
  const { oms, t, step, st, exits, audit } = await heldOnClock({}, 200_000, undefined, 60);
  for (const b of RUN) await step(b);
  assert.equal(st().blocked, 'volatility warming up');
  assert.equal(exits().length, 0, st().notes.join(' | '));
  assert.deepEqual([st().ratchet?.armed, st().ratchet?.best, st().ratchet?.stop], [true, 2.68, 2.18]);
  await step(0.66);
  await step(0.65);
  assert.equal(st().blocked, 'volatility warming up');
  assert.deepEqual(exits().map((o) => [o.side, o.price, o.count, o.filledCount]), [['ask', 0.65, 10, 10]], st().notes.join(' | '));
  assert.equal(oms.positions.position(t), 0);
  const d = audit.tail(50, 'decision').map((r) => r.data as { lane?: string; place?: Array<{ why: string }> }).filter((r) => r.lane === 'exit_only' && r.place?.length);
  assert.match(d.at(-1)?.place?.[0].why ?? '', /^profit ratchet: \+\$2\.17 net on 10 at bid 0\.65 is at or under its stop \+\$2\.18/);
  const sale = audit.tail(50, 'pacer').map((r) => r.data as { event: string; lane?: string }).filter((x) => x.event === 'profit_ratchet');
  assert.deepEqual(sale.map((x) => x.lane), ['volatility warming up'], 'audited with the lane it sold from, as the quota floor is');
});

// ---- The trade after a partial sale, the in-flight exit guard, the line exit's last resort ----------------------------------
// (the answer given to Steven, Nov 11 9:10 AM EST / 14:10 UTC; his idea at 9:15 AM EST / 14:15 UTC and card at 9:21 AM EST /
// 14:21 UTC)

/** A reduce-only sale of `count` at `price` sent by hand: an earlier exit that sold part of the position. */
const sellPart = (s: { oms: Oms; t: string; market: MarketInfo }, count: number, price: number) =>
  s.oms.submit({ ticker: s.t, asset: 'BTC', windowCloseTs: s.market.closeTime, side: 'ask', price, count, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: true, purpose: 'exit', fairValue: 0.5, modelId: 'm', decisionId: `part-${count}` });

test('profit ratchet after a partial sale: the trade (banked plus the rest at the bid) is no drop; the rest is sold at the stop; paper and live alike', async () => {
  for (const env of [{}, liveEnv()]) {
    const h = await heldOnClock(env, 200_000);
    const { cfg, oms, t, step, st, exits, pacer, placed } = h;
    const notes = () => `${cfg.mode}: ${st().notes.join(' | ')}`;
    for (const b of RUN) await step(b);
    assert.deepEqual([st().ratchet?.best, st().ratchet?.stop], [2.68, 2.18], notes());
    // 5 of the 10 sold at the 0.70 bid bank +$1.34 after fees; the 5 left net +$1.34 at that bid. On the rest alone that is
    // under the +$2.18 stop; the trade is +$2.67, so nothing is sold.
    await sellPart(h, 5, 0.7);
    assert.equal(oms.positions.position(t), 5);
    const banked = openBankedUsd(oms.positions.get(t));
    assert.ok(Math.abs(banked - 1.335) < 1e-9, String(banked));
    await step(0.7);
    assert.equal(exits().length, 1, `${notes()}: only the sale by hand`);
    assert.match(notes(), /profit ratchet armed: best \+\$2\.68, stop \+\$2\.18/);
    // 0.60: the 5 left net +$0.83, the trade +$2.16, at or under the stop: the 5 are sold at the bid.
    await step(0.6);
    assert.deepEqual([...exits()].reverse().map((o) => [o.side, o.price, o.count]), [['ask', 0.7, 5], ['ask', 0.6, 5]], notes());
    assert.equal(oms.positions.position(t), 0, `${cfg.mode}: filled at the bid`);
    const why = `profit ratchet: +$2.16 net (+$${banked.toFixed(2)} banked by partial sales) on 5 at bid 0.6 is at or under its stop +$2.18 (best +$2.68)`;
    assert.ok(placed().includes(why), placed().join(' | '));
    const sale = pacer('profit_ratchet');
    assert.deepEqual(sale.map((x) => [x.netUsd, x.bankedUsd, x.count, x.why]), [[2.16, 1.335, 5, why]]);
  }
});

test('hold exit after a partial sale: the trade keeps its +$1.50 and its seconds, so the rest is sold at 10 s, not stranded; paper and live alike', async () => {
  for (const env of [{}, liveEnv()]) {
    const h = await heldOnClock(env, 200_000);
    const { cfg, oms, t, step, st, exits, pacer, placed } = h;
    const notes = () => `${cfg.mode}: ${st().notes.join(' | ')}`;
    for (let i = 0; i < 6; i++) await step(0.59);
    assert.deepEqual(st().hold, { fire: false, cumSec: 5, runSec: 5 }, notes());
    // 6 of the 10 sold at 0.59 bank +$0.93 after fees; the 4 left net +$0.62 at that bid, the trade +$1.55. Measured on the
    // rest alone the count would stop under +$1.50 and the run under +$1.00, and the 4 would sit there.
    await sellPart(h, 6, 0.59);
    for (let i = 0; i < 4; i++) await step(0.59);
    assert.deepEqual(st().hold, { fire: false, cumSec: 9, runSec: 9 }, notes());
    // The ratchet armed at +$1.56 (stop +$1.06) does not sell the trade at +$1.55 either.
    assert.equal(exits().length, 1, notes());
    assert.deepEqual([st().ratchet?.armed, st().ratchet?.stop], [true, 1.06]);
    await step(0.59);
    assert.deepEqual([...exits()].reverse().map((o) => [o.side, o.price, o.count]), [['ask', 0.59, 6], ['ask', 0.59, 4]], notes());
    assert.equal(oms.positions.position(t), 0);
    const why = 'hold exit: +$1.55 net (+$0.93 banked by partial sales) on 4 at bid 0.59, 10.0 s in all at +$1.50 or more, the last 10.0 s in a row at +$1.00 or more';
    assert.ok(placed().includes(why), placed().join(' | '));
    const sale = pacer('hold_exit');
    assert.deepEqual(sale.map((x) => [x.netUsd, x.bankedUsd, x.count]), [[1.55, 0.928, 4]]);
  }
});

test('in-flight exit guard: live, an exit whose fills are not booked yet holds the next one back; once booked the rest is sold; after 2 s it lets go', async () => {
  type Fill = Parameters<Oms['onFill']>[0];
  /** Live's order of events: the REST acknowledgement says what filled, the fills reach the books when the test books them. */
  const liveLike = async () => {
    const h = await heldOnClock({ ...liveEnv(), RATCHET: 'false' }, 200_000);
    const queued: Fill[] = [];
    h.paper.removeAllListeners('fill');
    h.paper.on('fill', (f: Fill) => queued.push(f));
    for (let i = 0; i < 10; i++) await h.step(0.59);
    // 10 s at +$1.56: the hold exit sells 4 into a bid of 4. The acknowledgement says they filled; the books still hold 10.
    await h.step(0.59, undefined, { size: 4 });
    assert.deepEqual(h.exits().map((o) => [o.count, o.state, o.exchangeFillCount, o.filledCount]), [[4, 'FILLED', 4, 0]], h.st().notes.join(' | '));
    assert.equal(h.oms.positions.position(h.t), 10);
    return { ...h, queued };
  };
  const a = await liveLike();
  // A second later the hold exit would sell all 10 again (the books say 10): held back, noted.
  await a.step(0.59);
  assert.equal(a.exits().length, 1, a.st().notes.join(' | '));
  assert.ok(a.st().notes.includes('exit in flight: the exit order sent 1.0 s ago has fills not booked yet (0 of 4 booked); no new exit for up to 2 s after it'), a.st().notes.join(' | '));
  // The fills reach the books: 6 left. Half a second later the rest is sold.
  for (const f of a.queued.splice(0)) a.oms.onFill(f);
  assert.equal(a.oms.positions.position(a.t), 6);
  await a.step(0.59, undefined, { ms: 500 });
  assert.deepEqual([...a.exits()].reverse().map((o) => [o.price, o.count]), [[0.59, 4], [0.59, 6]], a.st().notes.join(' | '));
  assert.ok(!a.st().notes.some((n) => n.startsWith('exit in flight')));
  // Fills never booked (lost): the guard lets go 2 s after the exit was sent, whatever its state.
  const b = await liveLike();
  await b.step(0.59);
  await b.step(0.59, undefined, { ms: 500 });
  assert.equal(b.exits().length, 1, '1.5 s after it: still held');
  await b.step(0.59, undefined, { ms: 500 });
  assert.deepEqual([...b.exits()].reverse().map((o) => o.count), [4, 10], b.st().notes.join(' | '));
});

test('in-flight exit guard: paper books its fills as they happen, so it never waits; the rest after a thin bid goes a second later', async () => {
  const { step, st, exits, oms, t, audit } = await heldOnClock({ RATCHET: 'false' }, 200_000);
  for (let i = 0; i < 10; i++) await step(0.59);
  await step(0.59, undefined, { size: 4 });
  assert.deepEqual(exits().map((o) => [o.count, o.exchangeFillCount, o.filledCount]), [[4, 4, 4]]);
  assert.equal(oms.positions.position(t), 6);
  await step(0.59);
  assert.deepEqual([...exits()].reverse().map((o) => [o.price, o.count, o.filledCount]), [[0.59, 4, 4], [0.59, 6, 6]], st().notes.join(' | '));
  assert.equal(oms.positions.position(t), 0);
  assert.ok(!audit.tail(500, 'decision').some((r) => (r.data as { event?: string }).event === 'exit_in_flight'));
});

/** The coin's live line, broken against the side or not, as the test sets it. */
class SwitchLine extends LiveLines {
  broke = true;
  override read(): LiveLineReading { return { price: 100, projected: 100.1, band: { lower: 100.04, upper: 100.16, k: 2, sec: 300 }, underSd: 2.6, slope: -0.4, breakSec: 2, broke: this.broke }; }
}
/** The line exit with its sell signal off (SINUOUS_CROSS=false, the default). */
const lineCrossOff = () => new SinuousExitGate({ mode: 'cross', minNetProfit: 0.015, crossSource: 'line', cross: false }, { minTrades: 20, t: 1, maxLossUsd: 25, window: 200 });
// One failed try: +$1.15 at a 0.55 bid, then +$0.85 at 0.52 for 3 s in a row, never +$1.50.
const TRY = [0.55, 0.52, 0.52, 0.52, 0.52];
// 270 s to the close, outside the entry window: far enough out that YES still moves with the coin (this index sits well above
// the strike, and nearer the close it prices YES at 0.9999, with no side for the line to read).
const LINE_CLOSE = 270_000;

test('line exit as a last resort: after 5 failed tries the cross sells with SINUOUS_CROSS off, on its own conditions; not before; paper and live alike', async () => {
  for (const env of [{}, liveEnv()]) {
    const { cfg, oms, t, step, st, exits, placed } = await heldOnClock(env, LINE_CLOSE, undefined, undefined, { curveExit: lineCrossOff(), liveLines: new SwitchLine() });
    const notes = () => `${cfg.mode}: ${st().notes.join(' | ')}`;
    assert.equal(cfg.strategy.holdExit.lineAfterFails, 5);
    for (let k = 0; k < 4; k++) for (const b of TRY) await step(b);
    assert.equal(st().hold?.fails, 4, notes());
    assert.match(notes(), /live line: outside its wiggle band for 2 s \(2\.6 sd; the cross would sell; it is off, SINUOUS_CROSS\)/);
    assert.match(notes(), /line exit: 4 of 5 failed tries before its last resort/);
    assert.equal(exits().length, 0, notes());
    // The 5th try: nothing until it has failed.
    for (const b of TRY.slice(0, 4)) await step(b);
    assert.equal(exits().length, 0, notes());
    await step(0.52);
    assert.equal(st().hold?.fails, 5);
    assert.deepEqual(exits().map((o) => [o.side, o.price, o.count, o.purpose, o.timeInForce]), [['ask', 0.52, 10, 'exit', 'immediate_or_cancel']], notes());
    assert.equal(oms.positions.position(t), 0, `${cfg.mode}: filled at the bid`);
    const why = 'exit curve: cross 0.52 (+0.085 a contract net, live line outside its wiggle band for 2 s (2.6 sd, band +-2 sd of 300 s since the open)); last resort after 5 failed tries (HOLD_EXIT_LINE_AFTER_FAILS)';
    assert.ok(placed().includes(why), placed().join(' | '));
  }
});

test('line exit as a last resort: the line must be broken, the take-profit floor cleared; HOLD_EXIT_LINE_AFTER_FAILS=0 or HOLD_EXIT=false never sells', async () => {
  const run = async (env: Record<string, string>, line: SwitchLine, tries = 5) => {
    const h = await heldOnClock(env, LINE_CLOSE, undefined, undefined, { curveExit: lineCrossOff(), liveLines: line });
    for (let k = 0; k < tries; k++) for (const b of TRY) await h.step(b);
    await h.step(0.52);
    return h;
  };
  // The line not broken: 5 failed tries alone sell nothing; once it breaks the cross sells.
  const quiet = new SwitchLine();
  quiet.broke = false;
  const q = await run({}, quiet);
  assert.equal(q.st().hold?.fails, 5);
  assert.ok(q.st().notes.includes('line exit: 5 failed tries (HOLD_EXIT_LINE_AFTER_FAILS 5): the cross may sell this position as a last resort'), q.st().notes.join(' | '));
  assert.equal(q.exits().length, 0, q.st().notes.join(' | '));
  quiet.broke = true;
  await q.step(0.52);
  assert.deepEqual(q.exits().map((o) => [o.price, o.count]), [[0.52, 10]], q.st().notes.join(' | '));
  // PROFIT_TARGET_PCT=0.5: the floor is half the 0.417 cost a contract; +0.085 does not clear it.
  const floor = await run({ PROFIT_TARGET_PCT: '0.5' }, new SwitchLine());
  assert.equal(floor.st().hold?.fails, 5);
  assert.equal(floor.exits().length, 0, floor.st().notes.join(' | '));
  // HOLD_EXIT_LINE_AFTER_FAILS=0: never, whatever the count.
  const off = await run({ HOLD_EXIT_LINE_AFTER_FAILS: '0' }, new SwitchLine(), 7);
  assert.equal(off.st().hold?.fails, 7);
  assert.equal(off.exits().length, 0, off.st().notes.join(' | '));
  assert.ok(!off.st().notes.some((n) => n.startsWith('line exit:')));
  // HOLD_EXIT=false: no tries are counted, so no last resort: the line exit stays off as before.
  const noHold = await run({ HOLD_EXIT: 'false' }, new SwitchLine(), 7);
  assert.equal(noHold.st().hold, undefined);
  assert.equal(noHold.exits().length, 0, noHold.st().notes.join(' | '));
});

test('exit curve: the cross measures the open position\'s own entry fee, not the market\'s fees from earlier round trips', async () => {
  const curveExit = new SinuousExitGate({ mode: 'cross', minNetProfit: 0.015, crossSource: 'line' }, { minTrades: 20, t: 1, maxLossUsd: 25, window: 200 });
  const { engine, recon, market, md, oms, audit } = await setup({ exitPolicy: 'hold', curveExit, liveLines: new SwitchLine(), closeIn: 200_000, env: { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false' } });
  engine.balance = (await recon.run('startup'))!.balance;
  const t = market.ticker;
  const order = (side: 'bid' | 'ask', price: number) => oms.submit({ ticker: t, asset: 'BTC', windowCloseTs: market.closeTime, side, price, count: 10, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'entry', fairValue: 0.5, modelId: 'm', decisionId: `rt-${side}-${price}` });
  // A round trip first (10 YES sold at 0.45, bought back at 0.40: $0.18 and $0.17 in fees), then 10 YES bought at 0.40 ($0.17).
  md.book(t).applySnapshot({ bids: [{ price: 0.45, size: 50 }], asks: [{ price: 0.47, size: 50 }] }, Date.now());
  await order('ask', 0.45);
  md.book(t).applySnapshot({ bids: [{ price: 0.38, size: 50 }], asks: [{ price: 0.4, size: 50 }] }, Date.now());
  await order('bid', 0.4);
  await order('bid', 0.4);
  const pos = oms.positions.get(t)!;
  assert.deepEqual([pos.yes, Math.round(pos.fees * 100) / 100, Math.round(openEntryFee(pos)! * 1e4) / 1e4], [10, 0.52, 0.017]);
  // At a 0.48 bid: 0.48 - 0.40 - the 0.017 entry fee - the 0.018 exit fee = +0.045 a contract, over the 10% floor (0.0417).
  // With the market's fees ($0.052 a contract) it read +0.010 under a 0.0452 floor, and the line's break sold nothing.
  md.book(t).applySnapshot({ bids: [{ price: 0.48, size: 50 }], asks: [{ price: 0.5, size: 50 }] }, Date.now());
  await engine.tick();
  const notes = engine.status.get(t)!.notes.join(' | ');
  const exits = oms.allOrders(500).filter((o) => o.ticker === t && o.reduceOnly);
  assert.deepEqual(exits.map((o) => [o.side, o.price, o.count]), [['ask', 0.48, 10]], notes);
  const why = audit.tail(50, 'decision').flatMap((d) => ((d.data as { place?: Array<{ why: string }> }).place ?? []).map((p) => p.why));
  assert.ok(why.some((w) => /^exit curve: cross 0\.48 \(\+0\.045 a contract net, live line outside its wiggle band/.test(w)), why.join(' | '));
});

// ---- Review fixes (Nov 11): an add, a restart, a reopen, the guard on every path, the lane's partial sale and entry fee ------

/** A 10-YES IOC bought by hand at `price` (an entry of ours that filled between two evaluations). */
const buyMore = (s: { oms: Oms; t: string; market: MarketInfo }, count: number, price: number) =>
  s.oms.submit({ ticker: s.t, asset: 'BTC', windowCloseTs: s.market.closeTime, side: 'bid', price, count, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'entry', fairValue: 0.5, modelId: 'm', decisionId: `add-${count}-${price}` });

test('profit ratchet: an add to the position starts its ratchet afresh; the added lot\'s spread and fees do not sell the larger position at the old stop; paper and live alike', async () => {
  for (const env of [{}, liveEnv()]) {
    const h = await heldOnClock(env, 200_000);
    const { cfg, oms, t, step, st, exits } = h;
    const notes = () => `${cfg.mode}: ${st().notes.join(' | ')}`;
    // 0.59 arms (+$1.56, stop +$1.06); 0.58 (+$1.45) holds.
    await step(0.59);
    await step(0.58);
    assert.deepEqual([st().ratchet?.armed, st().ratchet?.stop], [true, 1.06], notes());
    // 20 more bought at the 0.60 ask: the 30 net +$0.37 at the 0.58 bid, under the old stop, which would sell all 30.
    await buyMore(h, 20, 0.6);
    assert.equal(oms.positions.position(t), 30);
    await step(0.58);
    assert.equal(exits().length, 0, notes());
    assert.deepEqual(st().ratchet, { armed: false, sell: false }, notes());
    // It arms again on the 30's own profit: +$1.59 at 0.62.
    await step(0.62);
    assert.deepEqual([st().ratchet?.armed, st().ratchet?.best, st().ratchet?.stop], [true, 1.59, 1.09], notes());
  }
});

test('profit ratchet: an armed stop survives a restart or deploy (saved in the book folder); the restarted bot sells at the stop it had', async () => {
  const h = await heldOnClock({}, 200_000);
  for (const b of RUN) await h.step(b);
  assert.deepEqual([h.st().ratchet?.best, h.st().ratchet?.stop], [2.68, 2.18]);
  const file = path.join(h.cfg.bookDir ?? h.cfg.dataDir!, 'profit_ratchet_state.json');
  assert.deepEqual((JSON.parse(fs.readFileSync(file, 'utf8')) as { tracks: Array<{ ticker: string; state: { stop: number } }> }).tracks.map((x) => [x.ticker, x.state.stop]), [[h.t, 2.18]]);
  // A restart: a new engine on the same data folder and books.
  const again = new Engine(h.deps);
  again.balance = h.engine.balance;
  const idx = h.md.index.get('BTC')!;
  h.clock.t += 1000;
  h.md.book(h.t).applySnapshot({ bids: [{ price: 0.65, size: 50 }], asks: [{ price: 0.67, size: 50 }] }, h.clock.t);
  idx.add(idx.latest()!.value, h.clock.t);
  // 0.65: +$2.17, at or under the +$2.18 stop it had: sold. A fresh ratchet would arm there with a +$1.67 stop and hold.
  await again.tick();
  const notes = again.status.get(h.t)?.notes.join(' | ');
  assert.deepEqual(h.exits().map((o) => [o.side, o.price, o.count]), [['ask', 0.65, 10]], notes);
  assert.equal(h.oms.positions.position(h.t), 0);
  assert.ok(h.placed().includes('profit ratchet: +$2.17 net on 10 at bid 0.65 is at or under its stop +$2.18 (best +$2.68)'), h.placed().join(' | '));
});

test('profit ratchet: a position it sold flat and reopened on the same side before the next evaluation starts from nothing (the fill resets it); paper and live alike', async () => {
  for (const env of [{}, liveEnv()]) {
    const h = await heldOnClock(env, 200_000);
    const { cfg, oms, t, step, st, exits } = h;
    const notes = () => `${cfg.mode}: ${st().notes.join(' | ')}`;
    for (const b of [...RUN, 0.66, 0.65]) await step(b);
    assert.equal(exits().length, 1, notes());
    assert.equal(oms.positions.position(t), 0);
    // A YES bid of ours fills 10 at 0.67 before the next evaluation: the position is never seen flat.
    await buyMore(h, 10, 0.67);
    assert.equal(oms.positions.position(t), 10);
    await step(0.65);
    assert.equal(exits().length, 1, `${notes()}: the old sale does not go on`);
    assert.deepEqual(st().ratchet, { armed: false, sell: false }, notes());
  }
});

/** Live's order of events (see the in-flight guard tests above): the paper fills are queued, the books get them when booked. */
async function liveQueued(o: { historySec?: number; env?: Record<string, string> } = {}) {
  type Fill = Parameters<Oms['onFill']>[0];
  const h = await heldOnClock({ ...liveEnv(), ...o.env }, 200_000, undefined, o.historySec);
  const queued: Fill[] = [];
  h.paper.removeAllListeners('fill');
  h.paper.on('fill', (f: Fill) => queued.push(f));
  const book = () => { for (const f of queued.splice(0)) h.oms.onFill(f); };
  return { ...h, queued, book };
}

test('in-flight exit guard in the exit-only lane: live, a profit ratchet sale whose fills are not booked yet holds the next sale back; once booked the rest is sold', async () => {
  const h = await liveQueued({ historySec: 60 });
  const notes = () => h.st().notes.join(' | ');
  for (const b of [...RUN, 0.66]) await h.step(b);
  // 0.65 with 4 bid: the ratchet sells, 4 fill; the acknowledgement says so, the books still hold 10.
  await h.step(0.65, undefined, { size: 4 });
  assert.equal(h.st().blocked, 'volatility warming up');
  assert.deepEqual(h.exits().map((o) => [o.count, o.state, o.exchangeFillCount, o.filledCount]), [[4, 'FILLED', 4, 0]], notes());
  // A second later the lane would sell the 10 the books still show: held back, noted.
  await h.step(0.65);
  assert.equal(h.exits().length, 1, notes());
  assert.ok(h.st().notes.includes('exit in flight: the exit order sent 1.0 s ago has fills not booked yet (0 of 4 booked); no new exit for up to 2 s after it'), notes());
  h.book();
  assert.equal(h.oms.positions.position(h.t), 6);
  await h.step(0.65, undefined, { ms: 500 });
  assert.deepEqual([...h.exits()].reverse().map((o) => [o.price, o.count]), [[0.65, 4], [0.65, 6]], notes());
  assert.match(h.placed().at(-1) ?? '', /^profit ratchet, the rest: /);
});

test('in-flight exit guard under the kill switch: live, an exit whose fills are not booked yet holds the kill exit back; once booked the rest is sold', async () => {
  const h = await liveQueued({ env: { RATCHET: 'false' } });
  const killExits = () => h.audit.tail(500, 'decision').map((x) => x.data as { leg?: string }).filter((x) => x.leg === 'kill_exit');
  // The book falls to 0.30 / 0.32: the 10 are at a loss. 4 are sold by hand into a bid of 4; the books still hold 10.
  await h.step(0.3, 0.32, { size: 4 });
  await sellPart(h, 4, 0.3);
  assert.deepEqual(h.exits().map((o) => [o.count, o.state, o.exchangeFillCount, o.filledCount]), [[4, 'FILLED', 4, 0]]);
  await h.kill.engage('5 consecutive order errors (test)', 'oms');
  // Half a second later the kill exit would sell the 10 the books show: held back.
  await h.step(0.3, 0.32, { ms: 500 });
  assert.deepEqual([h.exits().length, killExits().length], [1, 0]);
  // Booked: 6 left, and the kill exit sells them.
  h.book();
  await h.step(0.3, 0.32, { ms: 500 });
  assert.deepEqual([...h.exits()].reverse().map((o) => [o.price, o.count]), [[0.3, 4], [0.3, 6]]);
  assert.equal(killExits().length, 1);
});

test('in-flight exit guard at placement: an exit that reaches the order path while one is unbooked (an overlapping evaluation, a tennis exit) is not sent, audited once a minute, and goes after 2 s; a guarded whole-position sale takes the plan\'s quotes and entries with it', async () => {
  const h = await liveQueued();
  await h.step(0.59, undefined, { size: 4 });
  await sellPart(h, 4, 0.59);
  const m = h.md.activeMarkets(h.clock.t).find((x) => x.ticker === h.t)!;
  const e = h.engine as unknown as {
    placeChecked(m: unknown, p: OrderPlan, q: number, decisionId: string): Promise<boolean>;
    holdForExitInFlight(t: string, plan: { place: OrderPlan[]; cancel: unknown[]; notes: string[] }, now: number): void;
  };
  const exit: OrderPlan = { side: 'ask', price: 0.59, count: 10, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: true, purpose: 'exit', edge: 0, why: 'test exit' };
  const inFlight = () => h.audit.tail(500, 'decision').map((r) => r.data as { event?: string; held?: { why: string } }).filter((d) => d.event === 'exit_in_flight');
  h.clock.t += 500;
  assert.equal(await e.placeChecked(m, exit, 0.5, 'd1'), false);
  h.clock.t += 500;
  assert.equal(await e.placeChecked(m, exit, 0.5, 'd2'), false);
  assert.equal(h.exits().length, 1, 'nothing more sent');
  assert.deepEqual(inFlight().map((d) => d.held?.why), ['test exit'], 'audited once a minute');
  // The plan of an evaluation with the exit still in flight: a sale of the whole position (a hold exit, a quota snipe, a profit
  // ratchet sale) drops the plan's quotes and entries with it; any other exit goes alone and they stay.
  const quote: OrderPlan = { side: 'bid', price: 0.5, count: 5, timeInForce: 'good_till_canceled', postOnly: true, reduceOnly: false, purpose: 'quote', edge: 0.03, why: 'maker bid' };
  const whole = { place: [{ ...exit, liquidation: { hold: true } }, quote], cancel: [], notes: [] as string[] };
  e.holdForExitInFlight(h.t, whole, h.clock.t);
  assert.deepEqual(whole.place, []);
  assert.match(whole.notes[0], /^exit in flight: /);
  const part = { place: [exit, quote], cancel: [], notes: [] as string[] };
  e.holdForExitInFlight(h.t, part, h.clock.t);
  assert.deepEqual(part.place, [quote]);
  // 2 s after the first exit was sent the guard lets go, whatever its state.
  h.clock.t += 1000;
  assert.equal(await e.placeChecked(m, exit, 0.5, 'd3'), true);
  assert.equal(h.exits().length, 2);
});

test('profit ratchet after a partial sale, in the exit-only lane: the trade (banked plus the rest at the bid) is no drop; the rest is sold at the stop', async () => {
  const h = await heldOnClock({}, 200_000, undefined, 60);
  const { oms, t, step, st, exits, placed } = h;
  const notes = () => st().notes.join(' | ');
  for (const b of RUN) await step(b);
  assert.equal(st().blocked, 'volatility warming up');
  assert.deepEqual([st().ratchet?.best, st().ratchet?.stop], [2.68, 2.18], notes());
  // 5 of the 10 sold at 0.70 bank +$1.34: the 5 left net +$1.34 at that bid, under the stop; the trade is +$2.67.
  await sellPart(h, 5, 0.7);
  const banked = openBankedUsd(oms.positions.get(t));
  await step(0.7);
  assert.equal(exits().length, 1, `${notes()}: only the sale by hand`);
  // 0.60: the trade +$2.16, at or under the stop: the 5 left are sold from the lane.
  await step(0.6);
  assert.equal(st().blocked, 'volatility warming up');
  assert.deepEqual([...exits()].reverse().map((o) => [o.side, o.price, o.count]), [['ask', 0.7, 5], ['ask', 0.6, 5]], notes());
  assert.equal(oms.positions.position(t), 0);
  assert.ok(placed().includes(`profit ratchet: +$2.16 net (+$${banked.toFixed(2)} banked by partial sales) on 5 at bid 0.6 is at or under its stop +$2.18 (best +$2.68)`), placed().join(' | '));
});

test('exit curve in the exit-only lane: its gate measures the open position\'s own entry fee, not the market\'s fees from earlier round trips', async () => {
  const curveExit = new SinuousExitGate({ mode: 'gate', minNetProfit: 0.015 }, { minTrades: 20, t: 1, maxLossUsd: 25, window: 200 });
  const { engine, recon, market, md, oms } = await setup({ historySec: 60, curveExit, env: { PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false' } });
  engine.balance = (await recon.run('startup'))!.balance;
  const t = market.ticker;
  const order = (side: 'bid' | 'ask', price: number) => oms.submit({ ticker: t, asset: 'BTC', windowCloseTs: market.closeTime, side, price, count: 10, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'entry', fairValue: 0.5, modelId: 'm', decisionId: `rt-${side}-${price}` });
  // A round trip first ($0.18 and $0.17 in fees), then 10 YES bought at 0.40 ($0.17): the market's fees are $0.052 a contract,
  // the open position's $0.017.
  md.book(t).applySnapshot({ bids: [{ price: 0.45, size: 50 }], asks: [{ price: 0.47, size: 50 }] }, Date.now());
  await order('ask', 0.45);
  md.book(t).applySnapshot({ bids: [{ price: 0.38, size: 50 }], asks: [{ price: 0.4, size: 50 }] }, Date.now());
  await order('bid', 0.4);
  await order('bid', 0.4);
  assert.equal(Math.round(openEntryFee(oms.positions.get(t)!)! * 1e4) / 1e4, 0.017);
  const notes = () => engine.status.get(t)!.notes.join(' | ');
  // 0.56 arms the take-profit; at 0.50 it sells +0.065 a contract (0.50 - 0.40 - the 0.017 entry fee - the 0.018 exit fee), a
  // profit exit the gate holds. Measured with the market's fees it read +0.030.
  md.book(t).applySnapshot({ bids: [{ price: 0.56, size: 50 }], asks: [{ price: 0.58, size: 50 }] }, Date.now());
  await engine.tick();
  md.book(t).applySnapshot({ bids: [{ price: 0.5, size: 50 }], asks: [{ price: 0.52, size: 50 }] }, Date.now());
  await engine.tick();
  assert.equal(engine.status.get(t)!.blocked, 'volatility warming up');
  assert.equal(oms.allOrders(500).filter((o) => o.ticker === t && o.reduceOnly).length, 0, notes());
  assert.match(notes(), /curve: holding the profit exit at 0\.5 \(net \+6\.5c\)/);
});

test('hunt mode is not blocked in twilight by default; HUNT_SESSION_GUARD=true blocks it as before (Steven, Nov 11 2026)', async () => {
  const twilight = Date.parse('2026-07-15T21:00:00Z');
  const off = await setup({ exitPolicy: 'confluence_ratchet' });
  assert.equal(off.cfg.strategy.huntSessionGuard, false);
  assert.equal(off.engine.sessionStatus(twilight).key, 'twilight');
  assert.equal(off.engine.sessionStatus(twilight).huntBlocked, undefined);
  const on = await setup({ exitPolicy: 'confluence_ratchet', env: { HUNT_SESSION_GUARD: 'true' } });
  assert.match(on.engine.sessionStatus(twilight).huntBlocked ?? '', /twilight/);
});
