import assert from 'node:assert/strict';
import path from 'path';
import { test } from 'node:test';
import { Alerter } from '../bot/alerts/alerter';
import { buildNeuralMap } from '../bot/api/neuralMap';
import type { ApiDeps } from '../bot/api/server';
import { loadConfig } from '../bot/config';
import { Engine } from '../bot/engine';
import type { KalshiRest } from '../bot/kalshi/rest';
import type { MarketInfo } from '../bot/kalshi/types';
import { MarketData, Recorder } from '../bot/marketdata/marketData';
import { OrderBook } from '../bot/marketdata/orderBook';
import { breakEvenExit } from '../bot/strategy/fairValueStrategy';
import { orderFee } from '../bot/fees';
import { contractKind } from '../bot/model/fairValue';
import { MetaModel } from '../bot/model/metaModel';
import { Oms } from '../bot/oms/oms';
import { PaperExchange } from '../bot/paper/paperExchange';
import { KillSwitch } from '../bot/risk/killSwitch';
import { RiskGateway } from '../bot/risk/riskGateway';
import { Reconciler } from '../bot/recon/reconciler';
import { QuotaFloors, type PacerFloorMode } from '../bot/risk/quotaPacer';
import { decideMatch, MatchTracker, SCORE_FRESH_MS, tennisLoserCutAt, tennisSize, tennisStartTime, WIN_CHANCE_MAX_SPREAD, type MatchMarket } from '../bot/tennis/tennisStrategy';
import { impliedModel } from '../bot/tennis/tennisModel';
import { openExchange, tmpAudit, tmpDir } from './helpers';

const T = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32) }).tennis;
const t0 = 1_800_000_000_000;
const mk = (ticker: string, bid: number, ask: number, o: Partial<MatchMarket> = {}): MatchMarket => ({ ticker, quote: { bid, ask, bidSize: 50, askSize: 50 }, position: 0, ...o });
const budget = { bankroll: 1000, tennisRisk: 0, matchRisk: 0 };
/** Market with a real book: `bidSize` vs `askSize` sets the depth-imbalance confluence signal. */
const mkb = (ticker: string, bid: number, ask: number, bidSize: number, askSize: number, now: number, o: Partial<MatchMarket> = {}): MatchMarket => {
  const book = new OrderBook(ticker);
  book.applySnapshot({ bids: [{ price: bid, size: bidSize }], asks: [{ price: ask, size: askSize }] }, now);
  return { ...mk(ticker, bid, ask, o), book };
};

test('defaults: 25% total tennis cap (and it cannot be raised above 25%)', () => {
  assert.equal(T.maxTotalFrac, 0.25);
  assert.throws(() => loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), TENNIS_MAX_TOTAL_FRAC: '0.3' }));
  assert.equal(contractKind('KXATPMATCH'), 'match');
  assert.equal(contractKind('KXWTAMATCH'), 'match');
  assert.notEqual(contractKind('KXWTAMATCHX'), 'match');
});

test('sizing respects per-order, per-match and the 25% total cap', () => {
  const cost = 0.2 + 0.0175 * 0.2 * 0.8; // price + maker fee per contract
  assert.equal(tennisSize(0.2, T, budget), Math.floor((49.99 / cost) * 100) / 100);                 // 5% of $1000
  assert.equal(tennisSize(0.2, T, { ...budget, matchRisk: 90 }), Math.floor((9.99 / cost) * 100) / 100);   // 10% match cap
  assert.equal(tennisSize(0.2, T, { ...budget, tennisRisk: 245 }), Math.floor((4.99 / cost) * 100) / 100); // 25% total cap
  assert.equal(tennisSize(0.2, T, { ...budget, tennisRisk: 250 }), 0);
  assert.ok(tennisSize(0.2, T, budget) * cost <= 50);
});

test('underdog rule: skewed match about to start -> maker bid on the underdog; not when balanced', () => {
  const tr = new MatchTracker('E', T);
  const snap = { event: 'E', now: t0, startTime: t0 + 10 * 60_000, closeTime: t0 + 86_400_000, markets: [mk('E-ALC', 0.84, 0.86), mkb('E-DOG', 0.14, 0.17, 300, 100, t0)] };
  const out = decideMatch(tr, snap, T, budget);
  assert.equal(out.phase, 'underdog_window');
  assert.equal(out.plans.length, 1);
  const p = out.plans[0];
  assert.deepEqual([p.ticker, p.side, p.postOnly, p.leg], ['E-DOG', 'bid', true, 'underdog_entry']);
  assert.equal(p.price, 0.15, 'improves the underdog bid by one tick');
  const balanced = decideMatch(new MatchTracker('F', T), { ...snap, event: 'F', markets: [mk('F-A', 0.55, 0.57), mk('F-B', 0.43, 0.45)] }, T, budget);
  assert.equal(balanced.plans.length, 0);
  assert.ok(balanced.notes.some((n) => n.includes('not skewed')));
  const early = decideMatch(new MatchTracker('G', T), { ...snap, event: 'G', startTime: t0 + 3 * 3_600_000 }, T, budget);
  assert.equal(early.phase, 'pre');
  assert.equal(early.plans.length, 0, 'hours before the start: wait');
});

test('fixed take-profit mode (TENNIS_TRAIL=false): resting take-profit at max(+6c, +40%)', () => {
  const noTrail = { ...T, trail: false };
  const tr = new MatchTracker('E', noTrail);
  const markets = [mk('E-ALC', 0.80, 0.82), mk('E-DOG', 0.18, 0.20, { position: 100, avgEntry: 0.15 })];
  tr.underdogTicker = 'E-DOG';
  const out = decideMatch(tr, { event: 'E', now: t0, startTime: t0 - 60_000, closeTime: t0 + 86_400_000, markets }, noTrail, budget);
  const tp = out.plans[0];
  assert.deepEqual([tp.leg, tp.side, tp.count, tp.price], ['underdog_tp', 'ask', 100, 0.21]); // 0.15 + max(0.06, 0.06)
});


test('conservative price hunt: no confluence -> take the profit at the target; confluence -> hunt, then the next exit in profit', () => {
  const run = (tr: MatchTracker, now: number, dogBids: Array<[number, number]>, dogAsk: number, favBid: number, flow?: number) => {
    const book = new OrderBook('E-DOG');
    book.applySnapshot({ bids: dogBids.map(([price, size]) => ({ price, size })), asks: [{ price: dogAsk, size: 100 }] }, now);
    const m = [mk('E-ALC', favBid, favBid + 0.02), { ...mk('E-DOG', dogBids[0][0], dogAsk, { position: 100, avgEntry: 0.15, flow }), book }];
    return decideMatch(tr, { event: 'E', now, startTime: t0 - 60_000, closeTime: t0 + 86_400_000, markets: m }, T, budget);
  };
  // Below the 0.21 target: ride, no exit order.
  const a = new MatchTracker('E', T); a.underdogTicker = 'E-DOG';
  const o0 = run(a, t0, [[0.18, 300]], 0.20, 0.80);
  assert.equal(o0.plans.length, 0);
  assert.ok(o0.notes.some((n) => n.includes('hunt starts at 0.21')));
  // Reaches the target with no confirming signals (flat, balanced book): take the profit now.
  const quiet = new MatchTracker('Q', T); quiet.underdogTicker = 'E-DOG';
  for (let i = 0; i < 13; i++) run(quiet, t0 + i * 5000, [[0.21, 100]], 0.23, 0.77);
  const take = run(quiet, t0 + 13 * 5000, [[0.21, 100]], 0.23, 0.77);
  assert.deepEqual([take.plans[0]?.leg, take.plans[0]?.price, take.plans[0]?.reduceOnly], ['underdog_trail', 0.21, true], JSON.stringify(take.notes));
  // A surge with confluence (momentum, heavy bids, opponent falling, buyers lifting): hunt.
  const h = new MatchTracker('H', T); h.underdogTicker = 'E-DOG';
  let now = t0;
  for (let i = 0; i < 13; i++) { run(h, now, [[0.15, 100]], 0.17, 0.83); now += 5000; }
  let o = run(h, now, [[0.24, 400], [0.22, 400]], 0.25, 0.74, 0.6);
  assert.equal(o.plans.length, 0, JSON.stringify(o.notes));
  assert.ok(h.signals.get('E-DOG')!.score >= 2);
  now += 5000;
  o = run(h, now, [[0.27, 400], [0.25, 400]], 0.28, 0.71, 0.6);
  assert.equal(o.plans.length, 0);
  assert.equal(h.stops.get('E-DOG'), 0.25, 'stop trails 2 ticks under the peak bid');
  // The bid breaks the stop: next available exit in profit, where the bids can fill 100.
  now += 5000;
  o = run(h, now, [[0.24, 60], [0.23, 400]], 0.26, 0.74, 0.6);
  assert.deepEqual([o.plans[0].leg, o.plans[0].price], ['underdog_trail', 0.23], 'sell where depth covers the position');
  // Time limit ends a hunt that keeps confirming.
  const lim = new MatchTracker('L', { ...T, huntMaxSec: 10 }); lim.underdogTicker = 'E-DOG';
  now = t0;
  for (let i = 0; i < 13; i++) { run(lim, now, [[0.15, 100]], 0.17, 0.83); now += 5000; }
  const cfgL = { ...T, huntMaxSec: 10 };
  const runL = (bid: number) => { const book = new OrderBook('E-DOG'); book.applySnapshot({ bids: [{ price: bid, size: 400 }], asks: [{ price: bid + 0.01, size: 50 }] }, now); return decideMatch(lim, { event: 'E', now, startTime: t0 - 60_000, closeTime: t0 + 86_400_000, markets: [mk('E-ALC', 1 - bid - 0.02, 1 - bid), { ...mk('E-DOG', bid, bid + 0.01, { position: 100, avgEntry: 0.15, flow: 0.8 }), book }] }, cfgL, budget); };
  assert.equal(runL(0.24).plans.length, 0);
  now += 12_000;
  const late = runL(0.26);
  assert.match(late.plans[0]?.why ?? '', /time limit/);
});

test('in-play detection without a start time, then favorite re-entry once half the match is done', () => {
  const tr = new MatchTracker('E', T);
  let now = t0;
  // The leader's book leans to the bid side and buyers are lifting: 2 confluence signals.
  const snap = (pFav: number) => ({ event: 'E', now, closeTime: t0 + 86_400_000, markets: [mkb('E-A', pFav - 0.01, pFav + 0.01, 300, 100, now, { flow: 0.5 }), mk('E-B', 1 - pFav - 0.01, 1 - pFav + 0.01)] });
  // Quiet pre-match: not live.
  for (let i = 0; i < 10; i++) { assert.equal(decideMatch(tr, snap(0.6), T, budget).phase, 'pre'); now += 30_000; }
  // A 4c move within 3 minutes: in play.
  decideMatch(tr, snap(0.64), T, budget);
  assert.equal(tr.liveSince, now);
  // 0.6 is not skewed enough for the underdog rule; move to the middle of the match.
  now += 85 * 60_000;
  for (let i = 0; i < 12; i++) { decideMatch(tr, snap(0.85), T, budget); now += 30_000; }
  const out = decideMatch(tr, snap(0.85), T, budget);
  assert.equal(out.phase, 'late');
  const fav = out.plans.find((p) => p.leg === 'fav_entry')!;
  assert.ok(fav, JSON.stringify(out));
  assert.deepEqual([fav.ticker, fav.side], ['E-A', 'bid']);
  // A slipping leader is not bought.
  const tr2 = new MatchTracker('E2', T);
  tr2.liveSince = t0;
  tr2.progress = () => 0.6; // past half: only the slipping check can block
  now = t0 + 60 * 60_000;
  for (let i = 0; i < 12; i++) { decideMatch(tr2, snap(0.90 - i * 0.01), T, budget); now += 30_000; }
  const slip = decideMatch(tr2, snap(0.78), T, budget);
  assert.equal(slip.plans.length, 0);
  assert.ok(slip.notes.some((n) => n.includes('slipping')));
});

test('grand slams are best of five (slower progress); the women\'s matches there best of three', () => {
  const tr = new MatchTracker('W', T);
  assert.equal(tr.bestOf([mk('W-A', 0.5, 0.52, { title: 'Will Sinner win the Sinner vs Alcaraz: Wimbledon Final match?' })]), 5);
  assert.equal(tr.bestOf([mk('X-A', 0.5, 0.52, { title: 'Will Sinner win the Sinner vs Alcaraz: Cincinnati match?' })]), 3);
  assert.deepEqual(tr.format([mk('KXWTAMATCH-26JUL11SWISAB-SWI', 0.5, 0.52, { title: 'Will Swiatek win the Swiatek vs Sabalenka: Wimbledon Final match?' })]), { bestOf: 3, finalTiebreak: 10 });
});

test('profit rules on tennis (Steven, Oct 30): the quota snipe sells a position whose profit after fees covers the hour; in the last 30% of the match one in profit rides to settlement', () => {
  assert.equal(T.settleFrac, 0.3);
  assert.equal(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), TENNIS_NO_EXIT_BEFORE_END_FRAC: '0.1' }).tennis.settleFrac, 0.1);
  const rules = { pacerUsd: 4.5, settleFrac: T.settleFrac };
  // A favorite held from 0.80: its hunt starts at the 0.86 target, so below it the legs plan nothing.
  const fav = (prog: number, bid: number, net: number | undefined, r: { pacerUsd?: number; settleFrac?: number }) => {
    const tr = new MatchTracker('P', T);
    tr.progress = () => prog; // progress itself is tested with the scoring model
    return decideMatch(tr, { event: 'P', now: t0 + 3_600_000, startTime: t0, closeTime: t0 + 86_400_000, markets: [mk('P-FAV', bid, bid + 0.02, { position: 30, avgEntry: 0.8, netAtBid: net }), mk('P-DOG', 1 - bid - 0.02, 1 - bid)] }, T, budget, 0.01, r);
  };
  // Mid-match, +$5 after fees covers the $4.50 the hour needs: sold at the bid at once, though the legs would hold.
  const snipe = fav(0.5, 0.84, 5, rules);
  assert.equal(snipe.plans.length, 1, JSON.stringify(snipe));
  const p = snipe.plans[0];
  assert.deepEqual([p.leg, p.side, p.price, p.count, p.reduceOnly, p.postOnly, p.timeInForce], ['quota_snipe', 'ask', 0.84, 30, true, false, 'immediate_or_cancel']);
  assert.equal(p.why, '+$5.00 net on 30 at bid 0.84 covers the $4.50 the hour needs');
  // Less than the hour needs, or the pacer off: the legs decide (the favorite holds under its target).
  assert.equal(fav(0.5, 0.84, 3, rules).plans.length, 0);
  assert.equal(fav(0.5, 0.84, 5, { settleFrac: T.settleFrac }).plans.length, 0);
  // At 65% the last 30% has not started: sniped. At 75% it has: in profit after fees, the position rides to settlement.
  assert.equal(fav(0.65, 0.84, 5, rules).plans[0]?.leg, 'quota_snipe');
  const ride = fav(0.75, 0.84, 5, rules);
  assert.equal(ride.plans.length, 0);
  assert.ok(ride.notes.includes('P-FAV: match 75% done (its last 30%), +$5.00 after fees: riding to settlement'), JSON.stringify(ride.notes));
  // With the rule off (0) the snipe applies to the end.
  assert.equal(fav(0.75, 0.84, 5, { pacerUsd: 4.5, settleFrac: 0 }).plans[0]?.leg, 'quota_snipe');
  // The legs' own exits of a position in profit are held too: above its target without confluence the hunt takes the profit,
  // except in the last 30%.
  assert.equal(fav(0.5, 0.9, 2.5, rules).plans[0]?.leg, 'fav_trail');
  assert.equal(fav(0.75, 0.9, 2.5, rules).plans.length, 0);
  // A position not in profit keeps its exits there: the late cut still sells an underdog under water.
  const dog = (bid: number, net: number) => {
    const tr = new MatchTracker('U', T);
    tr.liveSince = t0; tr.underdogTicker = 'U-DOG';
    tr.progress = () => 0.8;
    const now = t0 + 30 * 60_000;
    return decideMatch(tr, { event: 'U', now, startTime: t0, closeTime: t0 + 86_400_000, markets: [mk('U-FAV', 1 - bid - 0.02, 1 - bid), mkb('U-DOG', bid, bid + 0.02, 300, 100, now, { position: 100, avgEntry: 0.15, netAtBid: net })] }, T, budget, 0.01, rules);
  };
  assert.deepEqual([dog(0.1, -5.5).plans[0]?.leg, dog(0.1, -5.5).plans[0]?.price], ['underdog_cut', 0.1]);
  assert.equal(dog(0.2, 3.9).plans.length, 0, 'in profit: rides instead of the cut');
});

test('profit rules on tennis: in the last 30% of the match a position not in profit after fees is never held to settlement', () => {
  assert.equal(T.endLoserCut, true);
  assert.equal(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), TENNIS_END_LOSER_CUT: 'false' }).tennis.endLoserCut, false);
  const rules = { pacerUsd: 4.5, settleFrac: T.settleFrac, endLoserCut: true };
  // A favorite held from 0.80 (it has no loss exit of its own: TENNIS_FAV_STOP_CENTS is 0), the progress held 3 minutes.
  const fav = (prog: number, bid: number, net: number | undefined, r: { pacerUsd?: number; settleFrac?: number; endLoserCut?: boolean }) => {
    const tr = new MatchTracker('P', T);
    tr.progress = () => prog;
    const at = (now: number) => decideMatch(tr, { event: 'P', now, startTime: t0, closeTime: t0 + 86_400_000, markets: [mk('P-FAV', bid, bid + 0.02, { position: 30, avgEntry: 0.8, netAtBid: net }), mk('P-DOG', 1 - bid - 0.02, 1 - bid)] }, T, budget, 0.01, r);
    for (let k = 6; k > 0; k--) at(t0 + 3_600_000 - k * 30_000);
    return at(t0 + 3_600_000);
  };
  // 75% done, -$0.80 after fees at the 0.79 bid: sold at the bid.
  const cut = fav(0.75, 0.79, -0.8, rules);
  assert.equal(cut.plans.length, 1, JSON.stringify(cut));
  const p = cut.plans[0];
  assert.deepEqual([p.leg, p.side, p.price, p.count, p.reduceOnly, p.postOnly, p.timeInForce], ['end_cut', 'ask', 0.79, 30, true, false, 'immediate_or_cancel']);
  assert.equal(p.why, 'match 75% done (its last 30%), -$0.80 after fees at bid 0.79: not in profit, not held to settlement');
  // Break-even after fees is not a profit: cut too.
  assert.equal(fav(0.75, 0.81, 0, rules).plans[0]?.leg, 'end_cut');
  // In profit there: rides. Before the last 30%: the legs decide (the favorite holds).
  assert.equal(fav(0.75, 0.84, 1, rules).plans.length, 0);
  assert.equal(fav(0.65, 0.79, -0.8, rules).plans.length, 0);
  // With the rule off the favorite rides the loss to settlement (as before Nov 5).
  assert.equal(fav(0.75, 0.79, -0.8, { pacerUsd: 4.5, settleFrac: T.settleFrac }).plans.length, 0);
  // No bid: nothing to sell into (the engine then has no net either); judged again next tick.
  const noBid = new MatchTracker('P', T);
  noBid.progress = () => 0.75;
  noBid.progressHigh = 0.75;
  const dry = decideMatch(noBid, { event: 'P', now: t0 + 3_600_000, startTime: t0, closeTime: t0 + 86_400_000, markets: [{ ...mk('P-FAV', 0.79, 0.81, { position: 30, avgEntry: 0.8 }), quote: { ask: 0.81, askSize: 50 } }, mk('P-DOG', 0.19, 0.21)] }, T, budget, 0.01, rules);
  assert.equal(dry.plans.length, 0, JSON.stringify(dry.plans));
  // A comeback pulls the progress back below the last share just as the favorite goes under water: it is cut all the same.
  const back = new MatchTracker('P', T);
  let prog = 0.76, now = t0 + 3_600_000;
  back.progress = () => prog;
  const snapAt = (bid: number, net: number) => ({ event: 'P', now, startTime: t0, closeTime: t0 + 86_400_000, markets: [mk('P-FAV', bid, bid + 0.02, { position: 30, avgEntry: 0.8, netAtBid: net }), mk('P-DOG', 1 - bid - 0.02, 1 - bid)] });
  for (let k = 0; k < 6; k++, now += 30_000) assert.equal(decideMatch(back, snapAt(0.9, 2.5), T, budget, 0.01, rules).plans.length, 0, 'in profit: rides');
  prog = 0.62;
  const comeback = decideMatch(back, snapAt(0.79, -0.8), T, budget, 0.01, rules);
  assert.equal(comeback.plans[0]?.leg, 'end_cut', JSON.stringify(comeback));
  assert.equal(comeback.plans[0]?.why, 'match 62% done, 76% at its furthest (its last 30%), -$0.80 after fees at bid 0.79: not in profit, not held to settlement');
  // No last share (TENNIS_NO_EXIT_BEFORE_END_FRAC=0): no cut either.
  assert.equal(fav(0.75, 0.79, -0.8, { pacerUsd: 4.5, settleFrac: 0, endLoserCut: true }).plans.length, 0);
  // One tick's reading (a thin or one-sided book) does not latch: back at 30% the position is the legs' again.
  const spike = new MatchTracker('P', T);
  let sp = 0.3;
  spike.progress = () => sp;
  now = t0 + 3_600_000;
  for (let k = 0; k < 6; k++, now += 30_000) decideMatch(spike, snapAt(0.79, -0.8), T, budget, 0.01, rules);
  sp = 0.72;
  decideMatch(spike, snapAt(0.79, -0.8), T, budget, 0.01, rules);
  now += 5_000;
  sp = 0.3;
  for (let k = 0; k < 8; k++, now += 30_000) assert.equal(decideMatch(spike, snapAt(0.79, -0.8), T, budget, 0.01, rules).plans.length, 0, `tick ${k}`);
  assert.equal(spike.progressHigh, 0.3);
  // Held for two minutes it is reached: the cut stays on when the progress falls back.
  sp = 0.72;
  for (let k = 0; k < 5; k++, now += 30_000) decideMatch(spike, snapAt(0.9, 2.5), T, budget, 0.01, rules);
  sp = 0.5;
  assert.equal(decideMatch(spike, snapAt(0.79, -0.8), T, budget, 0.01, rules).plans[0]?.leg, 'end_cut');
  // No new entry in the last 30%: a favorite bought there would start under water.
  const entry = (r: { settleFrac?: number; endLoserCut?: boolean; endEntryMargin?: number }, prog = 0.8, high = 0) => {
    const tr = new MatchTracker('Q', T);
    tr.liveSince = t0;
    tr.progress = () => prog;
    tr.progressHigh = high;
    let now = t0 + 60 * 60_000;
    const snap = () => ({ event: 'Q', now, closeTime: t0 + 86_400_000, markets: [mkb('Q-A', 0.84, 0.86, 300, 100, now, { flow: 0.5 }), mk('Q-B', 0.14, 0.16)] });
    for (let i = 0; i < 12; i++) { decideMatch(tr, snap(), T, budget, 0.01, r); now += 30_000; }
    return decideMatch(tr, snap(), T, budget, 0.01, r);
  };
  assert.equal(entry({ settleFrac: T.settleFrac }).plans[0]?.leg, 'fav_entry', 'the rule off: the favorite is bought late');
  const none = entry({ settleFrac: T.settleFrac, endLoserCut: true });
  assert.equal(none.plans.length, 0, JSON.stringify(none.plans));
  assert.ok(none.notes.some((n) => n.includes('no new entry (fav_entry)')), JSON.stringify(none.notes));
  // The margin: none from 65% (TENNIS_END_ENTRY_MARGIN 0.05 before the last 30%), and a dip in progress does not reopen it.
  assert.equal(T.endEntryMargin, 0.05);
  const r = { settleFrac: T.settleFrac, endLoserCut: true, endEntryMargin: T.endEntryMargin };
  assert.equal(entry(r, 0.6).plans[0]?.leg, 'fav_entry', 'before the margin: bought');
  assert.equal(entry(r, 0.66).plans.length, 0, 'inside the margin: not bought');
  assert.equal(entry(r, 0.6, 0.72).plans.length, 0, 'the match reached its last share before: not bought on a dip');
});

test('quota floor on tennis (PACER_FLOOR, Steven Oct 31): a leg aiming higher keeps the position, the need it covered becomes its floor, and it is sold once its profit falls below it', () => {
  // The favorite held from 0.80 under its 0.86 hunt start: a set price above the bid, in either mode.
  const floors = new QuotaFloors();
  const tr = new MatchTracker('Q', T);
  tr.progress = () => 0.5;
  const at = (bid: number, net: number, r: { pacerUsd: number; floorMode: PacerFloorMode; floorTicks?: number }) => decideMatch(tr, { event: 'Q', now: t0 + 3_600_000, startTime: t0, closeTime: t0 + 86_400_000,
    markets: [mk('Q-FAV', bid, bid + 0.02, { position: 30, avgEntry: 0.8, netAtBid: net }), mk('Q-DOG', 1 - bid - 0.02, 1 - bid)] }, T, budget, 0.01, { ...r, settleFrac: T.settleFrac, floors });
  const held = at(0.84, 5, { pacerUsd: 4.5, floorMode: 'riding' });
  assert.equal(held.plans.length, 0, JSON.stringify(held));
  assert.ok(held.notes.includes('Q-FAV: quota floor: +$5.00 net covers the $4.50 the hour needs; held for the trail starting at 0.86, sold if the profit falls below its floor'), JSON.stringify(held.notes));
  assert.equal(floors.floor('Q-FAV', 30), 4.5);
  // The hour needs less now, but the profit fell below the $4.50 floor: sold at the bid.
  const fell = at(0.83, 4.4, { pacerUsd: 3, floorMode: 'riding' });
  assert.deepEqual([fell.plans[0]?.leg, fell.plans[0]?.price, fell.plans[0]?.count, fell.plans[0]?.why], ['quota_snipe', 0.83, 30, '+$4.40 net on 30 at bid 0.83 fell below its $4.50 floor'], JSON.stringify(fell));
  // PACER_FLOOR_TICKS: 2 ticks on 30 contracts is a $0.60 cushion: +$4.40 and +$3.95 hold, +$3.80 sells.
  assert.equal(at(0.83, 4.4, { pacerUsd: 3, floorMode: 'riding', floorTicks: 2 }).plans.length, 0);
  assert.equal(at(0.82, 3.95, { pacerUsd: 3, floorMode: 'riding', floorTicks: 2 }).plans.length, 0);
  assert.equal(at(0.81, 3.8, { pacerUsd: 3, floorMode: 'riding', floorTicks: 2 }).plans[0]?.why, '+$3.80 net on 30 at bid 0.81 fell below its $4.50 floor');
  // E22: the default 8 ticks on 30 contracts is a $2.40 cushion, more than a $0.75 floor (alone, a line at -$1.65); the line is
  // never below the smaller of the floor and 1 tick a contract of profit after fees ($0.30 on 30): +$0.35 holds, +$0.05 sells.
  floors.forget('Q-FAV');
  assert.equal(at(0.84, 0.9, { pacerUsd: 0.75, floorMode: 'riding', floorTicks: 8 }).plans.length, 0);
  assert.equal(floors.floor('Q-FAV', 30), 0.75);
  assert.equal(at(0.83, 0.35, { pacerUsd: 3, floorMode: 'riding', floorTicks: 8 }).plans.length, 0);
  const kept = at(0.82, 0.05, { pacerUsd: 3, floorMode: 'riding', floorTicks: 8 }).plans[0];
  assert.deepEqual([kept?.leg, kept?.price, kept?.count, kept?.why], ['quota_snipe', 0.82, 30, '+$0.05 net on 30 at bid 0.82 fell below its $0.75 floor']);
  assert.equal(at(0.78, -1.5, { pacerUsd: 3, floorMode: 'riding', floorTicks: 8 }).plans[0]?.leg, 'quota_snipe', 'a gap into a loss the cushion alone held to is sold');
  // targets counts the hunt start too; off sells at the quota as before.
  floors.forget('Q-FAV');
  assert.equal(at(0.84, 5, { pacerUsd: 4.5, floorMode: 'targets' }).plans.length, 0);
  assert.equal(floors.floor('Q-FAV', 30), 4.5);
  floors.forget('Q-FAV');
  assert.equal(at(0.84, 5, { pacerUsd: 4.5, floorMode: 'off' }).plans[0]?.leg, 'quota_snipe');
  assert.equal(floors.floor('Q-FAV', 30), undefined);
  // A hunt riding its stop with confluence (the underdog surge above): riding holds it on a floor; targets has no set price
  // there and sells at the quota.
  const surge = (mode: PacerFloorMode) => {
    const f = new QuotaFloors();
    const h = new MatchTracker('H', T); h.underdogTicker = 'E-DOG';
    const run = (now: number, dogBids: Array<[number, number]>, dogAsk: number, favBid: number, net: number, flow?: number) => {
      const book = new OrderBook('E-DOG');
      book.applySnapshot({ bids: dogBids.map(([price, size]) => ({ price, size })), asks: [{ price: dogAsk, size: 100 }] }, now);
      const m = [mk('E-ALC', favBid, favBid + 0.02), { ...mk('E-DOG', dogBids[0][0], dogAsk, { position: 100, avgEntry: 0.15, flow, netAtBid: net }), book }];
      return decideMatch(h, { event: 'E', now, startTime: t0 - 60_000, closeTime: t0 + 86_400_000, markets: m }, T, budget, 0.01, { pacerUsd: 4.5, settleFrac: T.settleFrac, floorMode: mode, floors: f });
    };
    let now = t0;
    for (let i = 0; i < 13; i++) { run(now, [[0.15, 100]], 0.17, 0.83, -0.5); now += 5000; }
    return { out: run(now, [[0.24, 400], [0.22, 400]], 0.25, 0.74, 7, 0.6), f };
  };
  const ride = surge('riding');
  assert.equal(ride.out.plans.length, 0, JSON.stringify(ride.out));
  assert.ok(ride.out.notes.some((n) => /^E-DOG: quota floor: \+\$7\.00 net covers the \$4\.50 the hour needs; held for the trail riding its stop 0\.\d\d, sold/.test(n)), JSON.stringify(ride.out.notes));
  assert.equal(ride.f.floor('E-DOG', 100), 4.5);
  assert.equal(surge('targets').out.plans[0]?.leg, 'quota_snipe');
});

test('engine trades tennis inside its own 25% budget and keeps it out of the crypto book', async () => {
  const dir = tmpDir();
  const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(40), DATA_DIR: dir, DOMINANCE_FEED: 'false', SPOT_FEED: 'false', PERPS_FEED: 'false', STRATEGY_SERIES: 'KXBTC15M', SESSION_EDGE_NO_ENTRY: 'false' });
  const now = Date.now();
  const m = (ticker: string, title: string): MarketInfo => ({ ticker, seriesTicker: 'KXATPMATCH', eventTicker: 'KXATPMATCH-E1', status: 'open', openTime: now - 3_600_000, closeTime: now + 6 * 3_600_000, tickSize: 0.01, title, startTime: now + 5 * 60_000, expirationTime: now + 5 * 60_000 + 14 * 86_400_000 });
  const markets = [m('KXATPMATCH-E1-FAV', 'Will Fav win?'), m('KXATPMATCH-E1-DOG', 'Will Dog win?')];
  const rest = {
    getSeriesFees: async () => ({ feeType: 'quadratic_with_maker_fees', multiplier: 1 }),
    getOpenMarkets: async (s: string) => (s === 'KXATPMATCH' ? markets : []),
    getMarket: async () => undefined,
  } as unknown as KalshiRest;
  const audit = tmpAudit();
  const md = new MarketData(cfg, rest, undefined, new Recorder(path.join(dir, 'rec')));
  await md.refreshCatalog(now);
  assert.equal(md.markets.get('KXATPMATCH-E1-DOG')?.kind, 'match');
  md.book('KXATPMATCH-E1-FAV').applySnapshot({ bids: [{ price: 0.84, size: 100 }], asks: [{ price: 0.86, size: 100 }] }, Date.now());
  md.book('KXATPMATCH-E1-DOG').applySnapshot({ bids: [{ price: 0.14, size: 300 }], asks: [{ price: 0.17, size: 100 }] }, Date.now());
  const paper = new PaperExchange(undefined, 200, (t) => md.books.get(t), () => ({ takerMultiplier: 1, makerMultiplier: 1 }));
  const kill = new KillSwitch(path.join(dir, 'kill.json'), audit);
  const oms = new Oms({ gateway: paper, audit, statePath: path.join(dir, 'oms.json'), feesFor: (t) => md.feesFor(t), sleep: async () => undefined });
  paper.on('fill', (f) => oms.onFill(f));
  paper.on('order', (o) => oms.onExchangeOrder(o));
  const recon = new Reconciler({ gateway: paper, oms, audit, getMarket: rest.getMarket, onPersistentBreak: () => undefined });
  const engine = new Engine({ cfg, audit, alerter: new Alerter([], audit), md, gateway: paper, oms, risk: new RiskGateway(cfg.risk), kill, recon, model: MetaModel.identity(), exchangeStatus: openExchange() });
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  await engine.tick();
  const open = await paper.getOpenOrders();
  assert.equal(open.length, 1, JSON.stringify([...engine.tennisStatus.values()]));
  const o = open[0];
  assert.deepEqual([o.ticker, o.side, o.price], ['KXATPMATCH-E1-DOG', 'bid', 0.15]);
  assert.ok(o.remainingCount * o.price <= 0.05 * 200 + 1e-9, 'per-order cap: 5% of the pool');
  const b = engine.tennisBudget();
  assert.ok(b.used > 0 && b.used <= b.cap, JSON.stringify(b));
  assert.equal(b.cap, 50);
  assert.equal(engine.status.has('KXATPMATCH-E1-DOG'), false, 'tennis never goes through the crypto pricer');
  // The neural map's tennis trader block: lit by the match, active with its resting order.
  const map = await buildNeuralMap({ cfg, md, engine, oms } as unknown as ApiDeps);
  const blk = map.layers.find((l) => l.id === 'bots')!.blocks.find((x) => x.id === 'bot_tennis')!;
  assert.ok(blk.cells.some((x) => x !== 0), 'the tracked match lights the block');
  assert.match(blk.note, /1 matches · 0 held · 1 resting/);
  assert.ok(blk.activity > 0.1);
});

test('engine: with TENNIS_SERIES=KXATPMATCH,KXWTAMATCH (the paper days, deploy/paper-settings.env) WTA matches are tennis matches too', async () => {
  const dir = tmpDir();
  const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(40), DATA_DIR: dir, DOMINANCE_FEED: 'false', SPOT_FEED: 'false', PERPS_FEED: 'false', STRATEGY_SERIES: 'KXBTC15M', SESSION_EDGE_NO_ENTRY: 'false',
    TENNIS_SERIES: 'KXATPMATCH,KXWTAMATCH', TENNIS_CONF_MOMENTUM_CENTS: '0.02', TENNIS_CONF_WINDOW_SEC: '120' });
  assert.deepEqual(cfg.tennis.series, ['KXATPMATCH', 'KXWTAMATCH']);
  const now = Date.now();
  // Closing in 6 h (past the crypto catalog horizon), starting in 5 min: only a match market is kept for that.
  const m = (series: string, ticker: string, title: string): MarketInfo => ({ ticker, seriesTicker: series, eventTicker: `${series}-E1`, status: 'open', openTime: now - 3_600_000, closeTime: now + 6 * 3_600_000, tickSize: 0.01, title, startTime: now + 5 * 60_000, expirationTime: now + 5 * 60_000 + 14 * 86_400_000 });
  const bySeries: Record<string, MarketInfo[]> = {
    KXATPMATCH: [m('KXATPMATCH', 'KXATPMATCH-E1-FAV', 'Will Fav win?'), m('KXATPMATCH', 'KXATPMATCH-E1-DOG', 'Will Dog win?')],
    KXWTAMATCH: [m('KXWTAMATCH', 'KXWTAMATCH-E1-FAV', 'Will Fav win?'), m('KXWTAMATCH', 'KXWTAMATCH-E1-DOG', 'Will Dog win?')],
  };
  const rest = {
    getSeriesFees: async () => ({ feeType: 'quadratic_with_maker_fees', multiplier: 1 }),
    getOpenMarkets: async (s: string) => bySeries[s] ?? [],
    getMarket: async () => undefined,
  } as unknown as KalshiRest;
  const audit = tmpAudit();
  const md = new MarketData(cfg, rest, undefined, new Recorder(path.join(dir, 'rec')));
  await md.refreshCatalog(now);
  for (const s of ['KXATPMATCH', 'KXWTAMATCH']) {
    assert.equal(md.markets.get(`${s}-E1-DOG`)?.kind, 'match', s);
    md.book(`${s}-E1-FAV`).applySnapshot({ bids: [{ price: 0.84, size: 100 }], asks: [{ price: 0.86, size: 100 }] }, Date.now());
    md.book(`${s}-E1-DOG`).applySnapshot({ bids: [{ price: 0.14, size: 300 }], asks: [{ price: 0.17, size: 100 }] }, Date.now());
  }
  const paper = new PaperExchange(undefined, 200, (t) => md.books.get(t), () => ({ takerMultiplier: 1, makerMultiplier: 1 }));
  const kill = new KillSwitch(path.join(dir, 'kill.json'), audit);
  const oms = new Oms({ gateway: paper, audit, statePath: path.join(dir, 'oms.json'), feesFor: (t) => md.feesFor(t), sleep: async () => undefined });
  paper.on('fill', (f) => oms.onFill(f));
  paper.on('order', (o) => oms.onExchangeOrder(o));
  const recon = new Reconciler({ gateway: paper, oms, audit, getMarket: rest.getMarket, onPersistentBreak: () => undefined });
  const engine = new Engine({ cfg, audit, alerter: new Alerter([], audit), md, gateway: paper, oms, risk: new RiskGateway(cfg.risk), kill, recon, model: MetaModel.identity(), exchangeStatus: openExchange() });
  const r = await recon.run('startup');
  engine.balance = r!.balance;
  await engine.tick();
  assert.deepEqual([...engine.tennisStatus.keys()].sort(), ['KXATPMATCH-E1', 'KXWTAMATCH-E1']);
  assert.equal(engine.isTennis('KXWTAMATCH-E1-DOG'), true);
  assert.equal(engine.status.has('KXWTAMATCH-E1-DOG'), false, 'WTA never goes through the crypto pricer');
  const open = (await paper.getOpenOrders()).map((o) => [o.ticker, o.side, o.price]).sort();
  assert.deepEqual(open, [['KXATPMATCH-E1-DOG', 'bid', 0.15], ['KXWTAMATCH-E1-DOG', 'bid', 0.15]]);
  const b = engine.tennisBudget();
  assert.ok(b.used > 0 && b.used <= b.cap, JSON.stringify(b));
});

test('engine: the quota snipe sells a tennis position whose profit after fees (entry fee in) covers the hour; the clock audits it', async () => {
  const run = async (entry: number) => {
    const dir = tmpDir();
    const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(40), DATA_DIR: dir, DOMINANCE_FEED: 'false', SPOT_FEED: 'false', PERPS_FEED: 'false', STRATEGY_SERIES: 'KXBTC15M', SESSION_EDGE_NO_ENTRY: 'false' });
    const now = Date.now();
    const m = (ticker: string, title: string): MarketInfo => ({ ticker, seriesTicker: 'KXATPMATCH', eventTicker: 'KXATPMATCH-E1', status: 'open', openTime: now - 3_600_000, closeTime: now + 6 * 3_600_000, tickSize: 0.01, title, startTime: now - 30 * 60_000, expirationTime: now - 30 * 60_000 + 14 * 86_400_000 });
    const markets = [m('KXATPMATCH-E1-FAV', 'Will Fav win?'), m('KXATPMATCH-E1-DOG', 'Will Dog win?')];
    const rest = {
      getSeriesFees: async () => ({ feeType: 'quadratic_with_maker_fees', multiplier: 1 }),
      getOpenMarkets: async (s: string) => (s === 'KXATPMATCH' ? markets : []),
      getMarket: async () => undefined,
    } as unknown as KalshiRest;
    const audit = tmpAudit();
    const md = new MarketData(cfg, rest, undefined, new Recorder(path.join(dir, 'rec')));
    await md.refreshCatalog(now);
    md.book('KXATPMATCH-E1-FAV').applySnapshot({ bids: [{ price: 0.84, size: 100 }], asks: [{ price: 0.86, size: 100 }] }, Date.now());
    md.book('KXATPMATCH-E1-DOG').applySnapshot({ bids: [{ price: 0.14, size: 300 }], asks: [{ price: 0.16, size: 100 }] }, Date.now());
    const paper = new PaperExchange(undefined, 200, (t) => md.books.get(t), () => ({ takerMultiplier: 1, makerMultiplier: 1 }));
    const kill = new KillSwitch(path.join(dir, 'kill.json'), audit);
    const oms = new Oms({ gateway: paper, audit, statePath: path.join(dir, 'oms.json'), feesFor: (t) => md.feesFor(t), sleep: async () => undefined });
    paper.on('fill', (f) => oms.onFill(f));
    paper.on('order', (o) => oms.onExchangeOrder(o));
    const recon = new Reconciler({ gateway: paper, oms, audit, getMarket: rest.getMarket, onPersistentBreak: () => undefined });
    const engine = new Engine({ cfg, audit, alerter: new Alerter([], audit), md, gateway: paper, oms, risk: new RiskGateway(cfg.risk), kill, recon, model: MetaModel.identity(), exchangeStatus: openExchange() });
    const r = await recon.run('startup');
    engine.balance = r!.balance;
    oms.adoptPosition('KXATPMATCH-E1-FAV', 50, entry);
    await engine.tick();
    return { snipes: audit.tail(500, 'pacer').map((x) => x.data as Record<string, unknown>).filter((x) => x.event === 'snipe'), status: engine.tennisStatus.get('KXATPMATCH-E1') };
  };
  // 50 from 0.70, bid 0.84: +$7.00 less the $0.48 taker fee covers the $4.50 a fresh clock needs.
  const won = await run(0.7);
  assert.equal(won.snipes.length, 1, JSON.stringify(won.status));
  assert.deepEqual([won.snipes[0].ticker, won.snipes[0].book, won.snipes[0].price, won.snipes[0].count, won.snipes[0].neededUsd], ['KXATPMATCH-E1-FAV', 'tennis', 0.84, 50, 4.5]);
  assert.equal(won.snipes[0].why, '+$6.52 net on 50 at bid 0.84 covers the $4.50 the hour needs');
  // From 0.80: +$1.52 does not: the favorite's own legs decide.
  assert.equal((await run(0.8)).snipes.length, 0);
});

test('engine: with the kill switch engaged a tennis position not in profit after fees is sold at the bid; one in profit is held', async () => {
  const run = async (entry: number, prior = false) => {
    const dir = tmpDir();
    const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(40), DATA_DIR: dir, DOMINANCE_FEED: 'false', SPOT_FEED: 'false', PERPS_FEED: 'false', STRATEGY_SERIES: 'KXBTC15M', SESSION_EDGE_NO_ENTRY: 'false' });
    const now = Date.now();
    const m = (ticker: string, title: string): MarketInfo => ({ ticker, seriesTicker: 'KXATPMATCH', eventTicker: 'KXATPMATCH-E1', status: 'open', openTime: now - 3_600_000, closeTime: now + 6 * 3_600_000, tickSize: 0.01, title, startTime: now - 30 * 60_000, expirationTime: now - 30 * 60_000 + 14 * 86_400_000 });
    const markets = [m('KXATPMATCH-E1-FAV', 'Will Fav win?'), m('KXATPMATCH-E1-DOG', 'Will Dog win?')];
    const rest = {
      getSeriesFees: async () => ({ feeType: 'quadratic_with_maker_fees', multiplier: 1 }),
      getOpenMarkets: async (s: string) => (s === 'KXATPMATCH' ? markets : []),
      getMarket: async () => undefined,
    } as unknown as KalshiRest;
    const audit = tmpAudit();
    const md = new MarketData(cfg, rest, undefined, new Recorder(path.join(dir, 'rec')));
    await md.refreshCatalog(now);
    md.book('KXATPMATCH-E1-FAV').applySnapshot({ bids: [{ price: 0.84, size: 100 }], asks: [{ price: 0.86, size: 100 }] }, Date.now());
    md.book('KXATPMATCH-E1-DOG').applySnapshot({ bids: [{ price: 0.14, size: 300 }], asks: [{ price: 0.16, size: 100 }] }, Date.now());
    const paper = new PaperExchange(undefined, 200, (t) => md.books.get(t), () => ({ takerMultiplier: 1, makerMultiplier: 1 }));
    const kill = new KillSwitch(path.join(dir, 'kill.json'), audit);
    const oms = new Oms({ gateway: paper, audit, statePath: path.join(dir, 'oms.json'), feesFor: (t) => md.feesFor(t), sleep: async () => undefined });
    paper.on('fill', (f) => oms.onFill(f));
    paper.on('order', (o) => oms.onExchangeOrder(o));
    const recon = new Reconciler({ gateway: paper, oms, audit, getMarket: rest.getMarket, onPersistentBreak: () => undefined });
    const engine = new Engine({ cfg, audit, alerter: new Alerter([], audit), md, gateway: paper, oms, risk: new RiskGateway(cfg.risk), kill, recon, model: MetaModel.identity(), exchangeStatus: openExchange() });
    const r = await recon.run('startup');
    engine.balance = r!.balance;
    const order = { ticker: 'KXATPMATCH-E1-FAV', asset: 'TENNIS', windowCloseTs: now + 6 * 3_600_000, timeInForce: 'immediate_or_cancel' as const, postOnly: false, fairValue: entry, modelId: 'm', decisionId: 'd' };
    if (prior) {
      // An earlier round trip on the same market: 50 bought at 0.70, sold at 0.86 (+$8.00 before fees).
      md.book('KXATPMATCH-E1-FAV').applySnapshot({ bids: [{ price: 0.68, size: 100 }], asks: [{ price: 0.7, size: 100 }] }, Date.now());
      await oms.submit({ ...order, side: 'bid', price: 0.7, count: 50, reduceOnly: false, purpose: 'quote' });
      md.book('KXATPMATCH-E1-FAV').applySnapshot({ bids: [{ price: 0.86, size: 100 }], asks: [{ price: 0.88, size: 100 }] }, Date.now());
      await oms.submit({ ...order, side: 'ask', price: 0.86, count: 50, reduceOnly: true, purpose: 'exit' });
      assert.equal(oms.positions.position('KXATPMATCH-E1-FAV'), 0);
    }
    // Bought on the paper exchange too (a reduce-only exit needs the position there): 50 at `entry`, then the book moves.
    md.book('KXATPMATCH-E1-FAV').applySnapshot({ bids: [{ price: entry - 0.02, size: 100 }], asks: [{ price: entry, size: 100 }] }, Date.now());
    await oms.submit({ ticker: 'KXATPMATCH-E1-FAV', asset: 'TENNIS', windowCloseTs: now + 6 * 3_600_000, side: 'bid', price: entry, count: 50, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'quote', fairValue: entry, modelId: 'm', decisionId: 'd' });
    md.book('KXATPMATCH-E1-FAV').applySnapshot({ bids: [{ price: 0.84, size: 100 }], asks: [{ price: 0.86, size: 100 }] }, Date.now());
    assert.equal(oms.positions.position('KXATPMATCH-E1-FAV'), 50);
    await kill.engage('test', 'manual');
    await engine.tick();
    await engine.tick();
    const exits = audit.tail(500, 'decision').map((x) => x.data as Record<string, unknown>).filter((x) => x.leg === 'kill_exit');
    return { position: oms.positions.position('KXATPMATCH-E1-FAV'), exits, rejects: audit.tail(500, 'risk_reject').length };
  };
  // 50 from 0.90, bid 0.84: -$3.00 and the fees: sold at the bid, once (the second tick finds it flat).
  const lost = await run(0.9);
  assert.equal(lost.position, 0, JSON.stringify(lost));
  assert.equal(lost.exits.length, 1);
  assert.deepEqual([lost.exits[0].price, lost.exits[0].count, lost.exits[0].side], [0.84, 50, 'ask']);
  assert.match(String(lost.exits[0].why), /^kill switch engaged: -\$3\.\d\d after fees at bid 0\.84, not in profit, not held to settlement$/);
  assert.equal(lost.rejects, 0);
  // From 0.70 it is in profit after fees: held to settlement as the rule allows; nothing is sent.
  const won = await run(0.7);
  assert.equal(won.position, 50);
  assert.equal(won.exits.length, 0);
  // An earlier winning round trip on the market does not hide the open contracts' loss: they are judged on their own cost.
  const again = await run(0.9, true);
  assert.equal(again.position, 0, JSON.stringify(again));
  assert.match(String(again.exits[0]?.why), /^kill switch engaged: -\$3\.\d\d after fees at bid 0\.84/);
});

import fs from 'fs';
import { engineTennisRules, runTennisBacktest } from '../research/tennisBacktest';

/** One match: the underdog is bought pre-start at 0.15, bounces to 0.30 (a wall at 0.28), slips to 0.27 and then 0.19. */
function writeBounceMatch(): string {
  const dir = path.join(tmpDir(), 'rec');
  fs.mkdirSync(dir, { recursive: true });
  const t0 = Date.parse('2026-10-01T12:00:00Z');
  const ev: any[] = [];
  const mkt = (ticker: string) => ({ t: t0, k: 'market', ticker, series: 'KXATPMATCH', asset: 'TENNIS', openTime: t0 - 3_600_000, closeTime: t0 + 4 * 3_600_000, kind: 'match', event: 'KXATPMATCH-E', tickSize: 0.01, startTime: t0 + 10 * 60_000 });
  ev.push(mkt('KXATPMATCH-E-DOG'), mkt('KXATPMATCH-E-FAV'));
  for (let s = 0; s <= 3 * 3600; s += 5) {
    const t = t0 + s * 1000;
    // pre-start 0.14/0.17 -> bounce past the 0.21 target -> run to 0.30 (wall at 0.28) -> slip to 0.27 -> 0.19.
    const dog = s < 1800 ? { bids: [{ price: 0.14, size: 300 }], asks: [{ price: 0.17, size: 100 }] }
      : s < 3600 ? { bids: [{ price: 0.22, size: 300 }], asks: [{ price: 0.24, size: 100 }] }
      : s < 5400 ? { bids: [{ price: 0.30, size: 300 }, { price: 0.28, size: 400 }], asks: [{ price: 0.32, size: 100 }] }
      : s < 5460 ? { bids: [{ price: 0.27, size: 300 }], asks: [{ price: 0.29, size: 100 }] }
      : { bids: [{ price: 0.19, size: 300 }], asks: [{ price: 0.21, size: 100 }] };
    ev.push({ t, k: 'book', ticker: 'KXATPMATCH-E-DOG', ...dog });
    ev.push({ t, k: 'book', ticker: 'KXATPMATCH-E-FAV', bids: [{ price: 1 - dog.asks[0].price, size: 100 }], asks: [{ price: 1 - dog.bids[0].price, size: 100 }] });
    if (s === 60) ev.push({ t, k: 'trade', ticker: 'KXATPMATCH-E-DOG', price: 0.15, count: 1000, takerSide: 'no', ts: t });
  }
  ev.push({ t: t0 + 3 * 3600 * 1000 + 1000, k: 'result', ticker: 'KXATPMATCH-E-DOG', result: 'no' }, { t: t0 + 3 * 3600 * 1000 + 1000, k: 'result', ticker: 'KXATPMATCH-E-FAV', result: 'yes' });
  ev.push({ t: t0 + 3 * 3600 * 1000 + 10_000, k: 'book', ticker: 'KXATPMATCH-E-DOG', bids: [], asks: [] });
  fs.writeFileSync(path.join(dir, 'md-2026-10-01.jsonl'), ev.map((e) => JSON.stringify(e)).join('\n') + '\n');
  return dir;
}

test('tennis backtest: underdog bought pre-start, trailed up the bounce, sold when it slipped below the stop', async () => {
  const r = await runTennisBacktest(writeBounceMatch(), T, 200);
  assert.equal(r.matches, 1);
  assert.ok(r.byLeg.underdog_entry?.fills > 0, JSON.stringify(r.byLeg));
  assert.ok(r.byLeg.underdog_trail?.fills > 0, JSON.stringify(r.byLeg));
  assert.ok(r.pnl > 0, `pnl ${r.pnl}`);
  assert.ok(r.maxTennisRisk <= 0.25 * 200 + 1e-9);
});

test('tennis backtest applies the engine\'s profit rules: the quota snipe sells the bounce once its profit covers the hour', async () => {
  const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32) });
  const rules = engineTennisRules(cfg);
  assert.equal(rules.settleFrac, cfg.tennis.settleFrac);
  assert.deepEqual([rules.endLoserCut, rules.endEntryMargin], [cfg.tennis.endLoserCut, cfg.tennis.endEntryMargin]);
  assert.equal(rules.pacer, cfg.strategy.pacer);
  assert.equal(engineTennisRules(cfg, false).pacer, undefined);
  const dir = writeBounceMatch();
  const plain = await runTennisBacktest(dir, T, 200);
  assert.equal(plain.byLeg.quota_snipe, undefined, 'no rules: the legs alone');
  // A $3 hour, no floor: the bounce to 0.22 is up about $3.65 after fees on 65.62 contracts, so the snipe sells it there.
  const pacer = { ...cfg.strategy.pacer, enabled: true, hourlyUsd: 3 };
  const sniped = await runTennisBacktest(dir, T, 200, undefined, { ...rules, pacer, floorMode: 'off' });
  assert.ok(sniped.byLeg.quota_snipe?.fills > 0, JSON.stringify(sniped.byLeg));
  assert.equal(sniped.byLeg.underdog_trail, undefined, 'the snipe sold before the trail did');
  assert.ok(sniped.pnl > 3 - 1e-9, `snipe pnl ${sniped.pnl}`);
  // The default $4.50 hour asks more than the bounce made: the legs trade as without the rules.
  const fullHour = await runTennisBacktest(dir, T, 200, undefined, { ...rules, pacer: { ...cfg.strategy.pacer, enabled: true }, floorMode: 'off' });
  assert.equal(fullHour.byLeg.quota_snipe, undefined, JSON.stringify(fullHour.byLeg));
  assert.ok(Math.abs(fullHour.pnl - plain.pnl) < 1e-9);
});

test('entries need tennis confluence: 1 signal pre-match, 2 live; thresholds are configurable', () => {
  const start = t0 + 10 * 60_000;
  const snap = (e: string, dog: MatchMarket, now = t0) => ({ event: e, now, startTime: start, closeTime: t0 + 86_400_000, markets: [mk(`${e}-FAV`, 0.84, 0.86), { ...dog, ticker: `${e}-DOG` }] });
  // Flat, balanced book: no signal, no entry.
  const flat = decideMatch(new MatchTracker('A', T), snap('A', mk('x', 0.14, 0.17)), T, budget);
  assert.equal(flat.plans.length, 0);
  assert.ok(flat.notes.some((n) => n.includes('waits for confluence: 0/4 < 1 (pre-match)')), JSON.stringify(flat.notes));
  // The same book passes when the pre-match gate is configured to 0.
  assert.equal(decideMatch(new MatchTracker('B', T), snap('B', mk('x', 0.14, 0.17)), { ...T, entryMinSignalsPre: 0 }, budget).plans[0]?.leg, 'underdog_entry');
  // Depth threshold: a 300/100 book (imbalance 0.5) passes the default 0.2, not a 0.6 threshold.
  assert.equal(decideMatch(new MatchTracker('C', T), snap('C', mkb('x', 0.14, 0.17, 300, 100, t0)), T, budget).plans.length, 1);
  assert.equal(decideMatch(new MatchTracker('D', T), snap('D', mkb('x', 0.14, 0.17, 300, 100, t0)), { ...T, confDepth: 0.6 }, budget).plans.length, 0);
  // Live (just started): one signal is not enough, two are.
  const live = (e: string, flow?: number) => {
    const tr = new MatchTracker(e, T);
    tr.liveSince = start;
    return decideMatch(tr, { ...snap(e, mkb('x', 0.14, 0.17, 300, 100, start + 60_000, { flow }), start + 60_000) }, T, budget);
  };
  const one = live('L1');
  assert.equal(one.plans.length, 0);
  assert.ok(one.notes.some((n) => n.includes('1/4 < 2 (live)')), JSON.stringify(one.notes));
  assert.equal(live('L2', 0.5).plans[0]?.leg, 'underdog_entry');
  // The favorite re-entry has its own gate.
  assert.equal(T.favEntryMinSignals, 2);
});

test('underdog window opens at most 30 minutes before the start; early entries get full size, later ones taper', () => {
  assert.equal(T.preStartMin, 30);
  assert.throws(() => loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), TENNIS_PRE_START_MIN: '60' }));
  const at = (minsBefore: number) => new MatchTracker('P', T).observe({ event: 'P', now: t0, startTime: t0 + minsBefore * 60_000, closeTime: t0 + 86_400_000, markets: [mk('P-A', 0.84, 0.86), mk('P-B', 0.14, 0.17)] });
  assert.equal(at(29), 'underdog_window');
  assert.equal(at(31), 'pre');
  const sized = (minIn: number) => {
    const tr = new MatchTracker('S', T);
    tr.liveSince = t0;
    const now = t0 + minIn * 60_000;
    const out = decideMatch(tr, { event: 'S', now, startTime: t0, closeTime: t0 + 86_400_000, markets: [mk('S-FAV', 0.84, 0.86), mkb('S-DOG', 0.14, 0.17, 300, 100, now, { flow: 0.5 })] }, T, budget);
    return out.plans[0]?.count ?? 0;
  };
  const full = sized(0);
  assert.ok(full > 0);
  assert.equal(sized(T.earlyFullSizeMin), full, 'full size through the first minutes');
  const later = sized(T.entryWindowMin);
  assert.ok(later < full && later >= Math.floor(full * 0.5 * 100) / 100 - 0.01, `${later} vs ${full}`);
});

test('tennis profit exits never sell under the break-even after fees (entry + 1 tick can lose to the taker fee)', () => {
  // 100 held at 0.15 with a 0.0023 maker entry fee each: at 0.16 the taker fee (0.95) beats the 0.77 gain, at 0.17 it does not.
  const cost = 0.1523, be = breakEvenExit(100, cost)!;
  assert.ok(be > 0.16 && be < 0.17, `break-even ${be}`);
  assert.ok(100 * (0.16 - cost) - orderFee(100, 0.16, true) < 0 && 100 * (be - cost) - orderFee(100, be, true) >= -1e-9);
  const run = (bid: number) => {
    const tr = new MatchTracker('U', T);
    tr.liveSince = t0; tr.underdogTicker = 'U-DOG';
    tr.progress = () => 0.4;
    const now = t0 + 30 * 60_000;
    return decideMatch(tr, { event: 'U', now, startTime: t0, closeTime: t0 + 86_400_000, markets: [mk('U-FAV', 1 - bid - 0.02, 1 - bid), mkb('U-DOG', bid, bid + 0.02, 300, 100, now, { position: 100, avgEntry: 0.15, breakEven: be })] }, T, budget);
  };
  assert.equal(run(0.16).plans.length, 0, 'entry + 1c nets a loss after fees: hold');
  assert.deepEqual([run(0.17).plans[0]?.leg, run(0.17).plans[0]?.price], ['underdog_late', 0.17]);
});

test('engine: the tennis profit exits get the break-even after fees from the position (entry fee in): no underdog_late sale one tick over the entry at a loss', async () => {
  const run = async (bid: number) => {
    const dir = tmpDir();
    const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(40), DATA_DIR: dir, DOMINANCE_FEED: 'false', SPOT_FEED: 'false', PERPS_FEED: 'false', STRATEGY_SERIES: 'KXBTC15M', SESSION_EDGE_NO_ENTRY: 'false' });
    const now = Date.now();
    // Started 2 hours ago, no score feed: a fresh tracker's information clock reads 0 on its first tick, so the progress is half
    // the time clock, about 0.44: past underdogLateProgress (0.35), short of underdogCutProgress (0.6) and of the last 30%
    // (settleFrac: the ride and the end cut), so of the underdog's exits only underdog_late (or the trail from 0.21) can sell.
    const m = (ticker: string, title: string): MarketInfo => ({ ticker, seriesTicker: 'KXATPMATCH', eventTicker: 'KXATPMATCH-E1', status: 'open', openTime: now - 3 * 3_600_000, closeTime: now + 6 * 3_600_000, tickSize: 0.01, title, startTime: now - 120 * 60_000, expirationTime: now - 120 * 60_000 + 14 * 86_400_000 });
    const markets = [m('KXATPMATCH-E1-FAV', 'Will Fav win?'), m('KXATPMATCH-E1-DOG', 'Will Dog win?')];
    const rest = {
      getSeriesFees: async () => ({ feeType: 'quadratic_with_maker_fees', multiplier: 1 }),
      getOpenMarkets: async (s: string) => (s === 'KXATPMATCH' ? markets : []),
      getMarket: async () => undefined,
    } as unknown as KalshiRest;
    const audit = tmpAudit();
    const md = new MarketData(cfg, rest, undefined, new Recorder(path.join(dir, 'rec')));
    await md.refreshCatalog(now);
    md.book('KXATPMATCH-E1-FAV').applySnapshot({ bids: [{ price: 0.82, size: 100 }], asks: [{ price: 0.84, size: 100 }] }, Date.now());
    md.book('KXATPMATCH-E1-DOG').applySnapshot({ bids: [{ price: 0.13, size: 300 }], asks: [{ price: 0.15, size: 300 }] }, Date.now());
    const paper = new PaperExchange(undefined, 200, (t) => md.books.get(t), () => ({ takerMultiplier: 1, makerMultiplier: 1 }));
    const kill = new KillSwitch(path.join(dir, 'kill.json'), audit);
    const oms = new Oms({ gateway: paper, audit, statePath: path.join(dir, 'oms.json'), feesFor: (t) => md.feesFor(t), sleep: async () => undefined });
    paper.on('fill', (f) => oms.onFill(f));
    paper.on('order', (o) => oms.onExchangeOrder(o));
    const recon = new Reconciler({ gateway: paper, oms, audit, getMarket: rest.getMarket, onPersistentBreak: () => undefined });
    const engine = new Engine({ cfg, audit, alerter: new Alerter([], audit), md, gateway: paper, oms, risk: new RiskGateway(cfg.risk), kill, recon, model: MetaModel.identity(), exchangeStatus: openExchange() });
    const r = await recon.run('startup');
    engine.balance = r!.balance;
    // 100 bought at 0.15 on the paper exchange (not adoptPosition, which books no fee; the reduce-only exit also needs the
    // position there): a taker fill paying the real $0.90 entry fee, so the cost is 0.159 a contract.
    await oms.submit({ ticker: 'KXATPMATCH-E1-DOG', asset: 'TENNIS', windowCloseTs: now + 6 * 3_600_000, side: 'bid', price: 0.15, count: 100, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'quote', fairValue: 0.15, modelId: 'm', decisionId: 'd' });
    const pos = oms.positions.get('KXATPMATCH-E1-DOG')!;
    assert.deepEqual([pos.yes, Math.round(pos.fees * 100) / 100], [100, 0.9]);
    md.book('KXATPMATCH-E1-DOG').applySnapshot({ bids: [{ price: bid, size: 300 }], asks: [{ price: Math.round((bid + 0.02) * 100) / 100, size: 100 }] }, Date.now());
    await engine.tick();
    const sent = audit.tail(500, 'decision').map((x) => x.data as Record<string, unknown>).filter((x) => x.strategy === 'tennis');
    return { position: oms.positions.position('KXATPMATCH-E1-DOG'), sent, status: engine.tennisStatus.get('KXATPMATCH-E1'), rejects: audit.tail(500, 'risk_reject').length };
  };
  // The break-even after the taker exit fee on the 0.159 cost is 0.169, 0.17 on the tick. Bid 0.16 is entry + 1 tick, the
  // stand-alone floor: 100 x 0.001 - $0.95 exit fee = -$0.85 (without the entry fee it would net +$0.05, so the engine's cost
  // basis must carry the fee too). Held: nothing is sent, the trail waits for 0.21.
  const held = await run(0.16);
  assert.ok(held.status && held.status.progress >= T.underdogLateProgress && held.status.progress < T.underdogCutProgress, JSON.stringify(held.status));
  assert.deepEqual(held.sent.map((x) => x.leg), [], JSON.stringify(held.sent));
  assert.equal(held.position, 100);
  assert.ok(held.status!.notes.includes('underdog_trail: holding, hunt starts at 0.21 (bid 0.16)'), JSON.stringify(held.status!.notes));
  // At the break-even (bid 0.17: +$0.11 after both fees) the late exit goes out and fills.
  const sold = await run(0.17);
  assert.deepEqual(sold.sent.map((x) => [x.leg, x.side, x.price, x.count]), [['underdog_late', 'ask', 0.17, 100]], JSON.stringify(sold.status));
  assert.equal(sold.position, 0);
  assert.equal(sold.rejects, 0);
});

test('underdogs lose late: past 35% of the match take any profit, past 60% sell regardless', () => {
  const run = (prog: number, bid: number, cfg = T) => {
    const tr = new MatchTracker('U', cfg);
    tr.liveSince = t0; tr.underdogTicker = 'U-DOG';
    tr.progress = () => prog; // progress itself is tested with the scoring model
    const now = t0 + 30 * 60_000;
    return decideMatch(tr, { event: 'U', now, startTime: t0, closeTime: t0 + 86_400_000, markets: [mk('U-FAV', 1 - bid - 0.02, 1 - bid), mkb('U-DOG', bid, bid + 0.02, 300, 100, now, { position: 100, avgEntry: 0.15 })] }, cfg, budget);
  };
  // Early: +2c is below the target, keep riding.
  assert.equal(run(0.2, 0.17).plans.length, 0);
  // 40% in: +2c is a profit the bids can fill -> take it.
  const late = run(0.4, 0.17);
  assert.deepEqual([late.plans[0]?.leg, late.plans[0]?.price, late.plans[0]?.reduceOnly], ['underdog_late', 0.17, true]);
  // 40% in but under water: hold (no forced loss before the cut).
  assert.equal(run(0.4, 0.13).plans.length, 0);
  // 65% in: sell at the bid even at a loss.
  const cut = run(0.65, 0.10);
  assert.deepEqual([cut.plans[0]?.leg, cut.plans[0]?.price], ['underdog_cut', 0.10]);
  // The cut can be switched off.
  assert.equal(run(0.65, 0.10, { ...T, underdogCutProgress: 0 }).plans.length, 0);
});

test('live tennis scores: a match that has not started spends no calls of the daily budget', async () => {
  const { TennisScoreClient } = await import('../bot/tennis/liveTennisApi');
  const run = async (startInMin: number) => {
    const dir = tmpDir();
    const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(40), DATA_DIR: dir, DOMINANCE_FEED: 'false', SPOT_FEED: 'false', PERPS_FEED: 'false', STRATEGY_SERIES: 'KXBTC15M', SESSION_EDGE_NO_ENTRY: 'false', TENNIS_SCORE_FEED: 'livetennis' });
    const now = Date.now();
    const m = (ticker: string, title: string): MarketInfo => ({ ticker, seriesTicker: 'KXATPMATCH', eventTicker: 'KXATPMATCH-E1', status: 'open', openTime: now - 3_600_000, closeTime: now + 6 * 3_600_000, tickSize: 0.01, title, startTime: now + startInMin * 60_000, expirationTime: now + startInMin * 60_000 + 14 * 86_400_000 });
    const markets = [m('KXATPMATCH-E1-FAV', 'Will Fav win?'), m('KXATPMATCH-E1-DOG', 'Will Dog win?')];
    const rest = { getSeriesFees: async () => ({ feeType: 'quadratic_with_maker_fees', multiplier: 1 }), getOpenMarkets: async (s: string) => (s === 'KXATPMATCH' ? markets : []), getMarket: async () => undefined } as unknown as KalshiRest;
    const audit = tmpAudit();
    const md = new MarketData(cfg, rest, undefined, new Recorder(path.join(dir, 'rec')));
    await md.refreshCatalog(now);
    md.book('KXATPMATCH-E1-FAV').applySnapshot({ bids: [{ price: 0.84, size: 100 }], asks: [{ price: 0.86, size: 100 }] }, Date.now());
    md.book('KXATPMATCH-E1-DOG').applySnapshot({ bids: [{ price: 0.14, size: 300 }], asks: [{ price: 0.17, size: 100 }] }, Date.now());
    const paper = new PaperExchange(undefined, 200, (t) => md.books.get(t), () => ({ takerMultiplier: 1, makerMultiplier: 1 }));
    const oms = new Oms({ gateway: paper, audit, statePath: path.join(dir, 'oms.json'), feesFor: (t) => md.feesFor(t), sleep: async () => undefined });
    const recon = new Reconciler({ gateway: paper, oms, audit, getMarket: rest.getMarket, onPersistentBreak: () => undefined });
    let calls = 0;
    const tennisScores = new TennisScoreClient({ apiKey: 'k', fetchFn: (async () => { calls++; return new Response(JSON.stringify({ data: [], meta: { offset: 0, limit: 200, has_more: false } }), { status: 200 }); }) as unknown as typeof fetch });
    const engine = new Engine({ cfg, audit, alerter: new Alerter([], audit), md, gateway: paper, oms, risk: new RiskGateway(cfg.risk), kill: new KillSwitch(path.join(dir, 'kill.json'), audit), recon, model: MetaModel.identity(), exchangeStatus: openExchange(), tennisScores });
    engine.balance = (await recon.run('startup'))!.balance;
    await engine.tick();
    return { calls, raw: engine.tennisStatus.get('KXATPMATCH-E1')?.scoreRaw };
  };
  const later = await run(120);
  assert.equal(later.calls, 0, 'starts in 2 hours: no call');
  assert.match(String(later.raw), /no score before the start/);
  assert.equal((await run(5)).calls, 1, 'about to start: the slate is read');
});

test('live tennis scores: a slate match only one title names gives no score; the one both titles name gives a named score', async () => {
  const { TennisScoreClient } = await import('../bot/tennis/liveTennisApi');
  const live = (id: number, p1: string, p2: string, sets: [number, number], games: [number[], number[]]) =>
    ({ id, status: 'live', tour: 'WTA', sets, games, points: ['15', '0'], server: 1, is_tiebreak: false, player1: { name: p1 }, player2: { name: p2 } });
  // Erika Andreeva's match, a set all and 5-5: its progress would read about 90% of Mirra Andreeva's match.
  const sister = live(1, 'Erika Andreeva', 'Anna Blinkova', [1, 1], [[6, 3, 5], [3, 6, 5]]);
  const real = live(2, 'Coco Gauff', 'Mirra Andreeva', [0, 0], [[1], [0]]);
  const run = async (slate: object[]) => {
    const dir = tmpDir();
    const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(40), DATA_DIR: dir, DOMINANCE_FEED: 'false', SPOT_FEED: 'false', PERPS_FEED: 'false', STRATEGY_SERIES: 'KXBTC15M', SESSION_EDGE_NO_ENTRY: 'false', TENNIS_SCORE_FEED: 'livetennis' });
    const now = Date.now();
    const m = (ticker: string, title: string): MarketInfo => ({ ticker, seriesTicker: 'KXATPMATCH', eventTicker: 'KXATPMATCH-E1', status: 'open', openTime: now - 3_600_000, closeTime: now + 6 * 3_600_000, tickSize: 0.01, title, startTime: now - 10 * 60_000, expirationTime: now - 10 * 60_000 + 14 * 86_400_000 });
    // Titles with surnames only, so the sister's match is found by one of them (with first names it would not be found).
    const markets = [m('KXATPMATCH-E1-AND', 'Will Andreeva win the Andreeva vs Gauff : Wuhan match?'), m('KXATPMATCH-E1-GAU', 'Will Gauff win the Andreeva vs Gauff : Wuhan match?')];
    const rest = { getSeriesFees: async () => ({ feeType: 'quadratic_with_maker_fees', multiplier: 1 }), getOpenMarkets: async (s: string) => (s === 'KXATPMATCH' ? markets : []), getMarket: async () => undefined } as unknown as KalshiRest;
    const audit = tmpAudit();
    const md = new MarketData(cfg, rest, undefined, new Recorder(path.join(dir, 'rec')));
    await md.refreshCatalog(now);
    md.book('KXATPMATCH-E1-AND').applySnapshot({ bids: [{ price: 0.6, size: 100 }], asks: [{ price: 0.62, size: 100 }] }, Date.now());
    md.book('KXATPMATCH-E1-GAU').applySnapshot({ bids: [{ price: 0.38, size: 100 }], asks: [{ price: 0.4, size: 100 }] }, Date.now());
    const paper = new PaperExchange(undefined, 200, (t) => md.books.get(t), () => ({ takerMultiplier: 1, makerMultiplier: 1 }));
    const oms = new Oms({ gateway: paper, audit, statePath: path.join(dir, 'oms.json'), feesFor: (t) => md.feesFor(t), sleep: async () => undefined });
    const recon = new Reconciler({ gateway: paper, oms, audit, getMarket: rest.getMarket, onPersistentBreak: () => undefined });
    const tennisScores = new TennisScoreClient({ apiKey: 'k', fetchFn: (async () => new Response(JSON.stringify({ data: slate, meta: { offset: 0, limit: 200, has_more: false } }), { status: 200 })) as unknown as typeof fetch });
    const engine = new Engine({ cfg, audit, alerter: new Alerter([], audit), md, gateway: paper, oms, risk: new RiskGateway(cfg.risk), kill: new KillSwitch(path.join(dir, 'kill.json'), audit), recon, model: MetaModel.identity(), exchangeStatus: openExchange(), tennisScores });
    engine.balance = (await recon.run('startup'))!.balance;
    await engine.tick();
    const tr = (engine as unknown as { matches: Map<string, MatchTracker> }).matches.get('KXATPMATCH-E1')!;
    return { tr, raw: engine.tennisStatus.get('KXATPMATCH-E1')?.scoreRaw };
  };
  // Only the sister's match live: found by one surname, not named. No score reaches the tracker, so no progress from it.
  const one = await run([sister]);
  assert.ok(one.tr, 'the match is tracked');
  assert.equal(one.tr.score, undefined, JSON.stringify(one.tr.score));
  assert.equal(one.tr.scoreOriented, false);
  assert.match(String(one.raw), /only one of the two players matched a live match/);
  // Both live, the sister's first: the match both titles name is taken, its score oriented to Mirra Andreeva (the event's
  // first market, API player two): 0-1 in games.
  const both = await run([sister, real]);
  assert.deepEqual(both.tr.score && [both.tr.score.setsA, both.tr.score.setsB, both.tr.score.gamesA, both.tr.score.gamesB], [0, 0, 0, 1]);
  assert.equal(both.tr.scoreOriented, true);
});

test('tennis loser cut by the match\'s progress (Steven, Nov 12): 20c at the start, 10c at 60%, 3c from 85%, and the end cut in the last 10%', () => {
  assert.deepEqual([T.loserCutOpen, T.loserCut, T.loserCutLate, T.endCutFrac, T.probTurn], [0.2, 0.1, 0.03, 0.1, 0.05]);
  const cfg = (e: Record<string, string>) => loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), ...e }).tennis;
  // Ends left unset follow the middle without crossing it; ends set by hand must stay on their side.
  assert.deepEqual([cfg({ TENNIS_LOSER_CUT_C: '15' }).loserCutOpen, cfg({ TENNIS_LOSER_CUT_C: '15' }).loserCutLate], [0.2, 0.03]);
  assert.deepEqual([cfg({ TENNIS_LOSER_CUT_C: '25' }).loserCutOpen, cfg({ TENNIS_LOSER_CUT_C: '2' }).loserCutLate], [0.25, 0.02]);
  assert.equal(cfg({ TENNIS_LOSER_CUT_C: '0' }).loserCut, 0);
  // A fraction of a cent: unset ends follow it unrounded; an end set by hand goes down to 0.01c.
  const frac = cfg({ TENNIS_LOSER_CUT_C: '0.5' });
  assert.deepEqual([frac.loserCutOpen, frac.loserCut, frac.loserCutLate], [0.2, 0.005, 0.005]);
  assert.equal(cfg({ TENNIS_LOSER_CUT_C: '2.5' }).loserCutLate, 0.025);
  assert.equal(cfg({ TENNIS_LOSER_CUT_C: '0.5', TENNIS_LOSER_CUT_LATE_C: '0.25' }).loserCutLate, 0.0025);
  assert.throws(() => cfg({ TENNIS_LOSER_CUT_LATE_C: '0' }), /TENNIS_LOSER_CUT_LATE_C=0 must be a number in \[0.01, 99\]/);
  assert.throws(() => cfg({ TENNIS_LOSER_CUT_OPEN_C: '5' }), /TENNIS_LOSER_CUT_OPEN_C=5 must be at least TENNIS_LOSER_CUT_C=10/);
  assert.throws(() => cfg({ TENNIS_LOSER_CUT_LATE_C: '12' }), /TENNIS_LOSER_CUT_LATE_C=12 must be at most TENNIS_LOSER_CUT_C=10/);
  // The line, dollars a contract under the entry, by the share of the match done.
  const line = { loserCut: T.loserCut, loserCutOpen: T.loserCutOpen, loserCutLate: T.loserCutLate };
  for (const [done, want] of [[0, 0.2], [0.3, 0.15], [0.6, 0.1], [0.725, 0.065], [0.85, 0.03], [0.95, 0.03], [-1, 0.2], [NaN, 0.2]]) {
    assert.ok(Math.abs(tennisLoserCutAt(line, done) - want) < 1e-9, `${done}: ${tennisLoserCutAt(line, done)} vs ${want}`);
  }
  assert.equal(tennisLoserCutAt({ loserCut: 0 }, 0.5), 0, 'off');
  assert.equal(tennisLoserCutAt({ loserCut: 0.1 }, 0.1), 0.1, 'ends unset: flat');

  const rules = { pacerUsd: 4.5, settleFrac: T.settleFrac, endLoserCut: true, endEntryMargin: T.endEntryMargin, endCutFrac: T.endCutFrac, ...line };
  // A favorite held from 0.80, 30 contracts (no loss exit of its own: TENNIS_FAV_STOP_CENTS is 0), the progress held 3 minutes.
  const fav = (prog: number, bid: number, net: number, r: object = rules) => {
    const tr = new MatchTracker('P', T);
    tr.progress = () => prog;
    const at = (now: number) => decideMatch(tr, { event: 'P', now, startTime: t0, closeTime: t0 + 86_400_000, markets: [mk('P-FAV', bid, bid + 0.02, { position: 30, avgEntry: 0.8, netAtBid: net }), mk('P-DOG', 1 - bid - 0.02, 1 - bid)] }, T, budget, 0.01, r);
    for (let k = 6; k > 0; k--) at(t0 + 3_600_000 - k * 30_000);
    return at(t0 + 3_600_000);
  };
  // 30% done: the line is 15c. 14c under the entry is held; 15c is sold at the bid.
  assert.equal(fav(0.3, 0.66, -4.5).plans.length, 0);
  const cut = fav(0.3, 0.65, -4.8).plans;
  assert.equal(cut.length, 1, JSON.stringify(cut));
  assert.deepEqual([cut[0].leg, cut[0].side, cut[0].price, cut[0].count, cut[0].reduceOnly, cut[0].postOnly, cut[0].timeInForce], ['loser_cut', 'ask', 0.65, 30, true, false, 'immediate_or_cancel']);
  assert.equal(cut[0].why, 'loser cut: bid 0.65 is 15.0c under the 0.8 entry, the cut is 15.0c at match 30% done (-$4.80 after fees)');
  // 75% done (inside the 30% where winners ride, not in profit): the line is 5.8c. The end cut no longer sells it at 70%.
  assert.equal(fav(0.75, 0.79, -0.8).plans.length, 0, 'a 1c loss at 75% is held');
  assert.equal(fav(0.75, 0.75, -1.8).plans.length, 0, 'a 5c loss at 75% is held');
  const late = fav(0.75, 0.74, -2.1).plans;
  assert.equal(late[0]?.leg, 'loser_cut', JSON.stringify(late));
  assert.equal(late[0]?.why, 'loser cut: bid 0.74 is 6.0c under the 0.8 entry, the cut is 5.8c at match 75% done (-$2.10 after fees)');
  // From 85%: 3c.
  assert.equal(fav(0.87, 0.78, -0.9).plans.length, 0);
  assert.equal(fav(0.87, 0.76, -1.5).plans[0]?.leg, 'loser_cut');
  // The last 10%: anything not in profit after fees is sold at the bid, break-even included.
  const end = fav(0.9, 0.79, -0.8).plans;
  assert.equal(end[0]?.leg, 'end_cut', JSON.stringify(end));
  assert.equal(end[0]?.why, 'match 90% done (its last 10%), -$0.80 after fees at bid 0.79: not in profit, not held to settlement');
  assert.equal(fav(0.9, 0.81, 0).plans[0]?.leg, 'end_cut');
  // In profit it rides; with the cut off the loss is the legs' (none here).
  assert.equal(fav(0.75, 0.84, 1).plans.length, 0);
  assert.equal(fav(0.3, 0.5, -9, { ...rules, loserCut: 0 }).plans.length, 0);
  // Without endCutFrac (the research backtest before Nov 12, an old caller) the end cut keeps settleFrac's 30%.
  assert.equal(fav(0.75, 0.79, -0.8, { ...rules, endCutFrac: undefined }).plans[0]?.leg, 'end_cut');

  // No new entry from 85% (the last 10% less TENNIS_END_ENTRY_MARGIN): a favorite is still bought at 80%.
  const entry = (prog: number, high = 0) => {
    const tr = new MatchTracker('Q', T);
    tr.liveSince = t0;
    tr.progress = () => prog;
    tr.progressHigh = high;
    let now = t0 + 60 * 60_000;
    const snap = () => ({ event: 'Q', now, closeTime: t0 + 86_400_000, markets: [mkb('Q-A', 0.84, 0.86, 300, 100, now, { flow: 0.5 }), mk('Q-B', 0.14, 0.16)] });
    for (let i = 0; i < 12; i++) { decideMatch(tr, snap(), T, budget, 0.01, rules); now += 30_000; }
    return decideMatch(tr, snap(), T, budget, 0.01, rules);
  };
  assert.equal(entry(0.8).plans[0]?.leg, 'fav_entry');
  const none = entry(0.86);
  assert.equal(none.plans.length, 0, JSON.stringify(none.plans));
  assert.ok(none.notes.some((n) => n.includes('its last 10% from 90%') && n.includes('no new entry (fav_entry)')), JSON.stringify(none.notes));
});

test('tennis: a position riding to settlement in profit is sold, still in profit, once the win chance turns (TENNIS_PROB_TURN, Steven Nov 12)', () => {
  const rules = { pacerUsd: 4.5, settleFrac: T.settleFrac, endLoserCut: true, endEntryMargin: T.endEntryMargin, endCutFrac: T.endCutFrac,
    loserCut: T.loserCut, loserCutOpen: T.loserCutOpen, loserCutLate: T.loserCutLate, probTurn: T.probTurn };
  type Score = { setsA: number; setsB: number; gamesA: number; gamesB: number; pointsA: number; pointsB: number };
  const ride = (prog: number | (() => number), r: object = rules) => {
    const tr = new MatchTracker('R', T);
    tr.progress = typeof prog === 'function' ? prog : () => prog;
    const clock = { now: t0 + 3_600_000 };
    const at = (bid: number, net: number, score?: Score, extra: { scoreAt?: number; scoreOriented?: boolean } = {}) => {
      const o = decideMatch(tr, { event: 'R', now: clock.now, startTime: t0, closeTime: t0 + 86_400_000, score, ...extra, markets: [mk('R-FAV', bid, bid + 0.02, { position: 30, avgEntry: 0.8, netAtBid: net }), mk('R-DOG', 1 - bid - 0.02, 1 - bid)] }, T, budget, 0.01, r);
      clock.now += 30_000;
      return o;
    };
    return { tr, at, clock };
  };
  // Without a score the win chance is the market's: the two books' mid, the bid + 1c here.
  const a = ride(0.8);
  for (const b of [0.88, 0.9, 0.92]) assert.equal(a.at(b, 2).plans.length, 0, 'rides');
  assert.ok(Math.abs(a.tr.rides.get('R-FAV')!.market! - 0.93) < 1e-9);
  const held = a.at(0.89, 1.6);
  assert.equal(held.plans.length, 0, 'down 3 points: still riding');
  assert.ok(held.notes.some((n) => n.includes('riding to settlement, win chance 90% by the market (best 93%)')), JSON.stringify(held.notes));
  const turn = a.at(0.87, 1).plans;
  assert.equal(turn.length, 1, JSON.stringify(turn));
  assert.deepEqual([turn[0].leg, turn[0].side, turn[0].price, turn[0].count, turn[0].reduceOnly, turn[0].timeInForce], ['prob_turn', 'ask', 0.87, 30, true, 'immediate_or_cancel']);
  assert.equal(turn[0].why, 'riding in profit (match 80% done), win chance 88% by the market, down 5.0 points from 93%: selling +$1.00 after fees at bid 0.87');
  // Out of profit by the time it turns: the cuts take it (4.4c at 80%: a 1c loss is held), and the ride ends.
  const b = ride(0.8);
  for (const x of [0.9, 0.92]) b.at(x, 2);
  assert.equal(b.at(0.79, -0.8).plans.length, 0);
  assert.equal(b.tr.rides.has('R-FAV'), false);
  // Off: rides through the drop. Before the last 30% there is no ride: the legs decide.
  const c = ride(0.8, { ...rules, probTurn: 0 });
  for (const x of [0.92, 0.87]) assert.equal(c.at(x, 1).plans.length, 0);
  const d = ride(0.5);
  for (const x of [0.92, 0.87]) assert.ok(d.at(x, 1).plans.every((p) => p.leg !== 'prob_turn'));
  assert.equal(d.tr.rides.has('R-FAV'), false);
  // Without a score the progress is half the information clock, which falls back as the leader's price falls: the turn this
  // exit is for pulls the progress under 70%. A ride once begun goes on while in profit, so the turn is still caught.
  let p = 0.75;
  const f = ride(() => p);
  assert.equal(f.at(0.92, 2).plans.length, 0);
  p = 0.66;
  assert.equal(f.at(0.9, 1.6).plans.length, 0, 'still riding at 66%');
  const back = f.at(0.87, 1).plans;
  assert.equal(back[0]?.leg, 'prob_turn', JSON.stringify(back));
  assert.equal(back[0]?.why, 'riding in profit (match 66% done), win chance 88% by the market, down 5.0 points from 93%: selling +$1.00 after fees at bid 0.87');

  // With a live score that names its players (the Live Tennis feed) the scoring model's chance counts too, on serve odds
  // calibrated to the starting price (70% here): a set and a break up at 4-2 is 97%; 4-3 is 4.8 points down (rides); broken
  // back at 4-4 it is 11.7 points down (sold) while the market has not moved.
  const sc = (gamesA: number, gamesB: number): Score => ({ setsA: 1, setsB: 0, gamesA, gamesB, pointsA: 0, pointsB: 0 });
  const named = { scoreOriented: true };
  const e = ride(0.8);
  e.tr.liveSince = t0;
  e.tr.pStart = 0.7;
  assert.equal(e.at(0.9, 2, sc(4, 2), named).plans.length, 0);
  const e43 = e.at(0.9, 2, sc(4, 3), named);
  assert.equal(e43.plans.length, 0);
  assert.ok(e43.notes.some((n) => n.includes('win chance 92% by the score (best 97%), 91% by the market (best 91%)')), JSON.stringify(e43.notes));
  const s44 = e.at(0.9, 1.5, sc(4, 4), named).plans;
  assert.equal(s44[0]?.leg, 'prob_turn', JSON.stringify(s44));
  assert.equal(s44[0]?.why, 'riding in profit (match 80% done), win chance 85% by the score, down 11.7 points from 97%: selling +$1.50 after fees at bid 0.9');
  // Kalshi's live data does not say which player is home: its score gives no win chance, only the market does.
  const k = ride(0.8);
  k.tr.liveSince = t0;
  k.tr.pStart = 0.7;
  for (const g of [sc(4, 2), sc(4, 3), sc(4, 4)]) assert.equal(k.at(0.9, 2, g).plans.length, 0);
  assert.equal(k.tr.rides.get('R-FAV')?.score, undefined);
  // A stale score (the feed out of calls: the engine passes the last good one on) gives none either; a market turn is caught.
  const g = ride(0.8);
  g.tr.liveSince = t0;
  g.tr.pStart = 0.7;
  const readAt = g.clock.now;
  assert.equal(g.at(0.9, 2, sc(4, 2), { ...named, scoreAt: readAt }).plans.length, 0);
  g.clock.now = readAt + SCORE_FRESH_MS + 60_000;
  assert.equal(g.at(0.9, 2, sc(4, 2), { ...named, scoreAt: readAt }).plans.length, 0);
  const stale = g.at(0.85, 1, sc(4, 2), { ...named, scoreAt: readAt }).plans;
  assert.equal(stale[0]?.leg, 'prob_turn', JSON.stringify(stale));
  assert.ok(stale[0]?.why.includes('win chance 86% by the market, down 5.0 points from 91%'), stale[0]?.why);
  // A ride begun on the market at 95% is not sold when the first score arrives with a lower estimate: each reading keeps its own best.
  const h = ride(0.8);
  h.tr.liveSince = t0;
  h.tr.pStart = 0.7;
  assert.equal(h.at(0.94, 3).plans.length, 0);
  assert.equal(h.at(0.94, 3, sc(4, 4), named).plans.length, 0);
  assert.ok(Math.abs(h.tr.rides.get('R-FAV')!.score! - 0.8529) < 1e-3);
});

test('MatchTracker.winChance: the market\'s price, and the scoring model\'s from a fresh live score that names its players; the other player\'s is its complement', () => {
  const ms = [mk('S-A', 0.69, 0.71), mk('S-B', 0.29, 0.31)];
  const tr = new MatchTracker('S', T);
  const m = tr.winChance(ms, 'S-A', t0);
  assert.equal(m?.score, undefined);
  assert.ok(Math.abs(m!.market! - 0.7) < 1e-9);
  assert.ok(Math.abs(tr.winChance(ms, 'S-B', t0)!.market! - 0.3) < 1e-9);
  assert.equal(tr.winChance(ms, 'S-X', t0), undefined);
  // One tick's thin or one-sided book is no market reading: a book wider than WIN_CHANCE_MAX_SPREAD (6c), or one with no bid.
  assert.equal(WIN_CHANCE_MAX_SPREAD, 0.06);
  assert.ok(Math.abs(tr.winChance([mk('S-A', 0.68, 0.74), ms[1]], 'S-A', t0)!.market! - 0.705) < 1e-9, '6c counts');
  assert.equal(tr.winChance([mk('S-A', 0.69, 0.71), mk('S-B', 0.29, 0.40)], 'S-A', t0)?.market, undefined, '11c');
  assert.equal(tr.winChance([ms[0], { ...ms[1], quote: { ask: 0.31 } } as MatchMarket], 'S-A', t0)?.market, undefined, 'no bid');
  tr.liveSince = t0;
  tr.pStart = 0.7;
  tr.score = { setsA: 1, setsB: 0, gamesA: 3, gamesB: 1, pointsA: 0, pointsB: 0 };
  tr.scoreAt = t0;
  assert.equal(tr.winChance(ms, 'S-A', t0)?.score, undefined, 'not named (Kalshi live data): no score reading');
  tr.scoreOriented = true;
  const want = impliedModel(0.7, tr.format(ms), T.serveBase).remaining(tr.score).pA;
  assert.ok(want > 0.95, `${want}`);
  assert.equal(tr.winChance(ms, 'S-A', t0 + 60_000)?.score, want);
  assert.equal(tr.winChance(ms, 'S-B', t0 + 60_000)?.score, 1 - want);
  assert.equal(tr.winChance(ms, 'S-A', t0 + SCORE_FRESH_MS)?.score, want, 'fresh to the limit');
  const old = tr.winChance(ms, 'S-A', t0 + SCORE_FRESH_MS + 1);
  assert.equal(old?.score, undefined, 'stale');
  assert.ok(old?.market !== undefined);
  // observe() takes the snapshot's flags: the time the score was read (else now) and whether it names its players.
  const o = new MatchTracker('O', T);
  const snap = (extra: object) => ({ event: 'O', now: t0 + 600_000, startTime: t0, closeTime: t0 + 86_400_000, markets: ms, score: tr.score, ...extra });
  o.observe(snap({ scoreAt: t0 + 500_000, scoreOriented: true }));
  assert.deepEqual([o.scoreAt, o.scoreOriented], [t0 + 500_000, true]);
  o.observe(snap({}));
  assert.deepEqual([o.scoreAt, o.scoreOriented], [t0 + 600_000, false]);
});

test('tennis: a ride survives a tick with no usable bid, and one tick\'s thin or one-sided book is no win-chance reading (review, Nov 12)', () => {
  const rules = { pacerUsd: 4.5, settleFrac: T.settleFrac, endLoserCut: true, endEntryMargin: T.endEntryMargin, endCutFrac: T.endCutFrac,
    loserCut: T.loserCut, loserCutOpen: T.loserCutOpen, loserCutLate: T.loserCutLate, probTurn: T.probTurn };
  type Q = [number | undefined, number | undefined];
  const book = (fav: Q, dog: Q, net: number | undefined): MatchMarket[] => [
    { ticker: 'R-FAV', quote: { bid: fav[0], ask: fav[1] }, position: 30, avgEntry: 0.8, netAtBid: net } as MatchMarket,
    { ticker: 'R-DOG', quote: { bid: dog[0], ask: dog[1] }, position: 0 } as MatchMarket];
  // The two books 2c wide and mirrored: the market's win chance is the bid + 1c.
  const two = (bid: number, net: number) => book([bid, bid + 0.02], [1 - bid - 0.02, 1 - bid], net);
  const run = (prog: () => number) => {
    const tr = new MatchTracker('R', T);
    tr.progress = prog;
    let now = t0 + 3_600_000;
    const at = (markets: MatchMarket[]) => {
      const o = decideMatch(tr, { event: 'R', now, startTime: t0, closeTime: t0 + 86_400_000, markets }, T, budget, 0.01, rules);
      now += 30_000;
      return o;
    };
    return { tr, at };
  };
  const turned = (o: { plans: { leg: string }[] }) => o.plans.some((p) => p.leg === 'prob_turn');

  // No usable bid for a tick (a reconnect, a stale or crossed book, a feed-lag halt): the profit is unknown, so the ride and its
  // best stand and nothing sells. The turn from the best (93%) is still caught at 0.87 the tick after.
  const a = run(() => 0.8);
  a.at(two(0.92, 2));
  assert.equal(turned(a.at(two(0.9, 1.6))), false);
  const gap = a.at(book([undefined, 0.93], [0.07, 0.09], undefined));
  assert.equal(gap.plans.length, 0, JSON.stringify(gap.plans));
  assert.ok(gap.notes.some((n) => n.includes('R-FAV: riding to settlement, no usable bid this tick')), JSON.stringify(gap.notes));
  assert.ok(Math.abs(a.tr.rides.get('R-FAV')!.market! - 0.93) < 1e-9);
  const sold = a.at(two(0.87, 1)).plans;
  assert.equal(sold[0]?.leg, 'prob_turn', JSON.stringify(sold));
  assert.ok(sold[0].why.includes('down 5.0 points from 93%'), sold[0].why);
  // Through a comeback (progress back to 66%, never latched past 70%) a gap tick does not end the ride either: +$8 rides on,
  // where without the ride the quota snipe would sell it.
  let p = 0.75;
  const b = run(() => p);
  b.at(two(0.92, 8));
  p = 0.66;
  b.at(book([undefined, 0.94], [0.06, 0.08], undefined));
  assert.ok(b.tr.rides.has('R-FAV'));
  const on = b.at(two(0.92, 8));
  assert.equal(on.plans.length, 0, JSON.stringify(on.plans));
  assert.ok(on.notes.some((n) => n.includes('riding to settlement, win chance 93% by the market (best 93%)')), JSON.stringify(on.notes));

  // One tick's thin or one-sided book moves the mid with no trade: no reading, so no sale and no new best.
  const c = run(() => 0.8);
  c.at(two(0.86, 2.9));
  for (const thin of [book([0.86, 0.88], [0.12, 0.34], 2.9), book([0.86, 0.99], [0.01, 0.14], 2.9), book([0.86, 0.99], [undefined, undefined], 2.9)]) {
    assert.equal(turned(c.at(thin)), false, JSON.stringify(thin));
    assert.ok(Math.abs(c.tr.rides.get('R-FAV')!.market! - 0.87) < 1e-9);
  }
  assert.equal(turned(c.at(two(0.86, 2.9))), false);
  const real = c.at(two(0.81, 1)).plans;
  assert.equal(real[0]?.leg, 'prob_turn', JSON.stringify(real));
  assert.ok(real[0].why.includes('win chance 82% by the market, down 5.0 points from 87%'), real[0].why);
});

test('tennis: after a ride is sold on a turn, the favorite leg does not buy the same player back that match (review, Nov 12)', () => {
  // The underdog cut off (TENNIS_UNDERDOG_CUT_PROGRESS=0), so the underdog leg still holds R-A at 75% and rides it.
  const T0 = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), TENNIS_UNDERDOG_CUT_PROGRESS: '0' }).tennis;
  const rules = { pacerUsd: 4.5, settleFrac: T0.settleFrac, endLoserCut: T0.endLoserCut, endEntryMargin: T0.endEntryMargin, endCutFrac: T0.endCutFrac,
    loserCut: T0.loserCut, loserCutOpen: T0.loserCutOpen, loserCutLate: T0.loserCutLate, probTurn: T0.probTurn };
  const tr = new MatchTracker('R', T0);
  tr.progress = () => 0.75;
  tr.underdogTicker = 'R-A';
  tr.underdogEntered = true;
  tr.liveSince = t0;
  tr.pStart = 0.3;
  let now = t0 + 90 * 60_000;
  const tick = (bid: number, pos: number) => {
    const markets = [mkb('R-A', bid, bid + 0.02, 300, 100, now, { position: pos, avgEntry: pos ? 0.3 : undefined, netAtBid: pos ? 15 : undefined, flow: 0.5 }), mkb('R-B', 0.98 - bid - 0.02, 0.98 - bid, 100, 300, now)];
    const o = decideMatch(tr, { event: 'R', now, startTime: t0, closeTime: t0 + 86_400_000, markets }, T0, budget, 0.01, rules);
    now += 30_000;
    return o;
  };
  // Rides from a 0.92 bid; a slide of 0.2c a tick turns it 5 points down at 0.87.
  let b = 0.92;
  for (let i = 0; i < 6; i++) tick(b, 30);
  let sale;
  for (let i = 0; i < 40 && !sale; i++) {
    b = Math.round((b - 0.002) * 1000) / 1000;
    sale = tick(b, 30).plans.find((p) => p.leg === 'prob_turn');
  }
  assert.ok(sale && sale.price === 0.87 && sale.count === 30, JSON.stringify(sale));
  assert.deepEqual([...tr.turnSold], ['R-A']);
  // Flat the tick after: the favorite leg would buy R-A back (the leader at 0.88, inside 0.75-0.92); the turn sale blocks it.
  const after = tick(b, 0);
  assert.equal(after.plans.filter((p) => p.ticker === 'R-A' && p.side === 'bid').length, 0, JSON.stringify(after.plans));
  assert.ok(after.notes.some((n) => n.includes('no new entry on R-A (fav_entry): a ride was sold there this match when the win chance turned')), JSON.stringify(after.notes));
  tr.turnSold.clear();
  assert.ok(tick(b, 0).plans.some((p) => p.ticker === 'R-A' && p.leg === 'fav_entry'), 'without the block the leg buys it back');
});

test('match clock: the real start is expiration_time minus 14 days; without it, the published time moved 3 hours earlier', () => {
  const real = t0;
  const published = real + 3 * 3_600_000; // Kalshi's start field on tennis: the expected finish
  const expiration = real + 14 * 86_400_000;
  assert.equal(T.startFromExpiry, true);
  assert.equal(T.startShiftMin, 180);
  assert.equal(tennisStartTime(published, expiration, T), real);
  assert.equal(tennisStartTime(published, undefined, T), published - 180 * 60_000);
  // An expiration that does not fit the rule (after the published time, or more than 6 h before it) is not used.
  assert.equal(tennisStartTime(published, published + 60_000 + 14 * 86_400_000, T), published - 180 * 60_000);
  assert.equal(tennisStartTime(published, published - 7 * 3_600_000 + 14 * 86_400_000, T), published - 180 * 60_000);
  assert.equal(tennisStartTime(published, expiration, { startFromExpiry: false, startShiftMin: 180 }), published - 180 * 60_000);
  assert.equal(tennisStartTime(undefined, expiration, T), undefined, 'no published time: the tracker reads play from the price');
  const old = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), TENNIS_START_FROM_EXPIRY: 'false', TENNIS_START_SHIFT_MIN: '0', TENNIS_LIVE_BY_MOVE: 'false' }).tennis;
  assert.equal(tennisStartTime(published, expiration, old), published, 'both off: the old clock');
  assert.throws(() => loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), TENNIS_START_SHIFT_MIN: '601' }));
});

test('match clock: a 3c move in the hour before the start marks the match live; earlier, without a move, or with TENNIS_LIVE_BY_MOVE=false it does not', () => {
  assert.equal(T.liveByMove, true);
  assert.equal(T.liveByMoveLeadMin, 60);
  const off = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), TENNIS_LIVE_BY_MOVE: 'false' }).tennis;
  const run = (cfg: typeof T, startInMin: number, dogTo: number) => {
    const tr = new MatchTracker('M', cfg);
    const snap = (now: number, dog: number) => ({ event: 'M', now, startTime: t0 + startInMin * 60_000, closeTime: t0 + 86_400_000, markets: [mk('M-FAV', 1 - dog - 0.02, 1 - dog), mk('M-DOG', dog - 0.01, dog + 0.01)] });
    tr.observe(snap(t0 - 60_000, 0.2));
    const phase = tr.observe(snap(t0, dogTo));
    return { live: tr.liveSince, phase };
  };
  const moved = run(T, 45, 0.25);
  assert.equal(moved.live, t0, 'in play 45 minutes before the listed start');
  assert.equal(moved.phase, 'underdog_window');
  assert.equal(run(T, 45, 0.2).live, undefined, 'no move: still pre-match');
  assert.equal(run(T, 90, 0.25).live, undefined, 'more than an hour before the start: a move is news, not play');
  assert.equal(run(off, 45, 0.25).live, undefined, 'TENNIS_LIVE_BY_MOVE=false: only the clock starts the match');
});

test('match clock: a Kalshi-style listing (start field = expected finish) goes live at the real start and reads Live Tennis from it', async () => {
  const { TennisScoreClient } = await import('../bot/tennis/liveTennisApi');
  const run = async (startedMinAgo: number, withExpiry = true) => {
    const dir = tmpDir();
    const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(40), DATA_DIR: dir, DOMINANCE_FEED: 'false', SPOT_FEED: 'false', PERPS_FEED: 'false', STRATEGY_SERIES: 'KXBTC15M', SESSION_EDGE_NO_ENTRY: 'false', TENNIS_SCORE_FEED: 'livetennis' });
    const now = Date.now();
    const real = now - startedMinAgo * 60_000;
    // As listed on Nov 12: occurrence_datetime 3 h after the first serve, expiration_time the first serve plus 14 days.
    const m = (ticker: string, title: string): MarketInfo => ({ ticker, seriesTicker: 'KXATPMATCH', eventTicker: 'KXATPMATCH-E1', status: 'open', openTime: now - 3_600_000, closeTime: real + 3 * 3_600_000, tickSize: 0.01, title, startTime: real + 3 * 3_600_000, ...(withExpiry ? { expirationTime: real + 14 * 86_400_000 } : {}) });
    const markets = [m('KXATPMATCH-E1-FAV', 'Will Fav win?'), m('KXATPMATCH-E1-DOG', 'Will Dog win?')];
    const rest = { getSeriesFees: async () => ({ feeType: 'quadratic_with_maker_fees', multiplier: 1 }), getOpenMarkets: async (s: string) => (s === 'KXATPMATCH' ? markets : []), getMarket: async () => undefined } as unknown as KalshiRest;
    const audit = tmpAudit();
    const md = new MarketData(cfg, rest, undefined, new Recorder(path.join(dir, 'rec')));
    await md.refreshCatalog(now);
    md.book('KXATPMATCH-E1-FAV').applySnapshot({ bids: [{ price: 0.84, size: 100 }], asks: [{ price: 0.86, size: 100 }] }, Date.now());
    md.book('KXATPMATCH-E1-DOG').applySnapshot({ bids: [{ price: 0.14, size: 300 }], asks: [{ price: 0.17, size: 100 }] }, Date.now());
    const paper = new PaperExchange(undefined, 200, (t) => md.books.get(t), () => ({ takerMultiplier: 1, makerMultiplier: 1 }));
    const oms = new Oms({ gateway: paper, audit, statePath: path.join(dir, 'oms.json'), feesFor: (t) => md.feesFor(t), sleep: async () => undefined });
    const recon = new Reconciler({ gateway: paper, oms, audit, getMarket: rest.getMarket, onPersistentBreak: () => undefined });
    let calls = 0;
    const tennisScores = new TennisScoreClient({ apiKey: 'k', fetchFn: (async () => { calls++; return new Response(JSON.stringify({ data: [], meta: { offset: 0, limit: 200, has_more: false } }), { status: 200 }); }) as unknown as typeof fetch });
    const engine = new Engine({ cfg, audit, alerter: new Alerter([], audit), md, gateway: paper, oms, risk: new RiskGateway(cfg.risk), kill: new KillSwitch(path.join(dir, 'kill.json'), audit), recon, model: MetaModel.identity(), exchangeStatus: openExchange(), tennisScores });
    engine.balance = (await recon.run('startup'))!.balance;
    await engine.tick();
    const tr = (engine as unknown as { matches: Map<string, MatchTracker> }).matches.get('KXATPMATCH-E1');
    return { calls, real, tr, status: engine.tennisStatus.get('KXATPMATCH-E1') };
  };
  // Ten minutes into the match: before the fix the bot read it as starting in 2 h 50 min, pre-match, and never asked for a score.
  const inPlay = await run(10);
  assert.equal(inPlay.status?.publishedStart, inPlay.real + 3 * 3_600_000);
  assert.equal(inPlay.status?.startTime, inPlay.real);
  assert.equal(inPlay.tr?.liveSince, inPlay.real, 'live from the real first serve');
  assert.equal(inPlay.calls, 1, 'Live Tennis is read for a match in play');
  // Two hours before the first serve: pre-match, no call.
  const early = await run(-120);
  assert.equal(early.tr?.liveSince, undefined);
  assert.equal(early.calls, 0);
  // No expiration_time on the listing: the published time moved 3 h earlier gives the same start.
  const noExpiry = await run(10, false);
  assert.equal(noExpiry.status?.startTime, noExpiry.real);
  assert.equal(noExpiry.tr?.liveSince, noExpiry.real);
});
