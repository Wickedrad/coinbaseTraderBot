// PLAN_RULES in the replay (research/backtest.ts): the same pure ratchet (bot/plan/planRatchet.ts, on the profit ratchet's core,
// in dollars for the whole position) and the hold exit sell a plan-tagged position, and today's other exits leave it alone;
// off, a tagged position is managed by today's exits. No plan entry lane exists yet (E01), so the test tags every entry the
// replay opens through opts.planTag (a synthetic plan position).
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

test('replay: PLAN_RULES on sells synthetic plan-tagged positions with the plan ratchet (and, HOLD_EXIT on, the hold exit) only; off, today\'s exits manage them', async () => {
  const dir = path.join(tmpDir(), 'rec');
  writeSyntheticRecordings(dir, { windows: 8, seed: 7, marketNoise: 0.06 });
  const run = async (on: boolean, env: Record<string, string> = {}) => {
    const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), STRATEGY_STYLE: 'both', PLAN_RULES: on ? 'true' : 'false', ...env });
    assert.equal(cfg.strategy.plan.enabled, on);
    const tagged = new Set<string>();
    const r = await runBacktest(dir, MetaModel.identity(), cfg.strategy, cfg.risk, 200, {
      exitPolicy: 'take_profit', paper: { orderFrac: 0.1, orderUsd: 0 }, fillLog: true,
      // A tight synthetic rule (arms at +$0.10, stop at least +$0.05, trails $0.15: about the old +2c and 3c on 5 contracts),
      // so the short synthetic windows exercise it.
      planTag: (e) => { tagged.add(e.ticker); return { ruleId: 'synthetic', settings: { armUsd: 0.1, stopMinUsd: 0.05, trailUsd: 0.15 } }; },
    });
    return { r, tagged };
  };

  // The hold exit off: every exit is the plan's.
  const on = await run(true, { HOLD_EXIT: 'false' });
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
  const gapAt = new Set(ev.filter((x) => x.event === 'plan_ratchet_gap').map((x) => `${x.ticker}|${x.at}`));
  for (const e of ev.filter((x) => x.event === 'plan_ratchet_sell')) {
    assert.ok(e.net! <= e.stop! + 1e-9, `sold at or under the stop: ${JSON.stringify(e)}`);
    assert.ok(e.net! >= -1e-9 || gapAt.has(`${e.ticker}|${e.at}`), `under the fee break-even only when the bid gapped through it: ${JSON.stringify(e)}`);
    assert.equal(e.limit, Math.max(0.01, Math.round((e.bid! - 0.02) * 100) / 100), 'the bid less 2 ticks');
  }
  // The stop never moved down for any ticker, and never sat under the rule's minimum.
  const stops = new Map<string, number>();
  for (const e of ev) {
    if (e.event !== 'plan_ratchet_arm' && e.event !== 'plan_ratchet_raise') continue;
    if (e.event === 'plan_ratchet_arm') stops.delete(e.ticker);
    assert.ok(e.stop! >= (stops.get(e.ticker) ?? -Infinity) - 1e-9 && e.stop! >= 0.05 - 1e-9, JSON.stringify(e));
    stops.set(e.ticker, e.stop!);
  }

  // The hold exit on (the default, Steven Nov 11 8:52 AM EST / 13:52 UTC): it sells plan positions too; nothing else does.
  const withHold = await run(true);
  const kinds = new Set((withHold.r.fillLog ?? []).filter((f) => f.coid?.includes('-exit-')).map((f) => f.coid!.replace(/^.*-exit-/, '')));
  assert.ok(kinds.has('plan') && [...kinds].every((k) => k === 'plan' || k === 'hold'), [...kinds].join(', '));

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
  const armUsd = 0.1;
  const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), STRATEGY_STYLE: 'both', PLAN_RULES: 'true' });
  const r = await runBacktest(dir, MetaModel.identity(), cfg.strategy, cfg.risk, 200, {
    exitPolicy: 'take_profit', paper: { orderFrac: 0.1, orderUsd: 0 }, fillLog: true, latency: { orderMs: 2500, cancelMs: 2500, jitterMs: 0 },
    planTag: () => ({ ruleId: 'synthetic', settings: { armUsd, stopMinUsd: 0.05, trailUsd: 0.15, clock: 'tick' } }),
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
  // At the evaluation before each arm (the same position held, no fill since), the trade (what partial sales banked plus the
  // whole rest at the bid, after both fees) was not yet up the arm level: the ratchet did not skip an evaluation while an order
  // or cancel of ours was travelling.
  let checked = 0;
  for (const e of arms) {
    const ticks = [...(books.get(e.ticker)?.keys() ?? [])].filter((t) => t < e.at);
    const prev = ticks[ticks.length - 1];
    const fills = (r.fillLog ?? []).filter((f) => f.ticker === e.ticker && f.t <= e.at);
    if (prev === undefined || !fills.length || fills[fills.length - 1].t >= prev) continue;
    const p = books.get(e.ticker)!.get(prev)!;
    const sideBid = e.side === 'yes' ? p.bid : p.ask !== undefined ? Math.round((1 - p.ask) * 1e4) / 1e4 : undefined;
    if (sideBid === undefined) continue;
    const n = e.count;
    const cost = e.bid! - (e.net! + orderFee(n, e.bid!, true, DEFAULT_FEES)) / n;
    const netPrev = n * (sideBid - cost) - orderFee(n, sideBid, true, DEFAULT_FEES);
    const tradePrev = netPrev + (e.banked ?? 0);
    assert.ok(tradePrev < armUsd - 1e-9, `${e.ticker} armed at ${e.at}, but at ${prev} its bid ${sideBid} had the trade already $${tradePrev.toFixed(2)} up`);
    checked++;
  }
  assert.ok(checked >= 10, `checked ${checked} of ${arms.length}`);
});

test('replay: a plan position\'s ratchet judges the trade, what partial sales banked plus the rest at the bid (the answer given to Steven, Nov 11 9:10 AM EST / 14:10 UTC), so a partial sale is no drop', async () => {
  const dir = path.join(tmpDir(), 'rec');
  writeSyntheticRecordings(dir, { windows: 8, seed: 7, marketNoise: 0.06 });
  const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), STRATEGY_STYLE: 'both', PLAN_RULES: 'true' });
  const r = await runBacktest(dir, MetaModel.identity(), cfg.strategy, cfg.risk, 200, {
    exitPolicy: 'take_profit', paper: { orderFrac: 0.1, orderUsd: 0 }, fillLog: true, planTag: () => ({ ruleId: 'synthetic' }),
  });
  const ev = r.plan!.events ?? [];
  // The maker quotes trim plan positions here too: the events name what was banked.
  assert.ok(ev.filter((e) => e.banked).length >= 3, JSON.stringify(r.plan));
  const trade = (e: (typeof ev)[number]) => e.net! + (e.banked ?? 0);
  for (const e of ev) {
    // Its best is the trade's net when it arms or rises, and it sells once the trade's net is at or under the stop.
    if (e.event === 'plan_ratchet_arm' || e.event === 'plan_ratchet_raise') assert.ok(Math.abs(e.best! - trade(e)) < 1e-3, JSON.stringify(e));
    if (e.event === 'plan_ratchet_sell') assert.ok(trade(e) <= e.stop! + 1e-9, JSON.stringify(e));
  }
  // The sale's reason names the trade's net and what was banked.
  const sales = (r.fillLog ?? []).filter((f) => f.coid?.endsWith('-exit-plan') && f.why?.includes('banked by partial sales'));
  assert.ok(sales.length > 0, JSON.stringify((r.fillLog ?? []).filter((f) => f.coid?.endsWith('-exit-plan')).map((f) => f.why)));
  for (const f of sales) {
    const m = /^plan ratchet: net ([+-]\$[\d.]+).* at or under its stop ([+-]\$[\d.]+)/.exec(f.why!);
    if (m) assert.ok(Number(m[1].replace('$', '')) <= Number(m[2].replace('$', '')) + 0.006, f.why);
  }
});
