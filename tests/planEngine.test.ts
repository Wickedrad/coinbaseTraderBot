// PLAN_RULES in the engine (bot/engine.ts, paper and live alike): a position opened by a plan rule is sold by the plan's
// ratchet and end rule (bot/plan/planRatchet.ts); the pacer only reports pace for it; today's exits leave it alone. Off
// (the default), every position is managed as before, tagged or not.
import assert from 'node:assert/strict';
import path from 'node:path';
import { test } from 'node:test';
import { Alerter } from '../bot/alerts/alerter';
import { loadConfig, type StrategyConfig } from '../bot/config';
import { DEFAULT_FEES } from '../bot/fees';
import { Engine } from '../bot/engine';
import type { KalshiRest } from '../bot/kalshi/rest';
import type { MarketInfo } from '../bot/kalshi/types';
import { MarketData, Recorder } from '../bot/marketdata/marketData';
import { MetaModel } from '../bot/model/metaModel';
import { Oms } from '../bot/oms/oms';
import { PaperExchange } from '../bot/paper/paperExchange';
import { KillSwitch } from '../bot/risk/killSwitch';
import { RiskGateway } from '../bot/risk/riskGateway';
import { Reconciler } from '../bot/recon/reconciler';
import { ConfluenceRatchetExit } from '../bot/strategy/exitPolicies';
import { decide, type MarketView } from '../bot/strategy/fairValueStrategy';
import { SinuousExitGate } from '../bot/strategy/sinuousExit';
import type { PlanEvent } from '../bot/plan/planRatchet';
import { openExchange, tmpAudit, tmpDir } from './helpers';

const PLAN_ON = { PLAN_RULES: 'true' };

/** One 15-minute BTC market on the paper exchange, its index warmed up (`historySec` of history: 60 = just after a restart,
 *  the volatility still warming up), `closeIn` ms to the close, the window `windowMs` long. `clock`: the engine's clock and
 *  the books' and index's timestamps follow it (advance() moves it and keeps the index fresh); else the wall clock. */
async function setup(o: { env?: Record<string, string>; historySec?: number; closeIn?: number; windowMs?: number; curveExit?: SinuousExitGate; dir?: string; clock?: { t: number } } = {}) {
  const dir = o.dir ?? tmpDir();
  const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(40), DATA_DIR: dir, RISK_DAILY_LOSS_USD: '10', DOMINANCE_FEED: 'false', SPOT_FEED: 'false', STRATEGY_SERIES: 'KXBTC15M', SESSION_EDGE_NO_ENTRY: 'false', TENNIS_ENABLED: 'false', PAPER_TRAINING_TRADES_PER_HOUR: '0', PAPER_EXPLORE: 'false', ...o.env });
  const clock = o.clock;
  const wall = () => clock?.t ?? Date.now();
  const now = wall();
  const closeTime = now + (o.closeIn ?? 600_000);
  const market: MarketInfo = { ticker: 'KXBTC15M-TEST', seriesTicker: 'KXBTC15M', status: 'open', openTime: closeTime - (o.windowMs ?? 900_000), closeTime, floorStrike: 60000, tickSize: 0.01 };
  const rest = { getSeriesFees: async () => ({ feeType: 'quadratic', multiplier: 1 }), getOpenMarkets: async () => [market], getMarket: async () => market } as unknown as KalshiRest;
  const audit = tmpAudit();
  const md = new MarketData(cfg, rest, undefined, new Recorder(path.join(dir, 'rec')));
  await md.refreshCatalog(now);
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.45, size: 50 }], asks: [{ price: 0.6, size: 50 }] }, now);
  const idx = md.index.get('BTC')!;
  let seed = 1;
  const rand = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
  let x = Math.log(60010);
  for (let s = o.historySec ?? 600; s >= 0; s--) { x += 0.0002 * (rand() - 0.5); idx.add(Math.exp(x), now - s * 1000); }
  const paper = new PaperExchange(undefined, 200, (t) => md.books.get(t), () => ({ takerMultiplier: 1, makerMultiplier: 0 }));
  const kill = new KillSwitch(path.join(dir, 'kill.json'), audit);
  const oms = new Oms({ gateway: paper, audit, statePath: path.join(dir, 'oms.json'), feesFor: (t) => md.feesFor(t), sleep: async () => undefined });
  kill.bindCancelAll((r) => oms.cancelAll(r));
  paper.on('fill', (f) => oms.onFill(f));
  paper.on('order', (ord) => oms.onExchangeOrder(ord));
  const recon = new Reconciler({ gateway: paper, oms, audit, getMarket: rest.getMarket, onPersistentBreak: (r) => void kill.engage(r, 'recon') });
  const deps = { cfg, audit, alerter: new Alerter([], audit), md, gateway: paper, oms, risk: new RiskGateway(cfg.risk), kill, recon, model: MetaModel.identity(), exchangeStatus: openExchange(), curveExit: o.curveExit, ...(clock ? { now: () => clock.t } : {}) };
  const engine = new Engine(deps);
  engine.balance = (await recon.run('startup'))!.balance;
  const t = market.ticker;
  /** Buys `count` YES (`side` bid) or NO (`side` ask: YES sold at `price`) on the paper exchange with a taker order. */
  const hold = async (side: 'bid' | 'ask', price: number, count: number) => {
    md.book(t).applySnapshot(side === 'bid' ? { bids: [{ price: price - 0.02, size: 100 }], asks: [{ price, size: 100 }] } : { bids: [{ price, size: 100 }], asks: [{ price: price + 0.02, size: 100 }] }, wall());
    await oms.submit({ ticker: t, asset: 'BTC', windowCloseTs: closeTime, side, price, count, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'entry', fairValue: 0.5, modelId: 'm', decisionId: 'e' });
    assert.equal(oms.positions.position(t), side === 'bid' ? count : -count);
  };
  /** Sets the book: `bid` / `ask` YES prices, 50 deep unless a size is given. */
  const book = (bid: number, ask: number, bidSize = 50) => md.book(t).applySnapshot({ bids: [{ price: bid, size: bidSize }], asks: [{ price: ask, size: 50 }] }, wall());
  /** Moves the injected clock on `ms` and adds an index point there (the index stays fresh). */
  const advance = (ms: number) => { clock!.t += ms; idx.add(Math.exp(x), clock!.t); };
  /** The held YES side's bid moved to `b` (ask 2c above). */
  const yesAt = async (b: number) => { book(b, Math.round((b + 0.02) * 100) / 100); await engine.tick(); };
  /** The held NO side's bid moved to `nb`: the YES ask is 1 - nb. */
  const noAt = async (nb: number) => { const a = Math.round((1 - nb) * 100) / 100; book(Math.round((a - 0.02) * 100) / 100, a); await engine.tick(); };
  /** The reduce-only orders, oldest first. */
  const exits = () => oms.allOrders(500).filter((r) => r.ticker === t && r.reduceOnly).sort((a, b) => a.createdTs - b.createdTs);
  /** Risk rejects of reduce-only orders (the old model's opposite-side quote can still be rejected for its distance from the
   *  touch: a known gap, not a plan sale). */
  const exitRejects = () => audit.tail(500, 'risk_reject').filter((r) => (r.data as { intent?: { reduceOnly?: boolean } }).intent?.reduceOnly !== false);
  const planEvents = () => audit.tail(500, 'plan').map((r) => r.data as PlanEvent);
  const whys = () => audit.tail(500, 'decision').flatMap((d) => ((d.data as { place?: Array<{ why: string }> }).place ?? []).map((p) => p.why));
  const notes = () => engine.status.get(t)?.notes.join(' | ') ?? 'not evaluated';
  const tag = (side: 'yes' | 'no', settings?: { armC?: number; trailC?: number }) => engine.planPositions.tag({ ticker: t, side, ruleId: 'dummy-heat', ...(settings ? { settings } : {}) }, wall());
  return { dir, cfg, deps, md, paper, oms, kill, engine, market, audit, t, hold, book, advance, yesAt, noAt, exits, exitRejects, planEvents, whys, notes, tag };
}

type G = Awaited<ReturnType<typeof setup>>;

/** The take-profit's walk on 10 YES bought at 0.40 (taker: 1.7c entry fee a contract): best 0.56, then 0.51 (more than a
 *  third of the best gain given back: the take-profit's sale), then 0.48. Returns the reduce-only orders after each step. */
async function takeProfitWalk(g: G): Promise<Array<Array<[string, number, number]>>> {
  const steps: Array<Array<[string, number, number]>> = [];
  for (const b of [0.5, 0.56, 0.51, 0.48]) {
    await g.yesAt(b);
    steps.push(g.exits().map((o) => [o.side, o.price, o.count]));
  }
  return steps;
}

test('PLAN_RULES off (the default): a plan-tagged position is managed by today\'s exits exactly as an untagged one', async () => {
  const runs: Array<{ steps: Array<Array<[string, number, number]>>; whys: string[]; plan: number; tagged: boolean }> = [];
  for (const tagged of [false, true]) {
    const g = await setup();
    assert.equal(g.cfg.plan.enabled, false);
    await g.hold('bid', 0.4, 10);
    if (tagged) g.tag('yes');
    const steps = await takeProfitWalk(g);
    runs.push({ steps, whys: g.whys().filter((w) => !w.startsWith('maker')), plan: g.planEvents().length, tagged: g.engine.planPositions.get(g.t) !== undefined });
  }
  assert.deepEqual(runs[1].steps, runs[0].steps);
  assert.deepEqual(runs[1].whys, runs[0].whys);
  // Today's take-profit sold at 0.51, more than a third of the best gain given back.
  assert.deepEqual(runs[1].steps[2], [['ask', 0.51, 10]]);
  assert.match(runs[1].whys.find((w) => w.startsWith('take-profit')) ?? '', /^take-profit: \+0\.075 a contract net of fees/);
  assert.deepEqual([runs[1].plan, runs[1].tagged], [0, false], 'no plan event; the sale left it flat and cleared the tag');
});

test('PLAN_RULES on: a tagged YES arms, raises its floor, is left alone by the take-profit, and sells the whole position at the bid less 2 ticks', async () => {
  const g = await setup({ env: PLAN_ON });
  await g.hold('bid', 0.4, 10);
  g.tag('yes');
  // 0.50: +6.5c a contract after the 1.7c entry fee and the 1.8c exit fee: armed at the fee floor price 0.44 (peak less 8c is 0.42).
  await g.yesAt(0.49);
  assert.equal(g.planEvents().length, 0, g.notes());
  await g.yesAt(0.5);
  await g.yesAt(0.56);
  // 0.51: the take-profit would sell here (see the test above); the plan holds above its 0.48 floor.
  await g.yesAt(0.51);
  assert.deepEqual(g.exits(), [], g.notes());
  assert.match(g.notes(), /plan position: its own ratchet and end rule sell it; no other exit/);
  assert.match(g.notes(), /plan ratchet armed: bid 0\.51, floor 0\.48, peak 0\.56/);
  // 0.48: at the floor. Sold: all 10, reduce-only, immediate-or-cancel, limit 0.46; it fills at the 0.48 bid.
  await g.yesAt(0.48);
  assert.deepEqual(g.exits().map((o) => [o.side, o.price, o.count, o.timeInForce, o.purpose, o.filledCount]), [['ask', 0.46, 10, 'immediate_or_cancel', 'exit', 10]], g.notes());
  assert.equal(g.oms.positions.position(g.t), 0);
  const ev = g.planEvents();
  assert.deepEqual(ev.map((e) => e.event), ['plan_ratchet_arm', 'plan_ratchet_raise', 'plan_ratchet_sell']);
  assert.deepEqual([ev[0].bid, ev[0].floor, ev[0].feeFloor, ev[0].net, ev[0].side, ev[0].ruleId], [0.5, 0.44, 0.44, 0.065, 'yes', 'dummy-heat']);
  assert.deepEqual([ev[1].prevFloor, ev[1].floor, ev[1].peak], [0.44, 0.48, 0.56]);
  assert.deepEqual([ev[2].bid, ev[2].floor, ev[2].limit, ev[2].count], [0.48, 0.48, 0.46, 10]);
  assert.ok(ev[2].net! >= 0, 'not below fees');
  assert.ok(ev.every((e) => typeof e.at === 'number' && e.ticker === g.t));
  assert.ok(g.whys().some((w) => /^plan ratchet: bid 0\.48 at or under its floor 0\.48 .*limit 0\.46 \(bid less 2 ticks\)$/.test(w)), g.whys().join(' | '));
  assert.ok(!g.whys().some((w) => w.startsWith('take-profit')));
  // Flat: the tag cleared itself.
  assert.equal(g.engine.planPositions.get(g.t), undefined);
  assert.deepEqual(g.exitRejects(), []);
});

test('PLAN_RULES on: a tagged NO position sells at the NO bid less 2 ticks (YES bought at 1 - that)', async () => {
  const g = await setup({ env: PLAN_ON });
  // 10 NO at 0.40: YES sold at 0.60.
  await g.hold('ask', 0.6, 10);
  g.tag('no');
  await g.noAt(0.5);
  await g.noAt(0.56);
  await g.noAt(0.51);
  assert.deepEqual(g.exits(), [], g.notes());
  await g.noAt(0.48);
  assert.deepEqual(g.exits().map((o) => [o.side, o.price, o.count, o.filledCount]), [['bid', 0.54, 10, 10]], g.notes());
  assert.equal(g.oms.positions.position(g.t), 0);
  const ev = g.planEvents();
  assert.deepEqual(ev.map((e) => [e.event, e.side, e.bid, e.floor]), [['plan_ratchet_arm', 'no', 0.5, 0.44], ['plan_ratchet_raise', 'no', 0.56, 0.48], ['plan_ratchet_sell', 'no', 0.48, 0.48]]);
  assert.equal(ev[2].limit, 0.46);
});

test('PLAN_RULES on: the pacer does not sell a plan position at the hour\'s need, nor arm or sell a floor; its realized P&L still counts toward the pace', async () => {
  // The hour needs $0.50 (PACER_HOURLY_USD 0.5). 10 YES at 0.40: at the 0.49 bid +$0.55 after fees covers it.
  const env = { PACER_HOURLY_USD: '0.5', PACER_MIN_TAKE_USD: '0.1' };
  const sold: Record<string, Array<[number, number]>> = {};
  for (const [name, e, tagged] of [['untagged', env, false], ['tagged, off', env, true], ['tagged, on', { ...env, ...PLAN_ON }, true]] as const) {
    const g = await setup({ env: { ...e, EXIT_POLICY: 'hold' } });
    await g.hold('bid', 0.4, 10);
    if (tagged) g.tag('yes');
    await g.yesAt(0.49);
    sold[name] = g.exits().map((o) => [o.price, o.count]);
    const pacer = g.audit.tail(200, 'pacer').map((r) => r.data as { event: string; ticker?: string });
    if (name === 'tagged, on') {
      assert.deepEqual(pacer.filter((p) => p.ticker === g.t && (p.event === 'snipe' || p.event === 'floor')), []);
      assert.equal(g.engine.status.get(g.t)!.snipe!.atUsd, undefined, 'the badge shows no target on a plan position');
      // The ratchet's own sale still credits the pace: arm at 0.50, raise at 0.60, sell at 0.52.
      for (const b of [0.5, 0.6, 0.52]) await g.yesAt(b);
      assert.equal(g.oms.positions.position(g.t), 0, g.notes());
      const credit = g.audit.tail(200, 'pacer').map((r) => r.data as { event: string; usd?: number; realized24hUsd?: number }).find((p) => p.event === 'credit');
      assert.ok(credit && credit.usd! > 0.8 && credit.realized24hUsd! > 0.8, JSON.stringify(credit));
      assert.equal(g.audit.tail(200, 'pacer').filter((r) => ['snipe', 'floor'].includes((r.data as { event: string }).event)).length, 0);
    } else {
      assert.ok(pacer.some((p) => p.event === 'snipe' && p.ticker === g.t), name);
    }
  }
  assert.deepEqual(sold, { untagged: [[0.49, 10]], 'tagged, off': [[0.49, 10]], 'tagged, on': [] });

  // The quota floor (PACER_FLOOR=riding, the take-profit riding its best): untagged it arms at the need and sells under it;
  // a plan position gets neither.
  for (const plan of [false, true]) {
    const g = await setup({ env: { ...env, EXIT_POLICY: 'fair_value', ...(plan ? PLAN_ON : {}) } });
    await g.hold('bid', 0.4, 10);
    g.tag('yes');
    await g.yesAt(0.5);
    const floors = g.audit.tail(200, 'pacer').filter((r) => (r.data as { event: string }).event === 'floor');
    assert.equal(floors.length, plan ? 0 : 1, `plan ${plan}: ${g.notes()}`);
  }
});

test('decide() for a plan position (planHeld): no model exit, take-profit, profit mandate, quota snipe or floor, Mode B take-profit or curve rest sell', () => {
  const scfg: StrategyConfig = { ...loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), STRATEGY_CADENCE: 'continuous' }).strategy, style: 'maker', exitPolicy: 'fair_value', takerBuffer: 0.01, profitGiveBack: 0 };
  // Long 10 YES at 0.40 plus the 0.0175 entry fee; the model values it at 0.30, so the 0.50 bid pays more than the model's value.
  const long = (o: Partial<MarketView> = {}): MarketView => ({
    ticker: 'T', pYes: 0.3, bestBid: { price: 0.5, size: 50 }, bestAsk: { price: 0.6, size: 50 }, position: 10, entrySidePrice: 0.4, entryFeePerContract: 0.0175,
    bankroll: 200, maxOrderRiskUsd: 4, maxContracts: 10, minSidePrice: 0.1, tauSec: 400, noEntryBeforeCloseSec: 15,
    fastMove: false, tickSize: 0.01, fees: DEFAULT_FEES, nowSec: 1000, closeSec: 1400, ...o,
  });
  const exitsOf = (v: MarketView, c: StrategyConfig, o: Parameters<typeof decide>[2] = {}) => decide(v, c, o).place.filter((p) => p.purpose === 'exit' || p.why.startsWith('take-profit'));
  // The model exit (and the take-profit at PROFIT_GIVE_BACK 0) sells today; the plan position keeps it.
  assert.match(exitsOf(long(), scfg)[0].why, /^take-profit|^bid 0\.5 - fee > q/);
  assert.match(exitsOf(long(), { ...scfg, profitTarget: 0.5, profitTargetPct: 0 })[0].why, /^bid 0\.5 - fee > q 0\.300/);
  const held = decide(long(), scfg, { planHeld: true });
  assert.deepEqual(held.place.filter((p) => p.purpose === 'exit'), []);
  assert.ok(held.notes.includes('plan position: its own ratchet and end rule sell it; no other exit'));
  // The profit mandate and the quota snipe at the hour's need, and the quota floor.
  const pm = { exits: false, profitMandate: 0.01 };
  assert.match(exitsOf(long({ pYes: 0.7 }), scfg, pm)[0].why, /^profit mandate exit/);
  assert.deepEqual(exitsOf(long({ pYes: 0.7 }), scfg, { ...pm, planHeld: true }), []);
  assert.match(exitsOf(long({ pYes: 0.7 }), scfg, { exits: false, pacerUsd: 0.5 })[0].why, /^quota snipe: /);
  assert.deepEqual(exitsOf(long({ pYes: 0.7 }), scfg, { exits: false, pacerUsd: 0.5, planHeld: true }), []);
  // The quota floor: the model's sell price (0.70 plus the fee and the margin) aims higher, so the quota arms a floor; a profit
  // below an armed floor sells.
  const fl: StrategyConfig = { ...scfg, profitGiveBack: 0.33, pacer: { ...scfg.pacer!, floor: 'riding', floorTicks: 0 } };
  assert.equal(decide(long({ pYes: 0.7 }), fl, { pacerUsd: 0.5 }).pacerArm?.usd, 0.5, 'the quota floor arms today');
  assert.equal(decide(long({ pYes: 0.7 }), fl, { pacerUsd: 0.5, planHeld: true }).pacerArm, undefined);
  assert.match(exitsOf(long({ pYes: 0.7 }), fl, { pacerUsd: 0.5, pacerFloor: 0.75 })[0].why, /^quota snipe \(floor\)/);
  assert.deepEqual(exitsOf(long({ pYes: 0.7 }), fl, { pacerUsd: 0.5, pacerFloor: 0.75, planHeld: true }), []);
  // Mode B (EXIT_POLICY take_profit): the resting take-profit sell; the curve's resting sell (rest mode).
  const tp = { ...scfg, exitPolicy: 'take_profit' as const };
  assert.ok(decide(long({ pYes: 0.45 }), tp).place.some((p) => /^take-profit 0\.\d+$/.test(p.why)));
  assert.ok(!decide(long({ pYes: 0.45 }), tp, { planHeld: true }).place.some((p) => /^take-profit/.test(p.why)));
  const rest = long({ pYes: 0.7, bestBid: { price: 0.47, size: 50 }, curveRestSidePrice: 0.553 });
  assert.ok(decide(rest, scfg).place.some((p) => /^exit curve: rest/.test(p.why)));
  assert.ok(!decide(rest, scfg, { planHeld: true }).place.some((p) => /^exit curve/.test(p.why) || p.purpose === 'exit'));
  // Selective taking (STRATEGY_STYLE both), the model valuing YES at 0.80 against a 0.55 ask. Long YES: "take YES" adds to the
  // position as before, but not in the tick the plan's sale goes out (planSelling). Long NO: "take YES" would sell the plan's
  // NO at the model's call; a plan position never gets it, an untagged one still does.
  const tk: StrategyConfig = { ...scfg, style: 'both' };
  const takes = (v: MarketView, o: Parameters<typeof decide>[2]) => decide(v, tk, o).place.filter((p) => p.purpose === 'entry' && p.timeInForce === 'immediate_or_cancel').map((p) => p.why.replace(/:.*/, ''));
  const cheap = { pYes: 0.8, bestBid: { price: 0.5, size: 50 }, bestAsk: { price: 0.55, size: 50 } };
  assert.deepEqual(takes(long(cheap), { exits: false, planHeld: true }), ['take YES']);
  assert.deepEqual(takes(long(cheap), { exits: false, planHeld: true, planSelling: true }), []);
  const shortNo = long({ ...cheap, position: -10, entrySidePrice: 0.3 });
  assert.deepEqual(takes(shortNo, { exits: false }), ['take YES']);
  assert.deepEqual(takes(shortNo, { exits: false, planHeld: true }), []);
  // Long YES with the model valuing YES at 0.20 against a 0.50 bid: "take NO" would sell the plan's YES.
  const rich = long({ pYes: 0.2, bestBid: { price: 0.5, size: 50 }, bestAsk: { price: 0.55, size: 50 } });
  assert.deepEqual(takes(rich, { exits: false }), ['take NO']);
  assert.deepEqual(takes(rich, { exits: false, planHeld: true }), []);
});

test('PLAN_RULES on: the take-profit and the hunt\'s stop leave a plan position alone; an untagged one is managed as before', async () => {
  // A plan position at a 0.95 bid: armed, nothing sold (today's rules would be judging a sale here).
  const p = await setup({ env: { EXIT_POLICY: 'fair_value', ...PLAN_ON } });
  await p.hold('bid', 0.4, 10);
  p.tag('yes');
  await p.yesAt(0.95);
  assert.deepEqual(p.exits(), [], p.notes());
  assert.deepEqual(p.planEvents().map((e) => e.event), ['plan_ratchet_arm']);
  assert.doesNotMatch(p.notes(), /take-profit|quota floor/);
  // The hunt: activated with its stop locked at 0.47; a 0.46 bid sells an untagged position at the stop. A plan position (armed
  // at 0.50, floor 0.44) is held, and the hunt is dropped.
  for (const plan of [false, true]) {
    const g = await setup({ env: { EXIT_POLICY: 'confluence_ratchet', ...PLAN_ON } });
    await g.hold('bid', 0.4, 10);
    if (plan) g.tag('yes');
    await g.yesAt(0.5);
    const book = g.md.book(g.t);
    const hunt = new ConfluenceRatchetExit({ targetMargin: 0.02, minConfluence: 2, lockSale: 'off' });
    const on = hunt.update({ position: 10, qSide: 0.45, sideBid: 0.5, confluence: 3, book, now: Date.now(), tick: 0.01, fees: g.md.feesFor(g.t) });
    assert.deepEqual([on.mode, on.stop], ['hunt', 0.47]);
    const hunts = (g.engine as unknown as { hunts: Map<string, ConfluenceRatchetExit> }).hunts;
    hunts.set(g.t, hunt);
    await g.yesAt(0.46);
    if (plan) {
      assert.deepEqual(g.exits(), [], g.notes());
      assert.equal(hunts.has(g.t), false, 'a plan position is never hunted');
      assert.doesNotMatch(g.notes(), /hunting/);
    } else {
      assert.ok(g.whys().some((w) => w.startsWith('confluence ratchet stop')), g.whys().join(' | '));
    }
  }
});

test('PLAN_RULES on: the exit curve in gate mode never holds the plan\'s sale; an untagged take-profit is held as before', async () => {
  for (const plan of [false, true]) {
    const curveExit = new SinuousExitGate({ mode: 'gate', minNetProfit: 0.015 }, { minTrades: 20, t: 1, maxLossUsd: 25, window: 200 });
    const g = await setup({ env: { EXIT_POLICY: 'fair_value', ...PLAN_ON }, curveExit });
    await g.hold('bid', 0.4, 10);
    if (plan) g.tag('yes', { armC: 6, trailC: 4 });
    for (const b of [0.5, 0.56, 0.51]) await g.yesAt(b);
    if (plan) assert.deepEqual(g.exits().map((o) => [o.price, o.count]), [[0.49, 10]], g.notes());
    else {
      assert.deepEqual(g.exits(), [], 'the take-profit at 0.51 is held for the curve\'s signal');
      assert.match(g.notes(), /curve: holding the profit exit/);
    }
  }
});

test('PLAN_RULES on: the plan\'s ratchet state survives a restart; a fresh one would not have sold', async () => {
  const g = await setup({ env: PLAN_ON });
  await g.hold('bid', 0.4, 10);
  g.tag('yes');
  await g.yesAt(0.5);
  await g.yesAt(0.56);
  assert.equal(g.engine.planPositions.get(g.t)?.state.floor, 0.48);
  // A restart: a new engine on the same data folder and books.
  const again = new Engine(g.deps);
  assert.deepEqual([again.planPositions.get(g.t)?.state.armed, again.planPositions.get(g.t)?.state.floor, again.planPositions.get(g.t)?.state.peakBid], [true, 0.48, 0.56]);
  g.book(0.48, 0.5);
  await again.tick();
  assert.deepEqual(g.exits().map((o) => [o.side, o.price, o.count, o.filledCount]), [['ask', 0.46, 10, 10]], again.status.get(g.t)?.notes.join(' | '));
  // Without the saved state the same bid (+4.5c, under the 6c arm level) would only be watched.
  const h = await setup({ env: PLAN_ON });
  await h.hold('bid', 0.4, 10);
  h.tag('yes');
  await h.yesAt(0.48);
  assert.deepEqual(h.exits(), []);
});

test('PLAN_RULES on, end rule: 90 s before a 15-minute close a plan loser is sold, a winner rides; inside the final minute too', async () => {
  for (const [closeIn, bid, sold] of [[100_000, 0.38, false], [90_000, 0.38, true], [45_000, 0.38, true], [90_000, 0.46, false], [30_000, 0.46, false]] as const) {
    const g = await setup({ env: PLAN_ON, closeIn });
    assert.equal(g.cfg.strategy.noExitBeforeCloseSec, 60);
    await g.hold('bid', 0.4, 10);
    g.tag('yes');
    await g.yesAt(bid);
    const what = `${closeIn / 1000} s, bid ${bid}: ${g.notes()}`;
    if (sold) {
      assert.deepEqual(g.exits().map((o) => [o.side, o.price, o.count, o.filledCount]), [['ask', Math.round((bid - 0.02) * 100) / 100, 10, 10]], what);
      const e = g.planEvents().find((x) => x.event === 'plan_end_rule_sell')!;
      assert.ok(e && e.net! < 0 && e.limit === Math.round((bid - 0.02) * 100) / 100, what);
    } else {
      assert.deepEqual(g.exits(), [], what);
      assert.equal(g.oms.positions.position(g.t), 10);
    }
  }
  // An untagged loser at 45 s rides to settlement, as before (STRATEGY_NO_EXIT_BEFORE_CLOSE_SEC).
  const u = await setup({ env: { ...PLAN_ON, EXIT_POLICY: 'fair_value' }, closeIn: 45_000 });
  await u.hold('bid', 0.4, 10);
  await u.yesAt(0.38);
  assert.deepEqual(u.exits(), [], u.notes());
  assert.match(u.notes(), /final minute: riding to settlement/);
});

test('PLAN_RULES on, exit-only lane: during the volatility warm-up after a restart the ratchet arms, raises and sells; the end rule runs there too', async () => {
  const g = await setup({ env: PLAN_ON, historySec: 60 });
  assert.equal(g.md.index.get('BTC')!.vol(), undefined, 'volatility still warming up');
  await g.hold('bid', 0.4, 10);
  g.tag('yes');
  for (const b of [0.5, 0.56, 0.51]) await g.yesAt(b);
  assert.equal(g.engine.status.get(g.t)!.blocked, 'volatility warming up');
  assert.match(g.notes(), /^exit-only lane \(volatility warming up\): the plan position's ratchet and end rule only/);
  assert.deepEqual(g.exits(), []);
  await g.yesAt(0.48);
  assert.deepEqual(g.exits().map((o) => [o.side, o.price, o.count, o.filledCount]), [['ask', 0.46, 10, 10]], g.notes());
  assert.deepEqual(g.planEvents().map((e) => e.event), ['plan_ratchet_arm', 'plan_ratchet_raise', 'plan_ratchet_sell']);
  const d = g.audit.tail(50, 'decision').map((r) => r.data as { lane?: string; blocked?: string; place?: Array<{ why: string }> }).find((r) => r.lane === 'exit_only');
  assert.equal(d?.blocked, 'volatility warming up');
  assert.match(d!.place![0].why, /^plan ratchet: /);
  // The end rule in the lane: a loser 90 s before the close.
  const e = await setup({ env: PLAN_ON, historySec: 60, closeIn: 90_000 });
  await e.hold('bid', 0.4, 10);
  e.tag('yes');
  await e.yesAt(0.38);
  assert.equal(e.engine.status.get(e.t)!.blocked, 'volatility warming up');
  assert.deepEqual(e.exits().map((o) => [o.price, o.filledCount]), [[0.36, 10]], e.notes());
});

test('PLAN_RULES on: a sale that does not fill is retried each evaluation; at 3 failed tries an alert and the bid less 3 ticks', async () => {
  const g = await setup({ env: PLAN_ON });
  await g.hold('bid', 0.4, 10);
  g.tag('yes');
  await g.yesAt(0.5);
  await g.yesAt(0.56);
  // 0.48 with only 2 bid and nothing under it: the first try takes the 2.
  g.book(0.48, 0.5, 2);
  await g.engine.tick();
  assert.equal(g.oms.positions.position(g.t), 8);
  // The level stays taken: three tries fail; the third raises the alert, the next goes at 0.45.
  for (let i = 0; i < 3; i++) await g.engine.tick();
  assert.deepEqual(g.exits().map((o) => [o.price, o.filledCount]), [[0.46, 2], [0.46, 0], [0.46, 0], [0.45, 0]], g.notes());
  const alerts = g.audit.tail(50, 'alert').map((r) => r.data as { key: string; text: string });
  assert.deepEqual(alerts.map((a) => a.key), [`plan-sale-${g.t}`]);
  assert.match(alerts[0].text, /3 failed tries; now selling at the bid less 3 ticks/);
  // A bid at 0.45 appears: the escalated try sells the rest there.
  g.md.book(g.t).applySnapshot({ bids: [{ price: 0.48, size: 2 }, { price: 0.45, size: 50 }], asks: [{ price: 0.5, size: 50 }] }, Date.now());
  await g.engine.tick();
  assert.equal(g.oms.positions.position(g.t), 0, g.notes());
  assert.deepEqual(g.planEvents().filter((e) => e.event === 'plan_ratchet_retry').map((e) => [e.failedTries, e.limit]), [[1, 0.46], [2, 0.46], [3, 0.45], [4, 0.45]]);
});

test('PLAN_RULES on, kill switch: a plan loser is sold at the bid by the kill exit (E10, kept); a plan winner keeps its ratchet', async () => {
  const g = await setup({ env: PLAN_ON });
  await g.hold('bid', 0.4, 10);
  g.tag('yes');
  g.book(0.3, 0.32);
  await g.kill.engage('5 consecutive order errors (test)', 'oms');
  await g.engine.tick();
  assert.deepEqual(g.exits().map((o) => [o.price, o.count, o.filledCount]), [[0.3, 10, 10]]);
  assert.ok(g.audit.tail(200, 'decision').some((d) => (d.data as { leg?: string }).leg === 'kill_exit'));
  const w = await setup({ env: PLAN_ON });
  await w.hold('bid', 0.4, 10);
  w.tag('yes');
  await w.yesAt(0.5);
  await w.yesAt(0.56);
  await w.kill.engage('5 consecutive order errors (test)', 'oms');
  await w.yesAt(0.48);
  assert.deepEqual(w.exits().map((o) => [o.price, o.count, o.filledCount]), [[0.46, 10, 10]], w.notes());
  assert.deepEqual(w.exitRejects(), []);
});

test('PLAN_RULES on: an untagged position is managed exactly as with the switch off', async () => {
  const runs = [];
  for (const env of [{}, PLAN_ON]) {
    const g = await setup({ env });
    await g.hold('bid', 0.4, 10);
    runs.push({ steps: await takeProfitWalk(g), whys: g.whys().filter((w) => !w.startsWith('maker')), plan: g.planEvents().length });
  }
  assert.deepEqual(runs[1], runs[0]);
  assert.deepEqual(runs[1].steps[2], [['ask', 0.51, 10]]);
});

test('PLAN_RULES on, kill switch: the plan\'s sale goes out marked for the gateway at most once every 30 s, on the exit-only lane and in a full evaluation; a try held back is no failed try, and the audit says which tries went', async () => {
  for (const historySec of [60, 600]) {
    const clock = { t: Date.now() };
    const g = await setup({ env: PLAN_ON, historySec, clock });
    await g.hold('bid', 0.4, 10);
    g.tag('yes');
    await g.yesAt(0.5);
    await g.yesAt(0.56);
    await g.kill.engage('5 consecutive order errors (test)', 'oms');
    const t0 = clock.t;
    // 0.48 (the floor) with only 2 bid and nothing under it: the first try takes the 2.
    g.book(0.48, 0.5, 2);
    await g.engine.tick();
    const lane = historySec === 60;
    assert.equal(g.engine.status.get(g.t)!.blocked, lane ? 'volatility warming up' : undefined, g.notes());
    assert.deepEqual(g.exits().map((o) => [o.price, o.count, o.filledCount]), [[0.46, 10, 2]], g.notes());
    // Three evaluations inside the 30 s: no order; the try that left 8 open is one failed try, the others are held back.
    for (let i = 0; i < 3; i++) { g.advance(1000); g.book(0.48, 0.5, 2); await g.engine.tick(); }
    assert.equal(g.exits().length, 1);
    assert.match(g.notes(), /kill switch engaged: exit waits, one attempt per market every 30 s/);
    assert.equal(g.engine.planPositions.get(g.t)?.state.failedTries, 1);
    // 31 s after the first try: the next one goes, at the bid less 2 ticks (the level is still taken: it fills nothing).
    g.advance(28_000);
    g.book(0.48, 0.5, 2);
    await g.engine.tick();
    assert.deepEqual(g.exits().map((o) => [o.price, o.count, o.filledCount]), [[0.46, 10, 2], [0.46, 8, 0]], g.notes());
    // Never refused by the gateway ("kill switch engaged"), no alert: a try held back by the throttle is not a failure.
    assert.deepEqual(g.exitRejects(), []);
    assert.deepEqual(g.audit.tail(50, 'alert').map((r) => (r.data as { key: string }).key), []);
    assert.deepEqual([g.engine.planPositions.get(g.t)?.state.failedTries, g.engine.planPositions.get(g.t)?.state.selling?.tries], [1, 2]);
    // The audit: the first try (sent), the failed try's retry held back (sent false), the resend written once it went.
    const ev = g.planEvents().filter((e) => e.limit !== null).map((e) => [e.event, e.sent, e.resend ?? false, e.failedTries ?? 0, e.at - t0]);
    assert.deepEqual(ev, [['plan_ratchet_sell', true, false, 0, 0], ['plan_ratchet_retry', false, false, 1, 1000], ['plan_ratchet_retry', true, true, 1, 31_000]], `history ${historySec}`);
  }
});

test('PLAN_RULES on, kill switch: a plan loser inside the final minute is sold by the plan\'s end rule; an untagged one still rides', async () => {
  const g = await setup({ env: PLAN_ON, closeIn: 45_000 });
  await g.hold('bid', 0.4, 10);
  g.tag('yes');
  g.book(0.38, 0.4);
  await g.kill.engage('5 consecutive order errors (test)', 'oms');
  await g.engine.tick();
  assert.deepEqual(g.exits().map((o) => [o.price, o.count, o.filledCount]), [[0.36, 10, 10]], g.notes());
  assert.deepEqual(g.planEvents().map((e) => [e.event, e.sent]), [['plan_end_rule_sell', true]]);
  assert.deepEqual(g.exitRejects(), []);
  // Untagged (or PLAN_RULES off): the kill switch holds a loser in the final minute, as before.
  for (const env of [PLAN_ON, {}]) {
    const u = await setup({ env, closeIn: 45_000 });
    await u.hold('bid', 0.4, 10);
    if (env !== PLAN_ON) u.tag('yes');
    u.book(0.38, 0.4);
    await u.kill.engage('5 consecutive order errors (test)', 'oms');
    await u.engine.tick();
    assert.deepEqual(u.exits(), []);
    assert.equal(u.oms.positions.position(u.t), 10);
  }
});

test('PLAN_RULES on, taker style: no taker entry buys back the plan\'s sale in the same tick, and none sells the plan position ("take YES" while long NO)', async () => {
  // 10 YES at 0.80; the plan arms at 0.90, raises at 0.96 (floor 0.88) and sells at 0.88.
  const g = await setup({ env: { ...PLAN_ON, STRATEGY_STYLE: 'both', STRATEGY_CADENCE: 'continuous' } });
  await g.hold('bid', 0.8, 10);
  g.tag('yes');
  for (const b of [0.9, 0.96]) await g.yesAt(b);
  const before = g.oms.allOrders(500).length;
  await g.yesAt(0.88);
  const tick = g.oms.allOrders(500).slice(0, g.oms.allOrders(500).length - before).filter((o) => o.ticker === g.t && o.timeInForce === 'immediate_or_cancel');
  assert.deepEqual(tick.map((o) => [o.purpose, o.side, o.price, o.count, o.reduceOnly, o.filledCount]), [['exit', 'ask', 0.86, 10, true, 10]], g.notes());
  assert.equal(g.oms.positions.position(g.t), 0);
  // A taker entry against the plan's side: 10 NO at 0.40, the NO bid at 0.70 (armed, floor 0.62, held). The model values YES
  // near $1 (the index is above the strike, the volatility tiny), so it would take YES at the 0.30 ask: selling the NO.
  const n = await setup({ env: { ...PLAN_ON, STRATEGY_STYLE: 'both', STRATEGY_CADENCE: 'continuous' } });
  await n.hold('ask', 0.6, 10);
  n.tag('no');
  await n.noAt(0.7);
  assert.ok(!n.whys().some((w) => w.startsWith('take YES')), n.whys().join(' | '));
  assert.equal(n.oms.positions.position(n.t), -10, n.notes());
  assert.match(n.notes(), /plan ratchet armed: bid 0\.70, floor 0\.62/);
  // Untagged, the same book takes YES against the NO as before.
  const u = await setup({ env: { ...PLAN_ON, STRATEGY_STYLE: 'both', STRATEGY_CADENCE: 'continuous', EXIT_POLICY: 'hold' } });
  await u.hold('ask', 0.6, 10);
  await u.noAt(0.7);
  assert.ok(u.whys().some((w) => w.startsWith('take YES')), u.whys().join(' | '));
});

test('PLAN_RULES on: a plan sale the risk gateway refuses (here the order rate) is no failed try: it goes again as a resend, with no escalation and no alert', async () => {
  // One order a minute: the entry used it, so the gateway refuses the plan's sale.
  const g = await setup({ env: { ...PLAN_ON, RISK_MAX_ORDERS_PER_MIN: '1' } });
  await g.hold('bid', 0.4, 10);
  g.tag('yes');
  await g.yesAt(0.5);
  await g.yesAt(0.56);
  for (let i = 0; i < 4; i++) await g.yesAt(0.48);
  assert.deepEqual(g.exits(), []);
  assert.ok(g.audit.tail(50, 'risk_reject').some((r) => /order rate 1\/min at limit/.test(((r.data as { reasons: string[] }).reasons ?? []).join(' '))));
  const st = g.engine.planPositions.get(g.t)!.state;
  assert.deepEqual([st.failedTries, st.selling?.kind, st.selling?.tries], [0, 'ratchet', 0]);
  assert.deepEqual(g.audit.tail(50, 'alert'), []);
  // The decision is audited once, as not sent; the resends held back are not written.
  assert.deepEqual(g.planEvents().filter((e) => e.limit !== null).map((e) => [e.event, e.sent, e.limit]), [['plan_ratchet_sell', false, 0.46]]);
  assert.ok(g.whys().some((w) => /^plan ratchet sale, try 1 \(0 failed\); limit 0\.46 \(bid less 2 ticks\)$/.test(w)), g.whys().join(' | '));
});
