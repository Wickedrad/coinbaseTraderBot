import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadConfig, type StrategyConfig } from '../bot/config';
import { DEFAULT_FEES } from '../bot/fees';
import { applyFvGate, decide, gateCfgFor, seriesMatches, fvGatePasses, inLoserWindow, loserExit, loserNoEntry, shareWindowSec, type MarketView, type StrategyOutput } from '../bot/strategy/fairValueStrategy';

// Steven's settlement rule (Oct 31) and the sizing lab's loser exits: the entry gate, the loser cut and the window cut.
const base = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), STRATEGY_CADENCE: 'continuous' }).strategy;
const cfg: StrategyConfig = {
  ...base,
  style: 'both', series: ['KXBTC15M'], kellyFraction: 0.25, minEdge: 0.02, takerBuffer: 0.01,
  inventorySkewPerContract: 0.002, requoteThreshold: 0.01, fastMoveSigmas: 3, fastMoveWindowSec: 5, orderTtlSec: 60,
  exitPolicy: 'fair_value', sessionRisk: {},
  // The rules under test on (the cut and the window cut are off by default since Nov 2) and the quote cushion at the gate's 6c.
  loserExits: { ...base.loserExits!, cut: true, window: true, gateQuoteMargin: undefined },
};
const off: StrategyConfig = { ...cfg, loserExits: { ...cfg.loserExits!, gate: false, cut: false, window: false } };

const view = (o: Partial<MarketView> = {}): MarketView => ({
  ticker: 'T', pYes: 0.55, bestBid: { price: 0.5, size: 20 }, bestAsk: { price: 0.6, size: 20 }, position: 0,
  bankroll: 200, maxOrderRiskUsd: 4, maxContracts: 10, minSidePrice: 0.1, tauSec: 400, noEntryBeforeCloseSec: 15,
  fastMove: false, tickSize: 0.01, fees: DEFAULT_FEES, nowSec: 1000, closeSec: 1400, ...o,
});
// Long 10 YES bought at 0.55 plus a 1.75c fee: under water at a 0.50 bid, in profit at 0.70.
const long = (o: Partial<MarketView> = {}) => view({ position: 10, entrySidePrice: 0.55, entryFeePerContract: 0.0175, ...o });
const ioc = (out: StrategyOutput) => out.place.filter((p) => p.purpose === 'exit' && p.timeInForce === 'immediate_or_cancel');

test('loser rules: gate 6c + 12c quote cushion on by default, cut and window cut off (8 recorded days), each by its flag', () => {
  assert.deepEqual(base.loserExits, { gate: true, gateMargin: 0.06, gateQuoteMargin: 0.12, cut: false, cutMargin: 0.03, cutMode: 'fair', cutMaxTau: 0, stopDrop: 0.5, cutState: 'any', window: false, windowJudge: 'bid', windowMode: 'bid', windowRestFinalSec: 60, windowShare: 0, noEntryShare: 0, gatedStakeMult: 1, gatedStakeCap: 'clamp' });
  const c = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), FV_ENTRY_GATE: 'false', LOSER_CUT: 'true', LOSER_WINDOW_CUT: 'true', FV_ENTRY_GATE_MARGIN: '0.09', LOSER_CUT_MARGIN: '0.05',
    FV_ENTRY_GATE_QUOTE_MARGIN: '', LOSER_WINDOW_JUDGE: 'cost', LOSER_WINDOW_MODE: 'rest', LOSER_WINDOW_REST_FINAL_SEC: '90', LOSER_WINDOW_SHARE: '0.25', LOSER_NO_ENTRY_SHARE: '0.2' }).strategy;
  assert.deepEqual(c.loserExits, { gate: false, gateMargin: 0.09, cut: true, cutMargin: 0.05, cutMode: 'fair', cutMaxTau: 0, stopDrop: 0.5, cutState: 'any', window: true, windowJudge: 'cost', windowMode: 'rest', windowRestFinalSec: 90, windowShare: 0.25, noEntryShare: 0.2, gatedStakeMult: 1, gatedStakeCap: 'clamp' });
});

test('loser window cut: in the last share of the window or the final minute a position not in profit is sold at the bid; one in profit rides', () => {
  // The last 10% (settleShare), -0.68 after fees: sold at the bid, the whole position (the bid shows 20).
  const share = decide(long({ settleShare: true, tauSec: 70 }), cfg);
  assert.equal(ioc(share).length, 1);
  const s = ioc(share)[0];
  assert.deepEqual([s.side, s.price, s.count, s.reduceOnly, s.postOnly], ['ask', 0.5, 10, true, false]);
  assert.match(s.why, /^loser window cut: -0\.\d\d net after fees on 10 at bid 0\.50, 70 s to the close/);
  // The final minute (exits closed): sold too, and the hold note is not written.
  const last = decide(long({ exitWindowOpen: false, settleShare: true, tauSec: 30 }), cfg);
  assert.match(ioc(last)[0]?.why ?? '', /^loser window cut: /);
  assert.ok(!last.notes.includes('final minute: riding to settlement'));
  // In profit after fees: it rides to settlement in both.
  const ride = decide(long({ settleShare: true, tauSec: 70, bestBid: { price: 0.7, size: 20 } }), cfg);
  assert.equal(ioc(ride).length, 0);
  assert.ok(ride.notes.includes('final share of the window, in profit after fees: riding to settlement'));
  const rideLast = decide(long({ exitWindowOpen: false, settleShare: true, tauSec: 30, bestBid: { price: 0.7, size: 20 } }), cfg);
  assert.equal(ioc(rideLast).length, 0);
  assert.ok(rideLast.notes.includes('final minute: riding to settlement'));
  // A thin bid sells what it shows; the rest is judged on the next evaluation.
  assert.equal(ioc(decide(long({ settleShare: true, tauSec: 70, bestBid: { price: 0.5, size: 4 } }), cfg))[0]?.count, 4);
  // The NO side: 10 NO bought at 0.40 plus the fee, NO bid 0.35 (YES ask 0.65): bought back at the YES ask.
  const no = ioc(decide(view({ position: -10, entrySidePrice: 0.4, entryFeePerContract: 0.0175, bestBid: { price: 0.6, size: 20 }, bestAsk: { price: 0.65, size: 20 }, settleShare: true, tauSec: 70 }), cfg))[0];
  assert.deepEqual([no?.side, no?.price, no?.count], ['bid', 0.65, 10]);
  assert.match(no!.why, /^loser window cut: .* on 10 NO at bid 0\.35/);
  // Off: the old behavior (the final minute holds every position).
  assert.equal(ioc(decide(long({ exitWindowOpen: false, settleShare: true, tauSec: 30 }), off)).length, 0);
  // No cost basis: no judgement, nothing sold.
  assert.equal(loserExit(view({ position: 10, settleShare: true, tauSec: 70 }), cfg), undefined);
});

test('loser window judge: fair and cost ask the coin before a thin closing bid is hit; no fair value judges at the bid', () => {
  // Long 10 YES at 0.55 + 1.75c (cost 0.5675), bid 0.50 (1.8c fee a contract: 0.482 net), the last share of the window.
  const end = (pFair: number | undefined, judge: 'bid' | 'fair' | 'cost', o: Partial<MarketView> = {}) =>
    ioc(decide(long({ settleShare: true, tauSec: 70, ...(pFair === undefined ? {} : { pFair }), ...o }), { ...cfg, loserExits: { ...cfg.loserExits!, windowJudge: judge } }));
  // fair: sold only when the coin says the bid beats holding (fair value under 0.482); 0.60 rides, 0.47 is sold.
  assert.equal(end(0.6, 'fair').length, 0);
  assert.match(end(0.47, 'fair')[0]?.why ?? '', /^loser window cut: .* at bid 0\.50, fair value 0\.470 < bid less fee 0\.482, 70 s to the close/);
  // cost: sold when the coin says the side is worth less than it cost (0.55 < 0.5675); 0.60 rides.
  assert.equal(end(0.6, 'cost').length, 0);
  assert.match(end(0.55, 'cost')[0]?.why ?? '', /^loser window cut: .* fair value 0\.550 < cost 0\.56\d, 70 s/);
  // bid (as first built) sells at 0.60 too; no fair value known: every judge sells at the bid.
  assert.equal(end(0.6, 'bid').length, 1);
  assert.equal(end(undefined, 'fair').length, 1);
  // Held by the judge in the final minute: it rides (no exit runs there), with the note.
  const last = decide(long({ exitWindowOpen: false, settleShare: true, tauSec: 30, pFair: 0.6 }), { ...cfg, loserExits: { ...cfg.loserExits!, windowJudge: 'cost' } });
  assert.equal(ioc(last).length, 0);
  assert.ok(last.notes.includes('final minute: riding to settlement'));
  // A side worth well under the bid (0.44) is sold under either judge.
  assert.match(end(0.44, 'cost')[0]?.why ?? '', /^loser window cut: /);
  assert.match(end(0.44, 'fair')[0]?.why ?? '', /^loser window cut: /);
});

test('loser window share: LOSER_WINDOW_SHARE starts the window cut earlier, while books are deeper', () => {
  const early = { ...cfg, loserExits: { ...cfg.loserExits!, windowShare: 0.3 } };
  // 900 s contract: the cut starts with 270 s left (30%), before the last 10%.
  assert.match(loserExit(long({ tauSec: 250, windowSec: 900 }), early)?.why ?? '', /^loser window cut: .* 250 s to the close/);
  assert.equal(loserExit(long({ tauSec: 300, windowSec: 900 }), early), undefined);
  // Off (0), or the window's length unknown: only the last share and the final minute.
  assert.equal(loserExit(long({ tauSec: 250, windowSec: 900 }), cfg), undefined);
  assert.equal(loserExit(long({ tauSec: 250 }), early), undefined);
  // In profit: never cut early (its own exits still run).
  assert.equal(loserExit(long({ tauSec: 250, windowSec: 900, bestBid: { price: 0.7, size: 20 } }), early), undefined);
});

test('loser no-entry window: no new risk where the window cut would sell it straight back, nor from LOSER_NO_ENTRY_SHARE left', () => {
  const ne = (share: number, o: Partial<StrategyConfig['loserExits']> = {}): StrategyConfig => ({ ...cfg, loserExits: { ...cfg.loserExits!, noEntryShare: share, ...o } });
  // Off (0): entries run in the last share as before.
  assert.equal(loserNoEntry({ settleShare: true, tauSec: 70, windowSec: 900 }, cfg), false);
  // On: the window cut's stretch (last share, final minute) and from the share left (180 s of 900 at 0.2).
  assert.equal(loserNoEntry({ settleShare: true, tauSec: 70, windowSec: 900 }, ne(0.1)), true);
  assert.equal(loserNoEntry({ exitWindowOpen: false, tauSec: 30 }, ne(0.1)), true);
  assert.equal(loserNoEntry({ tauSec: 150, windowSec: 900 }, ne(0.2)), true);
  assert.equal(loserNoEntry({ tauSec: 200, windowSec: 900 }, ne(0.2)), false);
  // With the window cut off only the share counts.
  assert.equal(loserNoEntry({ settleShare: true, tauSec: 100, windowSec: 900 }, ne(0.1, { window: false })), false);
  // A taker YES the model wants is not taken there, and a resting quote is pulled.
  const taker = (o: Partial<MarketView>, c: StrategyConfig) => decide(view({ pYes: 0.75, pFair: 0.75, ...o }), { ...c, style: 'taker' });
  assert.ok(taker({ tauSec: 400, windowSec: 900 }, ne(0.2)).place.some((p) => p.purpose === 'entry'));
  const late = taker({ tauSec: 150, windowSec: 900 }, ne(0.2));
  assert.equal(late.place.filter((p) => p.purpose === 'entry').length, 0);
  assert.ok(late.notes.includes('loser window: no new risk this close to the end'));
  const pulled = decide(view({ tauSec: 70, windowSec: 900, settleShare: true, restingBid: { clientOrderId: 'q1', price: 0.5, remaining: 5 } }), { ...ne(0.1), style: 'maker' });
  assert.ok(pulled.cancel.some((c) => c.clientOrderId === 'q1'));
  assert.equal(pulled.place.filter((p) => p.purpose === 'quote').length, 0);
  // The finished plan (fill-model crosses, training trades): every order that adds is dropped, exits and reductions stay.
  const plan = (): StrategyOutput => ({ cancel: [], notes: [], place: [
    { side: 'bid', price: 0.6, count: 5, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'entry', edge: 0.1, why: 'fill model YES -> cross' },
    { side: 'ask', price: 0.5, count: 3, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: true, purpose: 'exit', edge: 0, why: 'exit' },
    { side: 'ask', price: 0.5, count: 2, timeInForce: 'good_till_canceled', postOnly: true, reduceOnly: false, purpose: 'quote', edge: 0.02, why: 'maker ask' },
  ] });
  const flat = plan();
  assert.equal(applyFvGate(flat, 0.9, 0, DEFAULT_FEES, off, true), 2, 'gate off: the late window still drops new risk');
  assert.deepEqual(flat.place.map((p) => p.why), ['exit']);
  assert.ok(flat.notes.some((n) => n.startsWith('loser window: dropped entry YES at 0.60')));
  const held = plan();
  assert.equal(applyFvGate(held, 0.9, 5, DEFAULT_FEES, off, true), 1);
  assert.deepEqual(held.place.map((p) => p.why), ['exit', 'maker ask']);
});

test('loser cut: a position not in profit is sold at once when the spot fair value of its side is under the bid less the fee less 3c', () => {
  // Bid 0.50, fee 1.8c a contract on 10: the cut line is 0.50 - 0.018 - 0.03 = 0.452.
  const cut = decide(long({ pFair: 0.44 }), cfg);
  assert.equal(ioc(cut).length, 1, JSON.stringify(cut.place));
  assert.match(ioc(cut)[0].why, /^loser cut: fair value 0\.440 < bid 0\.50 - fee 0\.018 - 0\.03, -0\.\d\d net after fees on 10$/);
  assert.equal(ioc(cut)[0].count, 10);
  // Above the line: held (the model, at 0.55, does not sell either).
  assert.equal(ioc(decide(long({ pFair: 0.46 }), cfg)).length, 0);
  // In profit: never a loser cut (its own exits, the pacer or settlement in the last share decide).
  assert.ok(ioc(decide(long({ pFair: 0.2, bestBid: { price: 0.7, size: 20 } }), cfg)).every((p) => !p.why.startsWith('loser')));
  // No fair value, or the flag off: no cut.
  assert.equal(ioc(decide(long(), cfg)).length, 0);
  assert.equal(ioc(decide(long({ pFair: 0.44 }), off)).length, 0);
  // The NO side: NO fair value 1 - 0.7 = 0.30 under NO bid 0.35 - fee - 3c.
  const no = ioc(decide(view({ position: -10, pFair: 0.7, entrySidePrice: 0.4, entryFeePerContract: 0.0175, bestBid: { price: 0.6, size: 20 }, bestAsk: { price: 0.65, size: 20 } }), cfg));
  assert.match(no[0]?.why ?? '', /^loser cut: fair value 0\.300 < bid 0\.35/);
  // One sale a tick: the cut stands in for the position's other exits (the model's sale at the same bid).
  const both = decide(long({ pFair: 0.3, pYes: 0.3 }), cfg);
  assert.equal(ioc(both).length, 1);
  assert.match(ioc(both)[0].why, /^loser cut: /);
});

test('fair value gate: new risk only where the spot fair value of the side bought is at least cost + fee + 6c', () => {
  assert.equal(fvGatePasses(0.7, 'yes', 0.6, 0.02, cfg), true);
  assert.equal(fvGatePasses(0.67, 'yes', 0.6, 0.02, cfg), false);
  assert.equal(fvGatePasses(0.3, 'no', 0.6, 0.02, cfg), true); // NO worth 0.70 against 0.68
  assert.equal(fvGatePasses(undefined, 'yes', 0.6, 0.02, cfg), true);
  assert.equal(fvGatePasses(0.5, 'yes', 0.6, 0.02, off), true);
  // FV_ENTRY_GATE_QUOTE_MARGIN: a resting maker quote needs a wider cushion than a taker entry (12c by default; '' = the gate's 6c).
  const wide: StrategyConfig = { ...cfg, loserExits: { ...cfg.loserExits!, gateQuoteMargin: 0.1 } };
  assert.equal(fvGatePasses(0.7, 'yes', 0.6, 0.02, cfg, true), true);
  assert.equal(fvGatePasses(0.7, 'yes', 0.6, 0.02, wide, true), false); // a quote needs 0.60 + 0.02 + 0.10 = 0.72 with the wider margin
  assert.equal(fvGatePasses(0.7, 'yes', 0.6, 0.02, wide, false), true); // a taker entry still needs only 6c
  assert.equal(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32) }).strategy.loserExits?.gateQuoteMargin, 0.12);
  assert.equal(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), FV_ENTRY_GATE_QUOTE_MARGIN: '' }).strategy.loserExits?.gateQuoteMargin, undefined);
  assert.equal(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), FV_ENTRY_GATE_QUOTE_MARGIN: '0.1' }).strategy.loserExits?.gateQuoteMargin, 0.1);
  // A taker YES the model wants (q 0.75 against a 0.60 ask): taken only when the spot fair value clears the gate.
  const taker = (pFair?: number) => decide(view({ pYes: 0.75, pFair }), { ...cfg, style: 'taker' });
  const take = (out: StrategyOutput) => out.place.find((p) => p.purpose === 'entry');
  assert.ok(take(taker(0.75)));
  assert.ok(take(taker()), 'no fair value: no gate');
  const refused = taker(0.62);
  assert.equal(take(refused), undefined);
  assert.ok(refused.notes.some((n) => /^fair value gate: YES fair value 0\.620 < 0\.60 \+ fee 0\.0\d\d \+ 0\.06$/.test(n)), JSON.stringify(refused.notes));
  // Maker quotes: the gate drops the new risk a quote would add, never the part that unwinds a position.
  const short = (pFair: number) => decide(view({ position: -5, pFair, entrySidePrice: 0.45, entryFeePerContract: 0.0175 }), { ...cfg, style: 'maker' });
  const yesBid = (out: StrategyOutput) => out.place.find((p) => p.side === 'bid' && p.purpose === 'quote');
  assert.ok(yesBid(short(0.7))!.count > 5);
  assert.equal(yesBid(short(0.4))?.count, 5);
});

test('applyFvGate: the finished plan keeps no entry the gate refuses (fill-model crosses, training trades); orders that only reduce stay', () => {
  const plan = (): StrategyOutput => ({ cancel: [], notes: [], place: [
    { side: 'bid', price: 0.6, count: 5, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'entry', edge: 0.1, why: 'fill model YES -> cross' },
    { side: 'ask', price: 0.5, count: 3, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: true, purpose: 'exit', edge: 0, why: 'exit' },
    { side: 'ask', price: 0.5, count: 2, timeInForce: 'good_till_canceled', postOnly: true, reduceOnly: false, purpose: 'quote', edge: 0.02, why: 'maker ask' },
  ] });
  // Flat, YES fair value 0.62: the YES cross (0.60 + fee + 6c) and the NO quote (NO worth 0.38 against 0.50) go.
  const flat = plan();
  assert.equal(applyFvGate(flat, 0.62, 0, DEFAULT_FEES, cfg), 2);
  assert.deepEqual(flat.place.map((p) => p.why), ['exit']);
  assert.equal(flat.notes.filter((n) => n.startsWith('fair value gate: dropped')).length, 2);
  // Long 5 YES: the ask for 2 only sells what is held, so it stays.
  const held = plan();
  assert.equal(applyFvGate(held, 0.62, 5, DEFAULT_FEES, cfg), 1);
  assert.deepEqual(held.place.map((p) => p.why), ['exit', 'maker ask']);
  // Off, or no fair value: untouched.
  assert.equal(applyFvGate(plan(), 0.62, 0, DEFAULT_FEES, off), 0);
  assert.equal(applyFvGate(plan(), undefined, 0, DEFAULT_FEES, cfg), 0);
});

test('GATED_STAKE_MULT: off by default; at 2 only the orders that pass the gate double, exits and ungated plans stay', () => {
  assert.equal(base.loserExits!.gatedStakeMult, 1);
  assert.equal(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), GATED_STAKE_MULT: '2' }).strategy.loserExits!.gatedStakeMult, 2);
  const x2: StrategyConfig = { ...cfg, loserExits: { ...cfg.loserExits!, gatedStakeMult: 2 } };
  const plan = (): StrategyOutput => ({ cancel: [], notes: [], place: [
    { side: 'bid', price: 0.6, count: 5, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'entry', edge: 0.1, why: 'cross' },
    { side: 'ask', price: 0.5, count: 3, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: true, purpose: 'exit', edge: 0, why: 'exit' },
  ] });
  // YES fair value 0.80 clears 0.60 + fee + 6c: the entry doubles, the exit keeps its 3.
  const ok = plan();
  assert.equal(applyFvGate(ok, 0.8, 0, DEFAULT_FEES, x2), 0);
  assert.deepEqual(ok.place.map((p) => p.count), [10, 3]);
  assert.ok(ok.notes.some((n) => n.startsWith('gated stake x2: entry 5 -> 10')));
  // At 1 (the default) nothing changes; with the gate off or no fair value, nothing is scaled.
  const one = plan(); applyFvGate(one, 0.8, 0, DEFAULT_FEES, cfg); assert.deepEqual(one.place.map((p) => p.count), [5, 3]);
  const gOff = plan(); applyFvGate(gOff, 0.8, 0, DEFAULT_FEES, { ...x2, loserExits: { ...x2.loserExits!, gate: false } }); assert.deepEqual(gOff.place.map((p) => p.count), [5, 3]);
  const noFv = plan(); applyFvGate(noFv, undefined, 0, DEFAULT_FEES, x2); assert.deepEqual(noFv.place.map((p) => p.count), [5, 3]);
  // A training trade that passes the gate keeps its minimum size.
  const tr = plan(); tr.place[0] = { ...tr.place[0], why: 'train: YES at 0.60' }; applyFvGate(tr, 0.8, 0, DEFAULT_FEES, x2); assert.deepEqual(tr.place.map((p) => p.count), [5, 3]);
  // GATED_STAKE_CAP=clamp (default) with the band's top passed in: 5 at 0.60 ($3 + fee) doubles to 10 under a $20 top, but a
  // $5 top holds it at the most contracts that fit ($0.60 x 7 + fee <= $5); widen ignores the top (the caps widen instead).
  const c20 = plan(); applyFvGate(c20, 0.8, 0, DEFAULT_FEES, x2, false, 20); assert.equal(c20.place[0].count, 10);
  const c5 = plan(); applyFvGate(c5, 0.8, 0, DEFAULT_FEES, x2, false, 5);
  assert.ok(c5.place[0].count > 5 && c5.place[0].count < 10);
  assert.ok(c5.place[0].count * 0.6 <= 5);
  const wide = plan(); applyFvGate(wide, 0.8, 0, DEFAULT_FEES, { ...x2, loserExits: { ...x2.loserExits!, gatedStakeCap: 'widen' } }, false, 5);
  assert.equal(wide.place[0].count, 10);
  assert.equal(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), GATED_STAKE_CAP: 'widen' }).strategy.loserExits!.gatedStakeCap, 'widen');
});

test('shareWindowSec: the share rules measure a contract\'s own hour, not a ladder\'s listing hours or a day ahead', () => {
  const close = Date.parse('2026-10-30T17:00:00Z');
  assert.equal(base.shareWindowMaxSec, 3600, 'an hour by default');
  // A 15-minute contract keeps its 900 s (the last 10% is its last 90 s).
  assert.equal(shareWindowSec(close - 900_000, close, 3600), 900);
  // An hourly ladder listed an hour ahead, and a daily one listed 20 hours ahead: both an hour (the last 10% is 6 minutes).
  assert.equal(shareWindowSec(close - 3_600_000, close, 3600), 3600);
  assert.equal(shareWindowSec(close - 20 * 3_600_000, close, 3600), 3600);
  // No cap (0): the listing, as before (20 h: its last 10% was the last 2 hours, the bot's whole entry window).
  assert.equal(shareWindowSec(close - 20 * 3_600_000, close, 0), 72_000);
  // No open time, or a broken one: no window.
  assert.equal(shareWindowSec(Number.NaN, close, 3600), undefined);
  assert.equal(shareWindowSec(close, close, 3600), undefined);
  // At 30 minutes to the close a 20-hour listing is no longer inside the loser window (it was, measured on the listing).
  const L = { ...cfg.loserExits!, windowShare: 0.1 };
  const at = (maxSec: number) => inLoserWindow({ settleShare: false, exitWindowOpen: true, tauSec: 1800, windowSec: shareWindowSec(close - 20 * 3_600_000, close, maxSec) }, L);
  assert.equal(at(3600), false);
  assert.equal(at(0), true);
});

test('loser window rest (LOSER_WINDOW_MODE=rest): the window cut rests at the spot fair value of the side until the final seconds, then sells into the bid', () => {
  const rest: StrategyConfig = { ...cfg, loserExits: { ...cfg.loserExits!, windowMode: 'rest' } };
  const gtc = (out: StrategyOutput) => out.place.filter((p) => p.purpose === 'exit' && p.timeInForce === 'good_till_canceled');
  // Long 10 YES at 0.55 + fee, bid 0.50, fair value 0.57, 300 s to the close in the last share: a post-only ask for all 10 at 0.57.
  const r = decide(long({ settleShare: true, tauSec: 300, pFair: 0.57 }), rest);
  assert.equal(ioc(r).length, 0);
  assert.deepEqual(gtc(r).map((p) => [p.side, p.price, p.count, p.postOnly, p.reduceOnly, p.expirationTime]), [['ask', 0.57, 10, true, false, 1399]]);
  assert.match(gtc(r)[0]!.why, /^loser window rest: -0\.\d\d net after fees on 10 at bid 0\.50, sell rests at 0\.57 \(fair value 0\.570\), 300 s to the close/);
  assert.ok(r.notes.some((n) => n.startsWith('loser window rest')));
  // Fair value at or under the bid: the sell rests a tick over the bid, never in it.
  assert.equal(gtc(decide(long({ settleShare: true, tauSec: 300, pFair: 0.45 }), rest))[0]?.price, 0.51);
  // The final 60 s (LOSER_WINDOW_REST_FINAL_SEC): sold into the bid as the bid mode does; so is a position with no fair value.
  assert.match(ioc(decide(long({ settleShare: true, tauSec: 50, pFair: 0.57 }), rest))[0]?.why ?? '', /^loser window cut: /);
  assert.match(ioc(decide(long({ settleShare: true, tauSec: 300 }), rest))[0]?.why ?? '', /^loser window cut: /);
  assert.match(ioc(decide(long({ settleShare: true, tauSec: 80, pFair: 0.57 }), { ...rest, loserExits: { ...rest.loserExits!, windowRestFinalSec: 90 } }))[0]?.why ?? '', /^loser window cut: /);
  // In profit after fees: it rides, nothing rests.
  const ride = decide(long({ settleShare: true, tauSec: 300, pFair: 0.57, bestBid: { price: 0.7, size: 20 } }), rest);
  assert.equal(gtc(ride).length + ioc(ride).length, 0);
  // The NO side: 10 NO at 0.40 + fee, NO bid 0.35 (YES ask 0.65), NO fair value 0.42: the buy-back rests at YES 0.58 (= 1 - 0.42).
  const no = gtc(decide(view({ position: -10, entrySidePrice: 0.4, entryFeePerContract: 0.0175, bestBid: { price: 0.6, size: 20 }, bestAsk: { price: 0.65, size: 20 }, settleShare: true, tauSec: 300, pFair: 0.58 }), rest))[0];
  assert.deepEqual([no?.side, no?.price, no?.count], ['bid', 0.58, 10]);
  assert.match(no!.why, /on 10 NO at bid 0\.35, sell rests at 0\.42 \(fair value 0\.420\)/);
  // A style that never quotes sells into the bid instead (the rest needs the quote slot).
  assert.match(ioc(decide(long({ settleShare: true, tauSec: 300, pFair: 0.57 }), { ...rest, style: 'taker' }))[0]?.why ?? '', /^loser window cut: /);
  // The rest replaces any resting ask already in the slot at another price.
  const re = decide(long({ settleShare: true, tauSec: 300, pFair: 0.57, restingAsk: { clientOrderId: 'a1', price: 0.62, remaining: 10 } }), rest);
  assert.deepEqual(re.cancel.map((c) => c.clientOrderId), ['a1']);
  assert.equal(gtc(re)[0]?.price, 0.57);
});

test('TRAINING_GATE_MARGIN: training trades take their own gate margin; other orders keep theirs', () => {
  const tm: StrategyConfig = { ...cfg, loserExits: { ...cfg.loserExits!, gateQuoteMargin: 0.12, trainMargin: 0.03 } };
  // A resting YES at 0.50 (maker fee 0), fair value 0.56: a quote needs 0.62 (dropped); a training trade needs 0.53 (kept).
  const plan = (why: string): StrategyOutput => ({ place: [{ side: 'bid', price: 0.5, count: 10, timeInForce: 'good_till_canceled', postOnly: true, reduceOnly: false, purpose: why.startsWith('train') ? 'entry' : 'quote', edge: 0, why }], cancel: [], notes: [] });
  const q = plan('maker bid'); applyFvGate(q, 0.56, 0, DEFAULT_FEES, tm); assert.equal(q.place.length, 0);
  const t = plan('train: YES at 0.50 (maker at 0.50)'); applyFvGate(t, 0.56, 0, DEFAULT_FEES, tm); assert.equal(t.place.length, 1);
  const t2 = plan('train: YES at 0.50 (maker at 0.50)'); applyFvGate(t2, 0.52, 0, DEFAULT_FEES, tm); assert.equal(t2.place.length, 0);
  assert.equal(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32) }).strategy.loserExits?.trainMargin, undefined);
  assert.equal(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), TRAINING_GATE_MARGIN: '0.03' }).strategy.loserExits?.trainMargin, 0.03);
});

test('FV_ENTRY_GATE_SERIES_MARGINS: a series or *suffix pattern raises that series\' gate margins, others keep theirs', () => {
  const c = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), FV_ENTRY_GATE_SERIES_MARGINS: 'KXETHD=0.10,*15M=0.15' }).strategy;
  assert.deepEqual(c.loserExits!.seriesMargins, [{ pattern: 'KXETHD', margin: 0.1 }, { pattern: '*15M', margin: 0.15 }]);
  assert.equal(base.loserExits!.seriesMargins, undefined);
  assert.throws(() => loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), FV_ENTRY_GATE_SERIES_MARGINS: 'KXETHD=0.9' }));
  const sol = gateCfgFor(c, 'KXSOL15M-25OCT261530-30').loserExits!;
  assert.equal(sol.gateMargin, 0.15); assert.equal(sol.gateQuoteMargin, 0.15);
  const ethd = gateCfgFor(c, 'KXETHD-25OCT2617-T3999.99').loserExits!;
  assert.equal(ethd.gateMargin, 0.1); assert.equal(ethd.gateQuoteMargin, 0.12, 'never lowers the quote cushion');
  assert.equal(gateCfgFor(c, 'KXBTC-25OCT2617-B110000'), c);
  // In applyFvGate: a YES at 0.60 with fair value 0.70 passes the 6c gate but not the 15c 15-minute margin.
  const plan = (): StrategyOutput => ({ cancel: [], notes: [], place: [{ side: 'bid', price: 0.6, count: 5, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'entry', edge: 0.1, why: 'cross' }] });
  assert.equal(applyFvGate(plan(), 0.7, 0, DEFAULT_FEES, gateCfgFor(c, 'KXBTC-X')), 0);
  assert.equal(applyFvGate(plan(), 0.7, 0, DEFAULT_FEES, gateCfgFor(c, 'KXSOL15M-X')), 1);
});

test('TRAINING_SKIP_SERIES: parsed as series or *suffix patterns; seriesMatches reads a ticker\'s series', () => {
  assert.deepEqual(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), TRAINING_SKIP_SERIES: '*15M, KXETH' }).strategy.trainSkipSeries, ['*15M', 'KXETH']);
  assert.equal(base.trainSkipSeries, undefined);
  assert.throws(() => loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), TRAINING_SKIP_SERIES: 'kx eth' }));
  assert.ok(seriesMatches('*15M', 'KXSOL15M-25OCT261530-30'));
  assert.ok(!seriesMatches('*15M', 'KXSOLD-25OCT2617-T200'));
  assert.ok(seriesMatches('KXETH', 'KXETH-25OCT2617-B4000'));
  assert.ok(!seriesMatches('KXETH', 'KXETHD-25OCT2617-T4000'));
});

test('LOSER_CUT_MODE / LOSER_CUT_STATE: stop sells at half the entry price; the state splits never- and once-in-profit', () => {
  const c = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), LOSER_CUT_MODE: 'stop', LOSER_STOP_DROP: '0.4', LOSER_CUT_STATE: 'never' }).strategy.loserExits!;
  assert.equal(c.cutMode, 'stop'); assert.equal(c.stopDrop, 0.4); assert.equal(c.cutState, 'never');
  const L = (o: object) => ({ loserExits: { ...cfg.loserExits!, window: false, ...o } });
  // Bought at 0.55, bid 0.25 (under half), fair value 0.30 (above the bid: the fair mode would not sell).
  const down = long({ bestBid: { price: 0.25, size: 20 }, bestAsk: { price: 0.27, size: 20 }, pFair: 0.3 });
  assert.equal(loserExit(down, L({})), undefined, 'fair mode: the market does not overpay');
  assert.match(loserExit(down, L({ cutMode: 'stop' }))!.why, /^loser cut stop: bid 0\.25 at or below 50% of the entry 0\.55/);
  assert.equal(loserExit(long({ bestBid: { price: 0.3, size: 20 }, bestAsk: { price: 0.32, size: 20 }, pFair: 0.35 }), L({ cutMode: 'stop' })), undefined, 'above half: holds');
  // Never vs once in profit: a peak bid of 0.70 cleared the cost; 0.56 did not (exit fee).
  const once = { ...down, profitPeakSidePrice: 0.7 }, never = { ...down, profitPeakSidePrice: 0.56 };
  assert.match(loserExit(once, L({ cutMode: 'stop', cutState: 'once' }))!.why, /\(was in profit\)/);
  assert.equal(loserExit(never, L({ cutMode: 'stop', cutState: 'once' })), undefined);
  assert.match(loserExit(never, L({ cutMode: 'stop', cutState: 'never' }))!.why, /\(never in profit\)/);
  assert.equal(loserExit(once, L({ cutMode: 'stop', cutState: 'never' })), undefined);
});

test('LOSER_CUT_MODE=agree: sells only when the fair value fell to half the entry and the bid less the fee pays at least it; LOSER_CUT_MAX_TAU', () => {
  const L = (o: object) => ({ loserExits: { ...cfg.loserExits!, window: false, cutMode: 'agree' as const, ...o } });
  // Bought at 0.55; fair value 0.25 (under half); bid 0.28 less a ~1.4c fee >= 0.25: sells.
  const ok = long({ bestBid: { price: 0.28, size: 20 }, bestAsk: { price: 0.3, size: 20 }, pFair: 0.25 });
  assert.match(loserExit(ok, L({}))!.why, /^loser cut agree: fair value 0\.250 at or below 50% of the entry 0\.55/);
  // A collapsed bid under the fair value: holds (the stop's failure).
  assert.equal(loserExit(long({ bestBid: { price: 0.1, size: 20 }, bestAsk: { price: 0.3, size: 20 }, pFair: 0.25 }), L({})), undefined);
  // Fair value above half the entry: holds.
  assert.equal(loserExit(long({ bestBid: { price: 0.4, size: 20 }, bestAsk: { price: 0.42, size: 20 }, pFair: 0.35 }), L({})), undefined);
  // LOSER_CUT_MAX_TAU: 400 s left, a 300 s limit holds it.
  assert.equal(loserExit(ok, L({ cutMaxTau: 300 })), undefined);
  assert.ok(loserExit({ ...ok, tauSec: 200 }, L({ cutMaxTau: 300 })));
});
