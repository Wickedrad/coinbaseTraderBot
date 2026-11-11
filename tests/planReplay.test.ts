// PLAN_RULES in the replay (research/backtest.ts): the same pure ratchet (bot/plan/planRatchet.ts) sells a plan-tagged position,
// and today's exits leave it alone; off, a tagged position is managed by today's exits. No plan entry lane exists yet (E01), so
// the test tags every entry the replay opens through opts.planTag (a synthetic plan position).
import assert from 'node:assert/strict';
import path from 'node:path';
import { test } from 'node:test';
import { loadConfig } from '../bot/config';
import { DEFAULT_FEES, orderFee } from '../bot/fees';
import { MetaModel } from '../bot/model/metaModel';
import { runBacktest } from '../research/backtest';
import { readRecordings, ReplayState } from '../research/replay';
import { writeSyntheticRecordings } from '../research/synthetic';
import { tmpDir } from './helpers';

test('replay: PLAN_RULES on sells synthetic plan-tagged positions with the plan ratchet only; off, today\'s exits manage them', async () => {
  const dir = path.join(tmpDir(), 'rec');
  writeSyntheticRecordings(dir, { windows: 8, seed: 7, marketNoise: 0.06 });
  const run = async (on: boolean) => {
    const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), STRATEGY_STYLE: 'both', PLAN_RULES: on ? 'true' : 'false' });
    assert.equal(cfg.strategy.plan.enabled, on);
    const tagged = new Set<string>();
    const r = await runBacktest(dir, MetaModel.identity(), cfg.strategy, cfg.risk, 200, {
      exitPolicy: 'take_profit', paper: { orderFrac: 0.1, orderUsd: 0 }, fillLog: true,
      // A tight synthetic rule (arms at +2c, trails 3c) so the short synthetic windows exercise it.
      planTag: (e) => { tagged.add(e.ticker); return { ruleId: 'synthetic', settings: { armC: 2, trailC: 3 } }; },
    });
    return { r, tagged };
  };

  const on = await run(true);
  assert.ok(on.r.plan, 'the replay reports the plan');
  assert.ok(on.r.plan!.tagged > 0 && on.tagged.size > 0, JSON.stringify(on.r.plan));
  const exitsOn = (on.r.fillLog ?? []).filter((f) => f.coid?.includes('-exit-'));
  const planExits = exitsOn.filter((f) => f.coid!.endsWith('-exit-plan'));
  assert.ok(planExits.length > 0, `plan sales: ${JSON.stringify(on.r.plan)}`);
  assert.ok(on.r.plan!.arms > 0 && on.r.plan!.sales + on.r.plan!.endRuleSales > 0, JSON.stringify(on.r.plan));
  // Every exit fill is the plan's: every entry was tagged, so no take-profit, snipe, mandate or model exit sold anything.
  assert.deepEqual([...new Set(exitsOn.map((f) => f.coid!.replace(/^.*-exit-/, '')))], ['plan'], JSON.stringify(exitsOn.map((f) => f.coid)));
  const ev = on.r.plan!.events ?? [];
  assert.ok(ev.length > 0 && ev.every((e) => typeof e.at === 'number' && typeof e.ticker === 'string'));
  for (const e of ev.filter((x) => x.event === 'plan_ratchet_sell')) {
    assert.ok(e.bid! <= e.floor! + 1e-9, `sold at or under the floor: ${JSON.stringify(e)}`);
    assert.equal(e.limit, Math.max(0.01, Math.round((e.bid! - 0.02) * 100) / 100), 'the bid less 2 ticks');
  }
  // The floor never moved down for any ticker.
  const floors = new Map<string, number>();
  for (const e of ev) {
    if (e.event !== 'plan_ratchet_arm' && e.event !== 'plan_ratchet_raise') continue;
    if (e.event === 'plan_ratchet_arm') floors.delete(e.ticker);
    assert.ok(e.floor! >= (floors.get(e.ticker) ?? -Infinity) - 1e-9, JSON.stringify(e));
    floors.set(e.ticker, e.floor!);
  }

  const off = await run(false);
  assert.ok(off.r.plan!.tagged > 0, 'tagged the same way');
  assert.deepEqual([off.r.plan!.arms, off.r.plan!.sales, off.r.plan!.endRuleSales, off.r.plan!.events?.length], [0, 0, 0, 0]);
  const exitsOff = (off.r.fillLog ?? []).filter((f) => f.coid?.includes('-exit-'));
  assert.ok(!exitsOff.some((f) => f.coid!.endsWith('-exit-plan')));
  assert.ok(exitsOff.length > 0, 'today\'s exits sold the tagged positions');
  // Off is today's replay: the same run without the tag hook gives the same fills.
  const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), STRATEGY_STYLE: 'both' });
  const plain = await runBacktest(dir, MetaModel.identity(), cfg.strategy, cfg.risk, 200, { exitPolicy: 'take_profit', paper: { orderFrac: 0.1, orderUsd: 0 }, fillLog: true });
  assert.deepEqual(off.r.fillLog, plain.fillLog);
  assert.equal(off.r.pnl, plain.pnl);
});

test('replay: with orders and cancels 2.5 s in flight the ratchet still runs on every evaluation: each arm is at the first evaluation that reaches the arm level', async () => {
  const dir = path.join(tmpDir(), 'rec');
  writeSyntheticRecordings(dir, { windows: 8, seed: 7, marketNoise: 0.06 });
  const armC = 2;
  const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), STRATEGY_STYLE: 'both', PLAN_RULES: 'true' });
  const r = await runBacktest(dir, MetaModel.identity(), cfg.strategy, cfg.risk, 200, {
    exitPolicy: 'take_profit', paper: { orderFrac: 0.1, orderUsd: 0 }, fillLog: true, latency: { orderMs: 2500, cancelMs: 2500, jitterMs: 0 },
    planTag: () => ({ ruleId: 'synthetic', settings: { armC, trailC: 3, clock: 'tick' } }),
  });
  const arms = (r.plan!.events ?? []).filter((e) => e.event === 'plan_ratchet_arm');
  assert.ok(arms.length >= 10, JSON.stringify(r.plan));
  // The replay's evaluation ticks (the last event of an instant, at least 1 s after the last tick) and each armed market's
  // book at each of them, rebuilt from the same recordings.
  const want = new Set(arms.map((e) => e.ticker));
  const books = new Map<string, Map<number, { bid?: number; ask?: number }>>();
  const st = new ReplayState();
  let lastTick = 0;
  for await (const e of readRecordings(dir)) {
    st.apply(e);
    if (e.tie || st.now - lastTick < 1000) continue;
    lastTick = st.now;
    for (const t of want) {
      const b = st.books.get(t);
      if (!b) continue;
      const m = books.get(t) ?? new Map();
      books.set(t, m);
      m.set(st.now, { bid: b.bestBid()?.price, ask: b.bestAsk()?.price });
    }
  }
  // At the evaluation before each arm (the same position held, no fill since), the position was not yet up the arm level after
  // both fees: the ratchet did not skip an evaluation while an order or cancel of ours was travelling.
  let checked = 0;
  for (const e of arms) {
    const ticks = [...(books.get(e.ticker)?.keys() ?? [])].filter((t) => t < e.at);
    const prev = ticks[ticks.length - 1];
    const fills = (r.fillLog ?? []).filter((f) => f.ticker === e.ticker && f.t <= e.at);
    if (prev === undefined || !fills.length || fills[fills.length - 1].t >= prev) continue;
    const p = books.get(e.ticker)!.get(prev)!;
    const sideBid = e.side === 'yes' ? p.bid : p.ask !== undefined ? Math.round((1 - p.ask) * 1e4) / 1e4 : undefined;
    if (sideBid === undefined) continue;
    const cost = e.bid! - e.net! - orderFee(e.count, e.bid!, true, DEFAULT_FEES) / e.count;
    const netPrev = sideBid - cost - orderFee(e.count, sideBid, true, DEFAULT_FEES) / e.count;
    assert.ok(netPrev < armC / 100 - 1e-9, `${e.ticker} armed at ${e.at}, but at ${prev} its bid ${sideBid} was already ${(netPrev * 100).toFixed(2)}c up`);
    checked++;
  }
  assert.ok(checked >= 10, `checked ${checked} of ${arms.length}`);
});
