// The heat entry lane inside the engine (bot/engine.ts heatTick, docs/HEAT_LANE.md): an engine on the paper exchange, as
// tests/engine.test.ts builds one, with a heat lane and an in-memory curve source. A fake tag hook stands for the plan
// positions (the exits' owner) where a test wants entries to go out.
import assert from 'node:assert/strict';
import path from 'path';
import { test } from 'node:test';
import { Alerter } from '../bot/alerts/alerter';
import { ConfigError, heatStartCheck, loadConfig } from '../bot/config';
import { Engine } from '../bot/engine';
import { HeatLane } from '../bot/heat/heatLane';
import { MemoryHeatSource } from '../bot/heat/heatSource';
import type { HeatCallRow, HeatHooks, HeatSnapshot, HeatTag } from '../bot/heat/types';
import type { KalshiRest } from '../bot/kalshi/rest';
import type { MarketInfo } from '../bot/kalshi/types';
import { MarketData, Recorder } from '../bot/marketdata/marketData';
import { MetaModel } from '../bot/model/metaModel';
import { Oms } from '../bot/oms/oms';
import { PaperExchange } from '../bot/paper/paperExchange';
import { KillSwitch } from '../bot/risk/killSwitch';
import { RiskGateway } from '../bot/risk/riskGateway';
import { Reconciler } from '../bot/recon/reconciler';
import type { OrderPlan } from '../bot/strategy/fairValueStrategy';
import { openExchange, tmpAudit, tmpDir } from './helpers';

const TOKEN = 'x'.repeat(40);

/** An engine with one BTC 15-minute market ten minutes from its close, quoted 45c / 60c, and a heat lane on. */
async function setup(opts: { env?: Record<string, string>; hooks?: HeatHooks; tagged?: HeatTag[]; untagged?: string[]; plan?: boolean } = {}) {
  const dir = tmpDir();
  const cfg = loadConfig({ DASHBOARD_TOKEN: TOKEN, DATA_DIR: dir, RISK_DAILY_LOSS_USD: '10', DOMINANCE_FEED: 'false', SPOT_FEED: 'false', STRATEGY_SERIES: 'KXBTC15M', SESSION_EDGE_NO_ENTRY: 'false', TENNIS_ENABLED: 'false', HEAT_LANE: 'true', ...opts.env });
  const now = Date.now();
  const market: MarketInfo = { ticker: 'KXBTC15M-HEAT', seriesTicker: 'KXBTC15M', status: 'open', openTime: now - 300_000, closeTime: now + 600_000, floorStrike: 60000, tickSize: 0.01 };
  const rest = { getSeriesFees: async () => ({ feeType: 'quadratic', multiplier: 1 }), getOpenMarkets: async () => [market], getMarket: async () => market } as unknown as KalshiRest;
  const audit = tmpAudit();
  const md = new MarketData(cfg, rest, undefined, new Recorder(path.join(dir, 'rec')));
  await md.refreshCatalog(now);
  md.book(market.ticker).applySnapshot({ bids: [{ price: 0.45, size: 50 }], asks: [{ price: 0.6, size: 50 }] }, now);
  const idx = md.index.get('BTC')!;
  let seed = 1;
  const rand = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
  let x = Math.log(60010);
  for (let s = 600; s >= 0; s--) { x += 0.0002 * (rand() - 0.5); idx.add(Math.exp(x), now - s * 1000); }
  const paper = new PaperExchange(undefined, 200, (t) => md.books.get(t), () => ({ takerMultiplier: 1, makerMultiplier: 0 }));
  const kill = new KillSwitch(path.join(dir, 'kill.json'), audit);
  const oms = new Oms({ gateway: paper, audit, statePath: path.join(dir, 'oms.json'), feesFor: (t) => md.feesFor(t), sleep: async () => undefined });
  kill.bindCancelAll((r) => oms.cancelAll(r));
  paper.on('fill', (f) => oms.onFill(f));
  paper.on('order', (o) => oms.onExchangeOrder(o));
  const recon = new Reconciler({ gateway: paper, oms, audit, getMarket: rest.getMarket, onPersistentBreak: (r) => void kill.engage(r, 'recon') });
  const lane = new HeatLane(cfg.heat);
  const source = new MemoryHeatSource();
  const tagged = opts.tagged ?? [], untagged = opts.untagged ?? [];
  // `plan`: the hooks bot/main.ts gives the engine with PLAN_RULES on (the plan positions own the entries).
  const hooks: HeatHooks = opts.hooks ?? (opts.plan
    ? { tag: (t, at) => { engine.planPositions.tag(t, at); tagged.push(t); }, untag: (t) => { engine.planPositions.forget(t); untagged.push(t); } }
    : { tag: (t) => { tagged.push(t); }, untag: (t) => { untagged.push(t); } });
  const engine = new Engine({ cfg, audit, alerter: new Alerter([], audit), md, gateway: paper, oms, risk: new RiskGateway(cfg.risk), kill, recon, model: MetaModel.identity(), exchangeStatus: openExchange(), heat: { lane, source, ...hooks } });
  engine.balance = (await recon.run('startup'))!.balance;
  return { cfg, md, paper, oms, kill, engine, market, audit, lane, source, tagged, untagged };
}

/** BTC's hottest 15-minute row fired UP at the minute that closed five seconds ago. */
function fired(o: Partial<HeatCallRow> = {}): HeatSnapshot {
  const now = Date.now();
  const barClose = now - 5_000;
  const row: HeatCallRow = { key: '1m:RSI14=very low', kind: 'single', tf: 1, h: 15, dir: 1, rank: 1, of: 40, heat: 100, share: 0.53, odds: 3, barClose, ...o };
  return { source: 'oracle-heat', run: 'R1', packSha: 'pack', writtenAt: now - 3_000, coins: new Map([['BTC', { asOf: barClose, tableSha: 'table', ok: true, calls: [row] }]]) };
}

type Row = Record<string, any>;
const rows = (audit: ReturnType<typeof tmpAudit>, kind: 'heat' | 'decision') => audit.tail(500, kind).map((r) => r.data as Row);
const heatOrders = (oms: Oms) => oms.allOrders(100).filter((o) => o.modelId.startsWith('heat:'));

test('a fired call buys the called side with an immediate-or-cancel at the touch, through placeChecked, tagged first', async () => {
  const g = await setup();
  g.source.set(fired());
  await g.engine.tick();
  const [o] = heatOrders(g.oms);
  assert.ok(o, `no heat order: ${JSON.stringify(rows(g.audit, 'heat'))}`);
  assert.deepEqual([o.ticker, o.side, o.price, o.timeInForce, o.postOnly, o.reduceOnly, o.purpose, o.modelId], [g.market.ticker, 'bid', 0.6, 'immediate_or_cancel', false, false, 'entry', 'heat:R1']);
  // The flat phase: ORDER_USD_MIN ($10) in whole contracts at 60c.
  assert.equal(o.count, 16);
  assert.equal(g.oms.positions.position(g.market.ticker), 16, 'filled against the paper book');
  assert.equal(o.fairValue, 0.555, 'YES mid 0.525 moved 3 points toward the called side');
  assert.deepEqual(g.tagged.map((t) => [t.ticker, t.side, t.ruleId]), [[g.market.ticker, 'yes', 'heat:R1:BTC:h15:1m:RSI14=very low']]);
  assert.ok(g.lane.holds(g.market.ticker));
  // The decision record and the call's row.
  const dec = rows(g.audit, 'decision').find((d) => d.lane === 'heat')!;
  assert.equal(dec.decisionId, o.decisionId);
  assert.deepEqual([dec.heat.asset, dec.heat.h, dec.heat.key, dec.heat.slot, dec.heat.stake, dec.heat.count, dec.heat.run, dec.heat.packSha], ['BTC', 15, '1m:RSI14=very low', 1, 10, 16, 'R1', 'pack']);
  const call = rows(g.audit, 'heat').find((r) => r.key === '1m:RSI14=very low')!;
  assert.deepEqual([call.asset, call.h, call.dir, call.rank, call.fired, call.against, call.context, call.entry], ['BTC', 15, 1, 1, 1, 0, 'none', 'sent']);
  assert.equal(call.plan.ticker, g.market.ticker);
  // The engine ticks every second: the call is acted on once.
  await g.engine.tick();
  assert.equal(heatOrders(g.oms).length, 1);
  assert.equal(rows(g.audit, 'heat').filter((r) => r.key).length, 1, 'one row per call');
  // The lane shows in the status JSON.
  const st = g.engine.guardStatus().heat!;
  assert.deepEqual([st.enabled, st.exitOwner, st.source.ok, st.open.length], [true, true, true, 1]);
});

test('with the plan exits on (PLAN_RULES), a heat fill is a plan position and no other order goes on its market', async () => {
  // The loser cut off: the fixture's 15c spread would keep the lane out (see the loser-cut test below).
  const g = await setup({ env: { PLAN_RULES: 'true', PLAN_LOSER_CUT_C: '0' }, plan: true });
  heatStartCheck(g.cfg, g.cfg.plan.enabled);
  g.source.set(fired());
  await g.engine.tick();
  assert.equal(g.oms.positions.position(g.market.ticker), 16);
  const p = g.engine.planPositions.get(g.market.ticker)!;
  assert.deepEqual([p.side, p.ruleId], ['yes', 'heat:R1:BTC:h15:1m:RSI14=very low']);
  // The old lane's quote from this first tick was pulled before the entry, unfilled.
  const before = g.oms.allOrders(100).filter((o) => o.ticker === g.market.ticker && !o.modelId.startsWith('heat:'));
  assert.ok(before.every((o) => o.state === 'CANCELED' && o.filledCount === 0), JSON.stringify(before.map((o) => [o.purpose, o.state])));
  const seen = new Set(before.map((o) => o.clientOrderId));
  const newOthers = () => g.oms.allOrders(100).filter((o) => o.ticker === g.market.ticker && !o.modelId.startsWith('heat:') && !seen.has(o.clientOrderId));
  for (let i = 0; i < 5; i++) await g.engine.tick();
  assert.deepEqual(newOthers().map((o) => [o.side, o.purpose, o.price, o.count]), [], 'no old-lane order on the heat market');
  assert.ok(g.engine.planPositions.get(g.market.ticker)?.seenOpen, 'the plan positions saw it open');
  // The plan's ratchet arms at +$1.50 net: the bid moves to 75c (16 x 15c = $2.40 before fees), and the plan owns the exit.
  g.md.book(g.market.ticker).applySnapshot({ bids: [{ price: 0.75, size: 50 }], asks: [{ price: 0.8, size: 50 }] }, Date.now());
  await g.engine.tick();
  assert.equal(g.engine.planPositions.get(g.market.ticker)?.state.armed, true);
  assert.deepEqual(newOthers().filter((o) => o.purpose !== 'exit').map((o) => [o.side, o.purpose, o.price, o.count]), [], 'only the plan\'s exits may go on it');
});

test('the loser cut (PLAN_LOSER_CUT_C 10c, Steven Nov 11 6:56 PM EST / 23:56 UTC) sells a heat position 10c under its entry; a fresh call enters the contract again', async () => {
  // The flat cut (the same 10c at every point of the window); the cut by time is the next test.
  const g = await setup({ env: { PLAN_RULES: 'true', HEAT_COOLDOWN_SEC: '0', PLAN_LOSER_CUT_OPEN_C: '10', PLAN_LOSER_CUT_LATE_C: '10' }, plan: true });
  // The fixture's 15c spread: bought at the ask, the bid is already 15c under, so the lane stays out.
  g.source.set(fired());
  await g.engine.tick();
  assert.equal(heatOrders(g.oms).length, 0);
  assert.match(rows(g.audit, 'heat').find((r) => r.key)!.skip, /the spread \(15c\) is at or above the loser cut \(10c, PLAN_LOSER_CUT_C\): the cut would sell the position at once/);
  // A 1c spread: 16 YES at 60c.
  g.md.book(g.market.ticker).applySnapshot({ bids: [{ price: 0.59, size: 50 }], asks: [{ price: 0.6, size: 50 }] }, Date.now());
  g.source.set(fired());
  await g.engine.tick();
  assert.equal(g.oms.positions.position(g.market.ticker), 16, JSON.stringify(rows(g.audit, 'heat').filter((r) => r.key)));
  await g.engine.tick();
  // The bid 9c under: held. 11c under: sold at the bid less 2 ticks.
  g.md.book(g.market.ticker).applySnapshot({ bids: [{ price: 0.51, size: 50 }], asks: [{ price: 0.52, size: 50 }] }, Date.now());
  await g.engine.tick();
  assert.equal(g.oms.positions.position(g.market.ticker), 16);
  g.md.book(g.market.ticker).applySnapshot({ bids: [{ price: 0.49, size: 50 }], asks: [{ price: 0.5, size: 50 }] }, Date.now());
  await g.engine.tick();
  const cut = g.audit.tail(500, 'plan').map((r) => r.data as Row).filter((e) => e.event === 'plan_loser_cut_sell');
  assert.deepEqual(cut.map((e) => [e.bid, e.entry, e.loserCut, e.limit, e.sent]), [[0.49, 0.6, 0.1, 0.47, true]]);
  assert.equal(g.oms.positions.position(g.market.ticker), 0, 'sold');
  await g.engine.tick();
  assert.deepEqual([g.lane.status(Date.now()).trips, g.lane.status(Date.now()).wins], [1, 0]);
  assert.ok(g.lane.status(Date.now()).pnl < 0);
  // A call whose bar closed before the cut is the TA that lost: not a reason to go back in.
  g.source.set(fired());
  await g.engine.tick();
  assert.match(rows(g.audit, 'heat').filter((r) => r.key).at(-1)!.skip, /bar closed before the lane's last loss in this window/);
  // A call made after it (here DOWN): the other side, through the same checks.
  await new Promise((r) => setTimeout(r, 5));
  g.source.set(fired({ barClose: Date.now(), dir: -1 }));
  await g.engine.tick();
  // Bought NO: YES sold at the 49c bid, 19 contracts for the $10 stake.
  assert.deepEqual(heatOrders(g.oms).map((o) => [o.side, o.price, o.count, o.purpose]).sort(), [['ask', 0.49, 19, 'entry'], ['bid', 0.6, 16, 'entry']]);
  assert.equal(g.oms.positions.position(g.market.ticker), -19, 'holds 19 NO');
});

test('the cut by time (Steven, Nov 12 1:01 AM EST / 06:01 UTC): a third of the window gone, the cut is 14.4c; the spread guard and the dashboard read the same line', async () => {
  // The fixture's window: opened 5 minutes ago, 10 minutes to the close (a third gone): 20c - 10c x (1/3) / 0.6 = 14.4c.
  const g = await setup({ env: { PLAN_RULES: 'true' }, plan: true });
  g.source.set(fired());
  await g.engine.tick();
  assert.match(rows(g.audit, 'heat').find((r) => r.key)!.skip, /the spread \(15c\) is at or above the loser cut \(14\.4c now, 33% of the window gone\)/);
  g.md.book(g.market.ticker).applySnapshot({ bids: [{ price: 0.59, size: 50 }], asks: [{ price: 0.6, size: 50 }] }, Date.now());
  g.source.set(fired());
  await g.engine.tick();
  assert.equal(g.oms.positions.position(g.market.ticker), 16);
  await g.engine.tick();
  const plan = (g.engine.status.get(g.market.ticker) as unknown as { plan?: { cutAt?: number; armUsd?: number } }).plan;
  assert.equal(plan?.armUsd, 1.5);
  assert.ok(Math.abs(plan!.cutAt! - 0.4556) < 0.0005, `the dashboard: the bid the cut sells at now (${plan?.cutAt})`);
  // 11c under the entry: held (the flat 10c cut would have sold it). 15c under: sold.
  g.md.book(g.market.ticker).applySnapshot({ bids: [{ price: 0.49, size: 50 }], asks: [{ price: 0.5, size: 50 }] }, Date.now());
  await g.engine.tick();
  assert.equal(g.oms.positions.position(g.market.ticker), 16, 'held at 11c under');
  g.md.book(g.market.ticker).applySnapshot({ bids: [{ price: 0.45, size: 50 }], asks: [{ price: 0.46, size: 50 }] }, Date.now());
  await g.engine.tick();
  const cut = g.audit.tail(500, 'plan').map((r) => r.data as Row).filter((e) => e.event === 'plan_loser_cut_sell');
  assert.equal(cut.length, 1);
  assert.deepEqual([cut[0].bid, cut[0].entry, cut[0].loserCut, cut[0].loserCutOpen, cut[0].loserCutLate, cut[0].sent], [0.45, 0.6, 0.1, 0.2, 0.03, true]);
  assert.ok(Math.abs((cut[0].cutAt as number) - 0.1444) < 0.0005, String(cut[0].cutAt));
  assert.ok(Math.abs((cut[0].elapsed as number) - 1 / 3) < 0.01, String(cut[0].elapsed));
  assert.equal(g.oms.positions.position(g.market.ticker), 0, 'sold');
});

test('no tag hook wired: no entry, and the call is recorded with the reason', async () => {
  const g = await setup({ hooks: {} });
  g.source.set(fired());
  await g.engine.tick();
  assert.equal(heatOrders(g.oms).length, 0);
  assert.equal(g.oms.positions.position(g.market.ticker), 0);
  const call = rows(g.audit, 'heat').find((r) => r.key)!;
  assert.equal(call.skip, 'no exit owner');
  assert.equal(g.engine.guardStatus().heat!.exitOwner, false);
});

test('a halt or the entry gate stops it: every call becomes a skip with that reason', async () => {
  const gate = await setup({ hooks: { tag: () => undefined, entryGate: () => 'soft pause (test)' } });
  gate.source.set(fired());
  await gate.engine.tick();
  assert.equal(heatOrders(gate.oms).length, 0);
  assert.equal(rows(gate.audit, 'heat').find((r) => r.key)!.skip, 'soft pause (test)');
  // The engine's own guards on new risk, the list the risk gateway gets: here the dashboard's STOP.
  const halted = await setup();
  (halted.engine as unknown as { d: { control: { active: boolean } } }).d.control = { active: false };
  halted.source.set(fired());
  await halted.engine.tick();
  assert.equal(heatOrders(halted.oms).length, 0);
  assert.match(rows(halted.audit, 'heat').find((r) => r.key)!.skip, /stopped from the dashboard/);
  assert.deepEqual(halted.tagged, [], 'nothing tagged');
});

test('the risk gateway refuses the entry: the lane lets go of the ticker and the tag comes off at once', async () => {
  // HEAT_FEE_NET_CHECK on: the edge collar judges the heat value (YES mid 52.5c + 3 points) against a 60c ask, and refuses.
  const g = await setup({ env: { HEAT_FEE_NET_CHECK: 'true' } });
  g.source.set(fired());
  await g.engine.tick();
  assert.equal(heatOrders(g.oms).length, 0);
  assert.match(JSON.stringify(g.audit.tail(50, 'risk_reject').map((r) => r.data)), /no fee-net edge/);
  assert.equal(g.tagged.length, 1, 'tagged before the order');
  assert.deepEqual(g.untagged, [g.market.ticker]);
  assert.equal(g.lane.holds(g.market.ticker), false);
  assert.match(rows(g.audit, 'heat').find((r) => r.key)!.entry, /refused before it went out/);
});

test('our own resting orders on the market are cancelled before the entry goes out', async () => {
  const g = await setup();
  // The old lane quotes the flat market first: a YES bid above the 45c bid, which a DOWN call's sale of YES there crosses.
  await g.engine.tick();
  const quotes = g.oms.liveOrders().filter((o) => o.ticker === g.market.ticker && o.purpose === 'quote');
  assert.ok(quotes.some((q) => q.side === 'bid' && q.price >= 0.45), `old-lane quotes: ${JSON.stringify(quotes.map((q) => [q.side, q.price]))}`);
  g.source.set(fired({ dir: -1 }));
  await g.engine.tick();
  const [o] = heatOrders(g.oms);
  assert.deepEqual([o.side, o.price, o.count], ['ask', 0.45, 18], 'NO bought by selling YES at the bid: $10 at 55c a contract');
  assert.equal(g.oms.positions.position(g.market.ticker), -18);
  for (const q of quotes) assert.ok(g.oms.get(q.clientOrderId)!.cancelRequested || g.oms.get(q.clientOrderId)!.state === 'CANCELED', `${q.side} ${q.price} still resting`);
  // In the audit the cancels come before the entry.
  const all = g.audit.tail(500);
  const entrySeq = all.find((r) => r.kind === 'order_new' && (r.data as Row).clientOrderId === o.clientOrderId)!.seq;
  for (const q of quotes) {
    const c = all.find((r) => r.kind === 'order_cancel_req' && (r.data as Row).clientOrderId === q.clientOrderId);
    assert.ok(c && c.seq < entrySeq, 'cancelled first');
  }
  assert.deepEqual(rows(g.audit, 'decision').find((d) => d.lane === 'heat')!.cancel.map((c: Row) => c.clientOrderId).sort(), quotes.map((q) => q.clientOrderId).sort());
});

test('a heat-held market gets no old-lane quotes', async () => {
  // Every tick a full evaluation, so the old lane has its chance to quote each time.
  const g = await setup({ env: { STRATEGY_CADENCE: 'continuous' } });
  g.source.set(fired());
  await g.engine.tick();
  assert.equal(g.oms.positions.position(g.market.ticker), 16);
  for (let i = 0; i < 3; i++) await g.engine.tick();
  const quotes = g.oms.liveOrders().filter((o) => o.ticker === g.market.ticker && o.purpose === 'quote');
  assert.deepEqual(quotes.map((q) => [q.side, q.price]), []);
  // The same market and position without the lane's hold: the old lane quotes it again.
  g.lane.holds = () => false;
  await g.engine.tick();
  assert.ok(g.oms.liveOrders().some((o) => o.ticker === g.market.ticker && o.purpose === 'quote'), 'the control quotes');
});

test('placeChecked refuses any other order that adds risk on a heat-held market, whichever evaluation built it', async () => {
  // A decide() call that misses the entries flag hands placeChecked old-lane orders like these (the plan exits' branch calls
  // decide() for a plan-held position, and a filled heat position is one): the heat position must not be added to.
  const g = await setup();
  g.source.set(fired());
  await g.engine.tick();
  assert.equal(g.oms.positions.position(g.market.ticker), 16);
  const m = g.md.markets.get(g.market.ticker)!;
  const place = (p: Partial<OrderPlan>, id: string): Promise<unknown> => (g.engine as any).placeChecked(m, {
    side: 'bid', price: 0.55, count: 5, timeInForce: 'good_till_canceled', postOnly: true, reduceOnly: false, purpose: 'quote', edge: 0.1, why: 'maker bid', ...p,
  }, 0.7, id);
  const sent = (id: string) => g.oms.allOrders(100).filter((o) => o.decisionId === id);
  await place({}, 'd-quote');
  await place({ price: 0.6, timeInForce: 'immediate_or_cancel', postOnly: false, purpose: 'entry', why: 'taker entry' }, 'd-entry');
  assert.deepEqual([...sent('d-quote'), ...sent('d-entry')].map((o) => [o.purpose, o.price, o.count]), []);
  assert.equal(g.oms.positions.position(g.market.ticker), 16, 'not added to');
  assert.match(JSON.stringify(g.audit.tail(50, 'risk_reject').map((r) => r.data)), /the heat lane holds this market/);
  // The same quote once the lane lets go of the market: it goes out, so the hold alone refused it.
  const holds = g.lane.holds.bind(g.lane);
  g.lane.holds = () => false;
  await place({}, 'd-control');
  assert.equal(sent('d-control').length, 1, 'the control quotes');
  g.lane.holds = holds;
  // An exit still goes out while the lane holds the market: the exits' owner sells through the same path.
  await place({ side: 'ask', price: 0.45, count: 16, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: true, purpose: 'exit', why: 'test exit' }, 'd-exit');
  assert.equal(sent('d-exit').length, 1);
  assert.equal(g.oms.positions.position(g.market.ticker), 0, 'sold');
});

test('the round trip closes and counts: settled in profit, a trip and a win on the lane\'s book', async () => {
  const g = await setup();
  g.source.set(fired());
  await g.engine.tick();
  await g.engine.tick();
  assert.equal(g.lane.status(Date.now()).open[0]?.openedAt !== undefined, true, 'seen open');
  const settled = g.oms.settle(g.market.ticker, 'yes')!;
  await g.engine.tick();
  const st = g.lane.status(Date.now());
  assert.deepEqual([st.trips, st.wins, st.open.length], [1, 1, 0]);
  assert.ok(Math.abs(st.pnl - settled.realized!) < 1e-6, `pnl ${st.pnl} vs realized ${settled.realized}`);
  assert.ok(st.pnl > 0);
  const closed = rows(g.audit, 'heat').find((r) => r.event === 'closed')!;
  assert.deepEqual([closed.ticker, closed.settled, closed.trips, closed.wins], [g.market.ticker, true, 1, 1]);
  // The trip's own result under pnl, the book's running total under bookPnl (not written over the trip's).
  assert.ok(Math.abs(closed.pnl - settled.realized!) < 1e-6, `trip pnl ${closed.pnl}`);
  assert.ok(Math.abs(closed.bookPnl - st.pnl) < 1e-6, `book pnl ${closed.bookPnl}`);
  assert.ok(rows(g.audit, 'heat').some((r) => r.event === 'opened' && r.ticker === g.market.ticker));
  assert.equal(g.lane.holds(g.market.ticker), false);
});

test('an entry that never opened is dropped after 30 s and its tag comes off', async () => {
  const g = await setup();
  const now = Date.now();
  g.lane.sent({ asset: 'BTC', ticker: 'KXBTC15M-GONE', kind: '15m', h: 15, side: 'yes', price: 0.5, sideCost: 0.5, count: 20, stakeUsd: 10, weight: 1, slot: 1, context: 'none', fair: 0.53, ruleId: 'heat:R1:x', row: fired().coins.get('BTC')!.calls[0], why: 'heat test', closeTs: now + 600_000 }, now - 31_000, 0, 0);
  assert.ok(g.lane.holds('KXBTC15M-GONE'));
  await g.engine.tick();
  assert.deepEqual(g.untagged, ['KXBTC15M-GONE']);
  assert.equal(g.lane.holds('KXBTC15M-GONE'), false);
});

test('a market held by an evaluation still in flight: the call waits a few passes instead of being claimed as a skip', async () => {
  const busy = (e: Engine) => (e as unknown as { busy: Set<string> }).busy;
  // The lock clears on the third pass: the entry goes out then.
  const g = await setup();
  g.source.set(fired());
  busy(g.engine).add(g.market.ticker);
  await g.engine.tick();
  await g.engine.tick();
  assert.equal(heatOrders(g.oms).length, 0);
  assert.equal(rows(g.audit, 'heat').filter((r) => r.key).length, 0, 'not ruled on while it waits');
  busy(g.engine).delete(g.market.ticker);
  await g.engine.tick();
  assert.equal(heatOrders(g.oms).length, 1);
  assert.equal(rows(g.audit, 'heat').find((r) => r.key)!.entry, 'sent');
  // A lock that never clears: after ten passes the call is ruled on, as a skip with that reason.
  const s = await setup();
  s.source.set(fired());
  busy(s.engine).add(s.market.ticker);
  for (let i = 0; i < 11; i++) await s.engine.tick();
  assert.equal(heatOrders(s.oms).length, 0);
  assert.match(JSON.stringify(rows(s.audit, 'heat').filter((r) => r.key)), /an evaluation of this market is in flight/);
});

test('an entry that throws is recorded as failed, the lane lets go and the tag comes off, and the tick goes on', async () => {
  const g = await setup();
  g.source.set(fired());
  (g.engine as unknown as { placeChecked: () => Promise<never> }).placeChecked = async () => { throw new Error('exchange on fire'); };
  await g.engine.tick();
  const call = rows(g.audit, 'heat').find((r) => r.key)!;
  assert.match(call.entry, /^failed: Error: exchange on fire/);
  assert.deepEqual(g.untagged, [g.market.ticker]);
  assert.equal(g.lane.holds(g.market.ticker), false);
  assert.equal(g.audit.tail(50, 'error').map((r) => r.data as Row).filter((e) => e.where === 'heatTick').length, 1);
  assert.equal((g.engine as unknown as { busy: Set<string> }).busy.has(g.market.ticker), false, 'the busy lock is released');
});

test('a stale calls file is ignored and said once, never thrown', async () => {
  const g = await setup();
  const snap = fired();
  g.source.set({ ...snap, writtenAt: Date.now() - 181_000 });
  await g.engine.tick();
  await g.engine.tick();
  assert.equal(heatOrders(g.oms).length, 0);
  const said = rows(g.audit, 'heat').filter((r) => r.event === 'source');
  assert.equal(said.length, 1);
  assert.match(said[0].why, /ignored: written 18\d s ago/);
  assert.match(g.engine.guardStatus().heat!.notes.join(), /calls file ignored/);
});

test('a perps call (240 or 1440 minutes) is audited when new or changed, not each time it fires again', async () => {
  const g = await setup();
  // BTC's 4-hour and daily rows fired at a bar `back` ms ago (each a new call for the lane), the 4-hour one on side `dir4`.
  const perps = (back: number, dir4: 1 | -1 = 1): HeatSnapshot => {
    const barClose = Date.now() - back;
    const four: HeatCallRow = { key: '5m:WAD=low (falling in)', kind: 'single', tf: 5, h: 240, dir: dir4, rank: 1, of: 40, heat: 17.4, share: 0.6, odds: 2, barClose };
    const day: HeatCallRow = { ...four, key: '60m:DONCHIAN20pos=low (falling in)', tf: 60, h: 1440, dir: 1, heat: 5.19 };
    return { source: 'oracle-heat', run: 'R1', packSha: 'pack', writtenAt: barClose + 2_000, coins: new Map([['BTC', { asOf: barClose, tableSha: 'table', ok: true, calls: [four, day] }]]) };
  };
  const audited = (h: number) => rows(g.audit, 'heat').filter((r) => r.key && r.h === h).map((r) => [r.dir, r.skip.slice(0, 13)]);
  for (const back of [9_000, 8_000, 7_000]) { g.source.set(perps(back)); await g.engine.tick(); }
  assert.deepEqual([audited(240), audited(1440)], [[[1, 'perps context']], [[1, 'perps context']]], 'one row each while the call holds');
  g.source.set(perps(6_000, -1));
  await g.engine.tick();
  assert.deepEqual([audited(240), audited(1440)], [[[1, 'perps context'], [-1, 'perps context']], [[1, 'perps context']]], 'a new row when the side turns');
  assert.equal(heatOrders(g.oms).length, 0);
});

test('lane off (HEAT_LANE=false): the engine leaves the calls alone', async () => {
  const g = await setup({ env: { HEAT_LANE: 'false' } });
  g.source.set(fired());
  await g.engine.tick();
  assert.equal(heatOrders(g.oms).length, 0);
  assert.equal(rows(g.audit, 'heat').length, 0);
});

test('a throwing source never breaks the tick', async () => {
  const g = await setup();
  (g.source as unknown as { read: () => never }).read = () => { throw new Error('disk on fire'); };
  await g.engine.tick();
  await g.engine.tick();
  assert.ok(g.oms.liveOrders().some((o) => o.purpose === 'quote'), 'the old lane still quotes');
  const errs = g.audit.tail(50, 'error').map((r) => r.data as Row).filter((e) => e.where === 'heatTick');
  assert.equal(errs.length, 1, 'logged once, not once a tick');
});

// ---- Settings and the start check ----

test('settings: every HEAT_* name with its default, DOGE dropped, values checked', () => {
  const c = loadConfig({ DASHBOARD_TOKEN: TOKEN, DATA_DIR: '/tmp/heat-cfg' }).heat;
  assert.deepEqual(c, {
    enabled: false, callsFile: path.resolve('/tmp/heat-cfg/heat_calls.json'), assets: ['BTC', 'ETH', 'SOL', 'XRP'], horizons: [15, 60], topN: 10, maxAgeSec: 90,
    entryLagSec: 45, sizing: true, context: 'size', contextBoost: 0.25, maxOpen: 2, maxPerCoin: 1, cooldownSec: 60, reentries15m: 3, reentriesHourly: 6, reentryLossStop: 0.5, flatTrips: 30,
    pilotLossUsd: 15, feeNetCheck: false, perps: 'entry', perpHorizons: [60, 240], perpsDaily: 'context', pairConflict: 'skip',
  });
  const set = loadConfig({ DASHBOARD_TOKEN: TOKEN, HEAT_LANE: 'true', HEAT_ASSETS: 'btc, DOGE ,eth', HEAT_PERPS: 'gate', HEAT_PAIR_CONFLICT: 'pair', HEAT_CONTEXT: 'block', HEAT_CALLS_FILE: '/srv/calls.json', HEAT_PERP_HORIZONS: '240', HEAT_PERPS_DAILY: 'off' }).heat;
  assert.deepEqual([set.enabled, set.assets, set.perps, set.pairConflict, set.context, set.callsFile, set.perpHorizons, set.perpsDaily], [true, ['BTC', 'ETH'], 'gate', 'pair', 'block', '/srv/calls.json', [240], 'off']);
  assert.deepEqual(loadConfig({ DASHBOARD_TOKEN: TOKEN, HEAT_PERP_HORIZONS: '240, 60,60' }).heat.perpHorizons, [60, 240], 'sorted, each once');
  // Re-entry after a loss (Steven, Nov 11 6:59 PM EST / 23:59 UTC): counts per window and the loss stop; the old switch is retired.
  const re = loadConfig({ DASHBOARD_TOKEN: TOKEN, HEAT_REENTRIES_15M: '0', HEAT_REENTRIES_HOURLY: '1', HEAT_REENTRY_LOSS_STOP: '0' }).heat;
  assert.deepEqual([re.reentries15m, re.reentriesHourly, re.reentryLossStop], [0, 1, 0]);
  assert.throws(() => loadConfig({ DASHBOARD_TOKEN: TOKEN, HEAT_REENTER_AFTER_LOSS: 'false' }), /HEAT_REENTER_AFTER_LOSS is retired: re-entries after a loss are counted \(HEAT_REENTRIES_15M, HEAT_REENTRIES_HOURLY; 0 = never\)/);
  for (const [k, v] of [['HEAT_PERPS', 'true'], ['HEAT_PAIR_CONFLICT', 'average'], ['HEAT_TOP_N', '2.5'], ['HEAT_HORIZONS', '15,x'], ['HEAT_CONTEXT_BOOST', '2'], ['HEAT_LANE', 'yes'],
    // The daily curve is never an entry (no daily row above the no-signal twin's best), and the perps enter on 60 and 240 only.
    ['HEAT_PERPS_DAILY', 'entry'], ['HEAT_PERP_HORIZONS', '60,1440'], ['HEAT_PERP_HORIZONS', '15'], ['HEAT_PERP_HORIZONS', '60,x'],
    ['HEAT_REENTRIES_15M', '1.5'], ['HEAT_REENTRIES_HOURLY', '-1'], ['HEAT_REENTRY_LOSS_STOP', '-0.1'], ['HEAT_REENTER_AFTER_LOSS', 'true']]) {
    assert.throws(() => loadConfig({ DASHBOARD_TOKEN: TOKEN, [k]: v }), ConfigError, `${k}=${v}`);
  }
  // The perps horizons never open a Kalshi contract: listing them under HEAT_HORIZONS stops the start with the reason.
  for (const v of ['15,60,240', '1440']) {
    assert.throws(() => loadConfig({ DASHBOARD_TOKEN: TOKEN, HEAT_HORIZONS: v }), /HEAT_HORIZONS=.*240 and 1440 are perps horizons, never a Kalshi contract/, v);
  }
});

test('start check: HEAT_LANE=true refuses to start without the plan exits or with ORDER_USD_MIN=0', () => {
  const cfg = (env: Record<string, string>) => loadConfig({ DASHBOARD_TOKEN: TOKEN, ...env });
  assert.doesNotThrow(() => heatStartCheck(cfg({}), false), 'lane off: nothing to check');
  assert.throws(() => heatStartCheck(cfg({ HEAT_LANE: 'true' }), false), /HEAT_LANE=true: the plan exits must own its positions \(PLAN_RULES=true\)/);
  assert.doesNotThrow(() => heatStartCheck(cfg({ HEAT_LANE: 'true' }), true));
  assert.throws(() => heatStartCheck(cfg({ HEAT_LANE: 'true', ORDER_USD_MIN: '0' }), true), /ORDER_USD_MIN must be above 0/);
  assert.throws(() => heatStartCheck(cfg({ HEAT_LANE: 'true' }), false), ConfigError);
});
