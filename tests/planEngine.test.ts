// PLAN_RULES in the engine (bot/engine.ts, paper and live alike): a position opened by a plan rule is sold by the plan's
// ratchet and end rule (bot/plan/planRatchet.ts) and by the hold exit (Steven, Nov 11 2026, 8:52 AM EST / 13:52 UTC); the
// pacer only reports pace for it; today's other exits leave it alone. Off (the default), every position is managed as
// before, tagged or not. The ratchet is the profit ratchet's, in dollars for the whole position (bot/strategy/profitRatchet.ts):
// 10 YES at 0.40 with the 1.7c taker entry fee nets +$1.45 at 0.58, +$1.56 at 0.59 (arms, stop +$1.06), +$1.86 at 0.62
// (stop +$1.36), +$1.35 at 0.57, +$2.17 at 0.65 (stop +$1.67), +$1.66 at 0.60.
import assert from 'node:assert/strict';
import fs from 'node:fs';
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

// The plan's own exits, the pacer reporting pace only on plan positions (pipeline decision 13, PACER_PLAN=off); PACER_PLAN's
// hybrid (the default since Steven's Nov 12 card) and need modes have their own test.
const PLAN_ON = { PLAN_RULES: 'true', PACER_PLAN: 'off' };

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
  // A clocked test drives the OMS's clock too, as one clock runs both in the bot: the in-flight exit guard compares an order's
  // send time with the evaluation's.
  const oms = new Oms({ gateway: paper, audit, statePath: path.join(dir, 'oms.json'), feesFor: (t) => md.feesFor(t), sleep: async () => undefined, ...(clock ? { now: () => clock.t } : {}) });
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
  const tag = (side: 'yes' | 'no', settings?: { armUsd?: number; stopMinUsd?: number; trailUsd?: number }) => engine.planPositions.tag({ ticker: t, side, ruleId: 'dummy-heat', ...(settings ? { settings } : {}) }, wall());
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

test('PLAN_RULES on: a tagged YES arms, raises its stop, is left alone by the take-profit, and sells the whole position at the bid less 2 ticks', async () => {
  const g = await setup({ env: PLAN_ON });
  await g.hold('bid', 0.4, 10);
  g.tag('yes');
  // 0.51 after 0.56: the take-profit would sell here (see the test above); the plan holds, not armed (+$0.75).
  for (const b of [0.5, 0.56, 0.51]) await g.yesAt(b);
  assert.deepEqual(g.exits(), [], g.notes());
  assert.match(g.notes(), /plan position: its own ratchet and end rule sell it, and the hold exit; no other exit/);
  // 0.58: +$1.45 after the 1.7c entry fee and the exit fee, under the $1.50 arm level.
  await g.yesAt(0.58);
  assert.equal(g.planEvents().length, 0, g.notes());
  // 0.59 arms (+$1.56: stop the best less $0.50, +$1.06, over the $1.00 minimum); 0.62 raises it to +$1.36; 0.58 holds.
  await g.yesAt(0.59);
  await g.yesAt(0.62);
  await g.yesAt(0.58);
  assert.deepEqual(g.exits(), [], g.notes());
  assert.match(g.notes(), /plan ratchet armed: bid 0\.58, net \+\$1\.45, stop \+\$1\.36, best \+\$1\.86/);
  // 0.57: +$1.35, at or under the stop. Sold: all 10, reduce-only, immediate-or-cancel, limit 0.55; it fills at the 0.57 bid.
  await g.yesAt(0.57);
  assert.deepEqual(g.exits().map((o) => [o.side, o.price, o.count, o.timeInForce, o.purpose, o.filledCount]), [['ask', 0.55, 10, 'immediate_or_cancel', 'exit', 10]], g.notes());
  assert.equal(g.oms.positions.position(g.t), 0);
  const ev = g.planEvents();
  assert.deepEqual(ev.map((e) => e.event), ['plan_ratchet_arm', 'plan_ratchet_raise', 'plan_ratchet_sell']);
  assert.deepEqual([ev[0].bid, ev[0].stop, ev[0].best, ev[0].feeFloor, ev[0].net, ev[0].side, ev[0].ruleId], [0.59, 1.06, 1.56, 0.44, 1.56, 'yes', 'dummy-heat']);
  assert.deepEqual([ev[1].prevStop, ev[1].stop, ev[1].best], [1.06, 1.36, 1.86]);
  assert.deepEqual([ev[2].bid, ev[2].stop, ev[2].net, ev[2].limit, ev[2].count], [0.57, 1.36, 1.35, 0.55, 10]);
  assert.ok(ev[2].net! >= 0, 'not below fees');
  assert.ok(ev.every((e) => typeof e.at === 'number' && e.ticker === g.t));
  assert.ok(g.whys().some((w) => /^plan ratchet: net \+\$1\.35 at bid 0\.57 at or under its stop \+\$1\.36 \(best \+\$1\.86\); limit 0\.55 \(bid less 2 ticks\)$/.test(w)), g.whys().join(' | '));
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
  for (const nb of [0.5, 0.56, 0.51, 0.59, 0.62, 0.58]) await g.noAt(nb);
  assert.deepEqual(g.exits(), [], g.notes());
  await g.noAt(0.57);
  assert.deepEqual(g.exits().map((o) => [o.side, o.price, o.count, o.filledCount]), [['bid', 0.45, 10, 10]], g.notes());
  assert.equal(g.oms.positions.position(g.t), 0);
  const ev = g.planEvents();
  assert.deepEqual(ev.map((e) => [e.event, e.side, e.bid, e.stop]), [['plan_ratchet_arm', 'no', 0.59, 1.06], ['plan_ratchet_raise', 'no', 0.62, 1.36], ['plan_ratchet_sell', 'no', 0.57, 1.36]]);
  assert.equal(ev[2].limit, 0.55);
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
      // The ratchet's own sale still credits the pace: arm at 0.59, raise at 0.65 (stop +$1.67), sell at 0.60 (+$1.66).
      for (const b of [0.59, 0.65, 0.6]) await g.yesAt(b);
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

test('PACER_PLAN (Steven, Nov 12 1:13 AM EST / 06:13 UTC): hybrid sells a plan position once its net covers the hour\'s need and the ratchet\'s $1.50, need at the need alone, off never; no floor in any mode', async () => {
  // The hour needs $0.50. 10 YES at 0.40: +$0.55 at a 0.49 bid, +$1.56 at 0.59 (where the ratchet arms, which sells nothing).
  const env = { PACER_HOURLY_USD: '0.5', PACER_MIN_TAKE_USD: '0.1', EXIT_POLICY: 'hold', PLAN_RULES: 'true' };
  const sold: Record<string, Array<[number, number]>> = {};
  const lines: Record<string, Array<number | undefined>> = {};
  for (const mode of ['hybrid', 'need', 'off'] as const) {
    const g = await setup({ env: { ...env, ...(mode === 'hybrid' ? {} : { PACER_PLAN: mode }) } });
    assert.equal(g.cfg.strategy.pacer.plan, mode, 'hybrid is the default');
    await g.hold('bid', 0.4, 10);
    g.tag('yes');
    lines[mode] = [];
    for (const b of [0.49, 0.59]) {
      if (g.oms.positions.position(g.t) === 0) break;
      await g.yesAt(b);
      lines[mode].push(g.engine.status.get(g.t)!.snipe?.atUsd);
    }
    sold[mode] = g.exits().map((o) => [o.price, o.count]);
    const pacer = g.audit.tail(200, 'pacer').map((r) => r.data as { event: string; ticker?: string; why?: string });
    assert.equal(pacer.filter((p) => p.event === 'floor').length, 0, `${mode}: no floor on a plan position`);
    if (mode !== 'off') assert.match(pacer.find((p) => p.event === 'snipe' && p.ticker === g.t)?.why ?? '', /^quota snipe: \+\$/, mode);
  }
  assert.deepEqual(sold, { hybrid: [[0.59, 10]], need: [[0.49, 10]], off: [] });
  // The badge's line: the need and the ratchet's arming net, whichever is higher; the need alone; none.
  assert.deepEqual(lines, { hybrid: [1.5, 1.5], need: [0.5], off: [undefined, undefined] });
  // The plan's own sale under way: no snipe beside it (decide's planSelling).
  const v: MarketView = {
    ticker: 'T', pYes: 0.7, bestBid: { price: 0.6, size: 50 }, bestAsk: { price: 0.62, size: 50 }, position: 10, entrySidePrice: 0.4, entryFeePerContract: 0.0175,
    bankroll: 200, maxOrderRiskUsd: 4, maxContracts: 10, minSidePrice: 0.1, tauSec: 400, noEntryBeforeCloseSec: 15, fastMove: false, tickSize: 0.01, fees: DEFAULT_FEES, nowSec: 1000, closeSec: 1400,
  };
  const scfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32) }).strategy;
  const exitsOf = (o: Parameters<typeof decide>[2]) => decide(v, scfg, o).place.filter((p) => p.purpose === 'exit').map((p) => p.why.slice(0, 13));
  assert.deepEqual(exitsOf({ exits: false, planHeld: true, planPacerUsd: 1.5 }), ['quota snipe: ']);
  assert.deepEqual(exitsOf({ exits: false, planHeld: true, planPacerUsd: 1.5, planSelling: true }), []);
  assert.deepEqual(exitsOf({ exits: false, planHeld: true, pacerUsd: 0.5 }), [], 'the plain pacer line never reaches a plan position');
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
  assert.ok(held.notes.includes('plan position: its own ratchet and end rule sell it, and the hold exit; no other exit'));
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
  // The hunt: activated with its stop locked at 0.47; a 0.46 bid sells an untagged position at the stop. A plan position (+$0.25
  // at 0.46, its ratchet not armed) is held, and the hunt is dropped.
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
    // A rule's own settings: arm at +$0.60, stop at least +$0.20, trail $0.40. 0.50 arms (+$0.65), 0.56 raises the stop to
    // +$0.85, 0.51 (+$0.75) sells at 0.49.
    if (plan) g.tag('yes', { armUsd: 0.6, stopMinUsd: 0.2, trailUsd: 0.4 });
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
  await g.yesAt(0.59);
  await g.yesAt(0.62);
  assert.equal(g.engine.planPositions.get(g.t)?.state.stop, 1.36);
  // A restart: a new engine on the same data folder and books.
  const again = new Engine(g.deps);
  assert.deepEqual([again.planPositions.get(g.t)?.state.armed, again.planPositions.get(g.t)?.state.stop, again.planPositions.get(g.t)?.state.best], [true, 1.36, 1.86]);
  g.book(0.57, 0.59);
  await again.tick();
  assert.deepEqual(g.exits().map((o) => [o.side, o.price, o.count, o.filledCount]), [['ask', 0.55, 10, 10]], again.status.get(g.t)?.notes.join(' | '));
  // Without the saved state the same bid (+$1.35, under the $1.50 arm level) would only be watched.
  const h = await setup({ env: PLAN_ON });
  await h.hold('bid', 0.4, 10);
  h.tag('yes');
  await h.yesAt(0.57);
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
  for (const b of [0.59, 0.62, 0.58]) await g.yesAt(b);
  assert.equal(g.engine.status.get(g.t)!.blocked, 'volatility warming up');
  assert.match(g.notes(), /^exit-only lane \(volatility warming up\): the plan position's ratchet and end rule only/);
  assert.deepEqual(g.exits(), []);
  await g.yesAt(0.57);
  assert.deepEqual(g.exits().map((o) => [o.side, o.price, o.count, o.filledCount]), [['ask', 0.55, 10, 10]], g.notes());
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
  await g.yesAt(0.59);
  await g.yesAt(0.62);
  // 0.57 with only 2 bid and nothing under it: the first try takes the 2.
  g.book(0.57, 0.59, 2);
  await g.engine.tick();
  assert.equal(g.oms.positions.position(g.t), 8);
  // The level stays taken: three tries fail; the third raises the alert, the next goes at 0.54.
  for (let i = 0; i < 3; i++) await g.engine.tick();
  assert.deepEqual(g.exits().map((o) => [o.price, o.filledCount]), [[0.55, 2], [0.55, 0], [0.55, 0], [0.54, 0]], g.notes());
  const alerts = g.audit.tail(50, 'alert').map((r) => r.data as { key: string; text: string });
  assert.deepEqual(alerts.map((a) => a.key), [`plan-sale-${g.t}`]);
  assert.match(alerts[0].text, /3 failed tries; now selling at the bid less 3 ticks/);
  // A bid at 0.54 appears: the escalated try sells the rest there.
  g.md.book(g.t).applySnapshot({ bids: [{ price: 0.57, size: 2 }, { price: 0.54, size: 50 }], asks: [{ price: 0.59, size: 50 }] }, Date.now());
  await g.engine.tick();
  assert.equal(g.oms.positions.position(g.t), 0, g.notes());
  assert.deepEqual(g.planEvents().filter((e) => e.event === 'plan_ratchet_retry').map((e) => [e.failedTries, e.limit]), [[1, 0.55], [2, 0.55], [3, 0.54], [4, 0.54]]);
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
  await w.yesAt(0.59);
  await w.yesAt(0.62);
  await w.kill.engage('5 consecutive order errors (test)', 'oms');
  await w.yesAt(0.57);
  assert.deepEqual(w.exits().map((o) => [o.price, o.count, o.filledCount]), [[0.55, 10, 10]], w.notes());
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
    await g.yesAt(0.59);
    await g.yesAt(0.62);
    await g.kill.engage('5 consecutive order errors (test)', 'oms');
    const t0 = clock.t;
    // 0.57 (+$1.35, under the +$1.36 stop) with only 2 bid and nothing under it: the first try takes the 2.
    g.book(0.57, 0.59, 2);
    await g.engine.tick();
    const lane = historySec === 60;
    assert.equal(g.engine.status.get(g.t)!.blocked, lane ? 'volatility warming up' : undefined, g.notes());
    assert.deepEqual(g.exits().map((o) => [o.price, o.count, o.filledCount]), [[0.55, 10, 2]], g.notes());
    // Three evaluations inside the 30 s: no order; the try that left 8 open is one failed try, the others are held back.
    for (let i = 0; i < 3; i++) { g.advance(1000); g.book(0.57, 0.59, 2); await g.engine.tick(); }
    assert.equal(g.exits().length, 1);
    assert.match(g.notes(), /kill switch engaged: exit waits, one attempt per market every 30 s/);
    assert.equal(g.engine.planPositions.get(g.t)?.state.failedTries, 1);
    // 31 s after the first try: the next one goes, at the bid less 2 ticks (the level is still taken: it fills nothing).
    g.advance(28_000);
    g.book(0.57, 0.59, 2);
    await g.engine.tick();
    assert.deepEqual(g.exits().map((o) => [o.price, o.count, o.filledCount]), [[0.55, 10, 2], [0.55, 8, 0]], g.notes());
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
  // 10 YES at 0.80, a rule's own settings (arm at +$0.80, stop at least +$0.50, trail $0.50): the plan arms at 0.90 (+$0.81),
  // raises at 0.96 (+$1.45, stop +$0.95) and sells at 0.88 (+$0.60).
  const g = await setup({ env: { ...PLAN_ON, STRATEGY_STYLE: 'both', STRATEGY_CADENCE: 'continuous' } });
  await g.hold('bid', 0.8, 10);
  g.tag('yes', { armUsd: 0.8, stopMinUsd: 0.5, trailUsd: 0.5 });
  for (const b of [0.9, 0.96]) await g.yesAt(b);
  const before = g.oms.allOrders(500).length;
  await g.yesAt(0.88);
  const tick = g.oms.allOrders(500).slice(0, g.oms.allOrders(500).length - before).filter((o) => o.ticker === g.t && o.timeInForce === 'immediate_or_cancel');
  assert.deepEqual(tick.map((o) => [o.purpose, o.side, o.price, o.count, o.reduceOnly, o.filledCount]), [['exit', 'ask', 0.86, 10, true, 10]], g.notes());
  assert.equal(g.oms.positions.position(g.t), 0);
  // A taker entry against the plan's side: 10 NO at 0.40, the NO bid at 0.70 (+$2.68: armed, stop +$2.18, held). The model values YES
  // near $1 (the index is above the strike, the volatility tiny), so it would take YES at the 0.30 ask: selling the NO.
  const n = await setup({ env: { ...PLAN_ON, STRATEGY_STYLE: 'both', STRATEGY_CADENCE: 'continuous' } });
  await n.hold('ask', 0.6, 10);
  n.tag('no');
  await n.noAt(0.7);
  assert.ok(!n.whys().some((w) => w.startsWith('take YES')), n.whys().join(' | '));
  assert.equal(n.oms.positions.position(n.t), -10, n.notes());
  assert.match(n.notes(), /plan ratchet armed: bid 0\.70, net \+\$2\.68, stop \+\$2\.18/);
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
  await g.yesAt(0.59);
  await g.yesAt(0.62);
  for (let i = 0; i < 4; i++) await g.yesAt(0.57);
  assert.deepEqual(g.exits(), []);
  assert.ok(g.audit.tail(50, 'risk_reject').some((r) => /order rate 1\/min at limit/.test(((r.data as { reasons: string[] }).reasons ?? []).join(' '))));
  const st = g.engine.planPositions.get(g.t)!.state;
  assert.deepEqual([st.failedTries, st.selling?.kind, st.selling?.tries], [0, 'ratchet', 0]);
  assert.deepEqual(g.audit.tail(50, 'alert'), []);
  // The decision is audited once, as not sent; the resends held back are not written.
  assert.deepEqual(g.planEvents().filter((e) => e.limit !== null).map((e) => [e.event, e.sent, e.limit]), [['plan_ratchet_sell', false, 0.55]]);
  assert.ok(g.whys().some((w) => /^plan ratchet sale, try 1 \(0 failed\); limit 0\.55 \(bid less 2 ticks\)$/.test(w)), g.whys().join(' | '));
});

test('PLAN_RULES on, hold exit (Steven, Nov 11 8:52 AM EST / 13:52 UTC): a plan position sitting at +$1.56 for 10 s is sold by the hold exit at the bid; a runner rides the same ratchet past it and is sold at its stop; paper and live alike', async () => {
  const live = (): Record<string, string> => {
    const key = path.join(tmpDir(), 'k.pem');
    fs.writeFileSync(key, 'x', { mode: 0o600 });
    return { TRADING_MODE: 'live', KALSHI_KEY_ID: 'id', KALSHI_PRIVATE_KEY_PATH: key, KALSHI_ENV: 'prod', LIVE_TRADING_ACKNOWLEDGED: 'I_ACCEPT_REAL_MONEY_RISK' };
  };
  for (const env of [PLAN_ON, { ...PLAN_ON, ...live() }]) {
    // The sitter: +$1.56 at 0.59 every second; the plan's ratchet arms (stop +$1.06) and sets no new best after the first.
    const clock = { t: Date.now() };
    const g = await setup({ env, clock });
    const mode = g.cfg.mode;
    await g.hold('bid', 0.4, 10);
    g.tag('yes');
    const at = async (b: number) => { g.advance(1000); await g.yesAt(b); };
    for (let i = 0; i < 10; i++) await at(0.59);
    assert.deepEqual(g.exits(), [], `${mode}: ${g.notes()}`);
    assert.deepEqual([g.engine.planPositions.get(g.t)?.state.armed, g.engine.planPositions.get(g.t)?.state.stop], [true, 1.06]);
    await at(0.59);
    // The hold exit's sale: the whole position at the bid (not the plan's bid less 2 ticks).
    assert.deepEqual(g.exits().map((o) => [o.side, o.price, o.count, o.filledCount]), [['ask', 0.59, 10, 10]], `${mode}: ${g.notes()}`);
    assert.ok(g.whys().includes('hold exit: +$1.56 net on 10 at bid 0.59, 10.0 s in all at +$1.50 or more, the last 10.0 s in a row at +$1.00 or more'), g.whys().join(' | '));
    const hx = g.audit.tail(50, 'pacer').map((r) => r.data as { event: string; ruleId?: string }).filter((d) => d.event === 'hold_exit');
    assert.deepEqual(hx.map((d) => d.ruleId), ['dummy-heat']);
    assert.deepEqual(g.planEvents().map((e) => e.event), ['plan_ratchet_arm'], 'the plan did not sell');
    assert.equal(g.engine.planPositions.get(g.t), undefined, 'flat: the tag cleared');

    // The runner: a new best every second from 0.59 to 0.70 (+$2.68, stop +$2.18): 11 s at +$1.50 or more, not sold.
    const clock2 = { t: Date.now() };
    const r = await setup({ env, clock: clock2 });
    await r.hold('bid', 0.4, 10);
    r.tag('yes');
    const at2 = async (b: number) => { r.advance(1000); await r.yesAt(b); };
    for (const b of [0.59, 0.6, 0.61, 0.62, 0.63, 0.64, 0.65, 0.66, 0.67, 0.68, 0.69, 0.7]) await at2(b);
    assert.deepEqual(r.exits(), [], `${mode}: ${r.notes()}`);
    assert.match(r.notes(), /but the profit set a new best in the last 3 s: it rides the profit ratchet/);
    assert.deepEqual([r.engine.planPositions.get(r.t)?.state.best, r.engine.planPositions.get(r.t)?.state.stop], [2.68, 2.18]);
    await at2(0.66);
    assert.deepEqual(r.exits(), [], r.notes());
    // 0.65: +$2.17, at or under the stop: the plan's sale at the bid less 2 ticks; it fills at the 0.65 bid.
    await at2(0.65);
    assert.deepEqual(r.exits().map((o) => [o.side, o.price, o.count, o.filledCount]), [['ask', 0.63, 10, 10]], `${mode}: ${r.notes()}`);
    assert.ok(r.whys().some((w) => w.startsWith('plan ratchet: net +$2.17 at bid 0.65 at or under its stop +$2.18 (best +$2.68)')), r.whys().join(' | '));
    assert.equal(r.audit.tail(50, 'pacer').filter((d) => (d.data as { event: string }).event === 'hold_exit').length, 0);
  }
});

test('PLAN_RULES on, HOLD_EXIT=false: a plan position sitting at +$1.56 is held; only the plan\'s ratchet and end rule sell it', async () => {
  const clock = { t: Date.now() };
  const g = await setup({ env: { ...PLAN_ON, HOLD_EXIT: 'false' }, clock });
  await g.hold('bid', 0.4, 10);
  g.tag('yes');
  for (let i = 0; i < 15; i++) { g.advance(1000); await g.yesAt(0.59); }
  assert.deepEqual(g.exits(), [], g.notes());
  assert.equal(g.engine.status.get(g.t)?.hold, undefined);
});

// ---- Review fixes (Nov 11): the in-flight guard on the plan's sale, the trade after a partial sale of a plan position ------

function liveEnv(): Record<string, string> {
  const key = path.join(tmpDir(), 'k.pem');
  fs.writeFileSync(key, 'x', { mode: 0o600 });
  return { TRADING_MODE: 'live', KALSHI_KEY_ID: 'id', KALSHI_PRIVATE_KEY_PATH: key, KALSHI_ENV: 'prod', LIVE_TRADING_ACKNOWLEDGED: 'I_ACCEPT_REAL_MONEY_RISK' };
}

test('PLAN_RULES on, in-flight exit guard: live, a plan sale whose fills are not booked yet is waited for: no new order, no failed try, no alert; booked, the rest goes again; never booked, it lets go at 2 s', async () => {
  type Fill = Parameters<Oms['onFill']>[0];
  const armed = async () => {
    const clock = { t: Date.now() };
    const g = await setup({ env: { ...PLAN_ON, ...liveEnv() }, clock });
    await g.hold('bid', 0.4, 10);
    g.tag('yes');
    // Live's order of events: the acknowledgement says what filled; the fills reach the books when the test books them.
    const queued: Fill[] = [];
    g.paper.removeAllListeners('fill');
    g.paper.on('fill', (f: Fill) => queued.push(f));
    const at = async (bid: number, bidSize = 50, ms = 1000) => { g.advance(ms); g.book(bid, Math.round((bid + 0.02) * 100) / 100, bidSize); await g.engine.tick(); };
    await at(0.59);
    await at(0.62);
    // 0.57 with 4 bid: the plan's sale (10 at 0.55) takes the 4; the books still hold 10.
    await at(0.57, 4);
    assert.deepEqual(g.exits().map((o) => [o.price, o.count, o.exchangeFillCount, o.filledCount]), [[0.55, 10, 4, 0]], g.notes());
    assert.equal(g.oms.positions.position(g.t), 10);
    const state = () => g.engine.planPositions.get(g.t)!.state;
    return { ...g, at, state, book: () => { for (const f of queued.splice(0)) g.oms.onFill(f); } };
  };
  const g = await armed();
  // A second later: the sale's fills are still on their way. Nothing is sent and no try has failed.
  await g.at(0.57, 4);
  assert.equal(g.exits().length, 1, g.notes());
  assert.ok(g.notes().includes('plan ratchet sale: an order is still working'), g.notes());
  assert.deepEqual([g.state().failedTries, g.state().selling?.tries], [0, 1]);
  // Booked: 6 left. The try left the position open: one failed try, and the 6 go again at the bid less 2 ticks.
  g.book();
  assert.equal(g.oms.positions.position(g.t), 6);
  await g.at(0.57, 4, 500);
  assert.deepEqual(g.exits().map((o) => [o.price, o.count]), [[0.55, 10], [0.55, 6]], g.notes());
  assert.equal(g.state().failedTries, 1);
  assert.deepEqual(g.planEvents().filter((e) => e.event === 'plan_ratchet_retry').map((e) => [e.failedTries, e.count, e.resend ?? false]), [[1, 6, false]]);
  assert.equal(g.audit.tail(50, 'alert').length, 0);
  // Fills never booked (lost): the guard lets go 2 s after the sale was sent, whatever its state.
  const h = await armed();
  await h.at(0.57, 4);
  await h.at(0.57, 4, 500);
  assert.deepEqual([h.exits().length, h.state().failedTries], [1, 0], '1.5 s after it: still waited for');
  await h.at(0.57, 4, 500);
  assert.deepEqual(h.exits().map((o) => o.count), [10, 10], h.notes());
});

test('PLAN_RULES on, after a partial sale of a plan position: the hold exit and the plan\'s ratchet measure the trade (banked plus the rest); the rest is sold by the hold exit at 10 s, not on a fake drop; paper and live alike', async () => {
  for (const env of [PLAN_ON, { ...PLAN_ON, ...liveEnv() }]) {
    const clock = { t: Date.now() };
    const g = await setup({ env, clock });
    const mode = g.cfg.mode;
    await g.hold('bid', 0.4, 10);
    g.tag('yes');
    const at = async (b: number) => { g.advance(1000); await g.yesAt(b); };
    // +$1.56 at 0.59: the plan's ratchet arms (stop +$1.06); 5 s at +$1.50 or more.
    for (let i = 0; i < 6; i++) await at(0.59);
    assert.deepEqual([g.engine.planPositions.get(g.t)?.state.stop, g.engine.status.get(g.t)?.hold?.cumSec], [1.06, 5], g.notes());
    // 6 of the 10 sold at 0.59 bank +$0.93: the 4 left net +$0.62 at that bid, under the plan's stop and under the hold
    // exit's levels; the trade is +$1.55.
    await g.oms.submit({ ticker: g.t, asset: 'BTC', windowCloseTs: g.market.closeTime, side: 'ask', price: 0.59, count: 6, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: true, purpose: 'exit', fairValue: 0.5, modelId: 'm', decisionId: 'part' });
    assert.equal(g.oms.positions.position(g.t), 4);
    // 0.60: the trade +$1.59 sets a new best (the stop rises to +$1.09), its event carrying what was banked.
    await at(0.6);
    const raise = g.planEvents().filter((e) => e.event === 'plan_ratchet_raise');
    assert.deepEqual(raise.map((e) => [e.count, e.banked, e.stop, e.best]), [[4, 0.928, 1.09, 1.59]], `${mode}: ${g.notes()}`);
    for (let i = 0; i < 3; i++) await at(0.59);
    assert.equal(g.exits().length, 1, `${mode}: only the sale by hand: ${g.notes()}`);
    assert.equal(g.engine.status.get(g.t)?.hold?.cumSec, 9);
    // 10 s in all at +$1.50 or more on the trade: the hold exit sells the 4 at the bid.
    await at(0.59);
    assert.deepEqual(g.exits().map((o) => [o.side, o.price, o.count, o.filledCount]), [['ask', 0.59, 6, 6], ['ask', 0.59, 4, 4]], `${mode}: ${g.notes()}`);
    assert.ok(g.whys().includes('hold exit: +$1.55 net (+$0.93 banked by partial sales) on 4 at bid 0.59, 10.0 s in all at +$1.50 or more, the last 10.0 s in a row at +$1.00 or more'), g.whys().join(' | '));
    assert.deepEqual(g.planEvents().map((e) => e.event), ['plan_ratchet_arm', 'plan_ratchet_raise'], 'the plan did not sell');
  }
});
