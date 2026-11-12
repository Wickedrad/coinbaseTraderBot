import './tmpScope'; // one temp folder per run, removed at exit
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { DEFAULT_FEES } from '../bot/fees';
import { DEFAULT_SNN } from '../bot/snn/params';
import { TapeWriter } from '../research/snnTape';
import { replayAtlasSnnTape, type FrozenSnnEvidence } from '../research/opportunity/snnReplay';
import { DirectionPaperAccount, type DirectionPaperPolicy, type SnapshotEvidence } from '../research/opportunity/directionPaper';
import type { ProfitPolicy } from '../research/opportunity/profitExit';
import type { SnnModelFile } from '../bot/snn/network';

const T = Date.UTC(2026, 9, 22, 12), sha = 'a'.repeat(64);
const profit = JSON.parse(fs.readFileSync('research/opportunity/examples/profit-policy.json', 'utf8')) as ProfitPolicy;
const policy: DirectionPaperPolicy = { startingCash: 200, maximumPositionCost: 20, maximumContracts: 20, maximumOpenPositions: 2,
  minimumNetTakeUsd: 0.01, targetContractRoi: 0.05, minimumSignalProbability: 0.6, maximumQuoteAgeMs: 2000, maximumSignalAgeMs: 2000, saleBufferMs: 30000 };
const contract = (ticker = 'TEST') => ({ ticker, asset: 'BTC', openTime: T, closeTime: T + 900000, termsKnownAt: T,
  terms: { kind: 'greater' as const, strike: 100 }, settlementReference: 'fixture' });
const fees = { schedule: DEFAULT_FEES, knownAt: T, effectiveFrom: T, sourceSha256: sha, basis: 'observed-as-of' as const };
const quote = (at: number, bid: number, ask: number, size = 20, ticker = 'TEST'): SnapshotEvidence => ({ ticker, at, knownAt: at, sourceSha256: sha,
  bids: [{ price: bid, size }], asks: [{ price: ask, size }], underlying: { price: 100 + (at - T) / 100000, knownAt: at } });
const signal = (at = T, direction: 'up' | 'down' = 'up') => ({ id: `${at}`, modelId: sha, asOf: at, producedAt: at, featuresKnownAt: at,
  byAt: T + 870000, direction, probability: 0.7 });

test('$200 paper ledger charges both fees, rejects a fee-negative 5% move, then credits a small net sale', async () => {
  const a = new DirectionPaperAccount(policy, profit, T), c = contract();
  assert.equal(await a.observe(c, quote(T, 0.39, 0.40), fees, signal()), 'entry-attempt');
  assert.ok(Math.abs(a.report().endingCash - 191.66) < 1e-9);
  assert.equal(await a.observe(c, quote(T + 1000, 0.42, 0.43), fees, null), 'manage');
  assert.equal(a.report().sales, 0, '5% gross is a 29 cent net loss, not a profit');
  assert.equal(await a.observe(c, quote(T + 2000, 0.45, 0.46), fees, null), 'exit-attempt');
  const r = a.report(); assert.ok(Math.abs(r.simulatedNetRealizedUsd - 0.31) < 1e-9);
  assert.ok(Math.abs(r.endingCash - 200.31) < 1e-9); assert.ok(Math.abs(r.paidFees - 0.69) < 1e-9);
  assert.equal(r.unresolvedPositions.length, 0); assert.equal(r.hourly[0].goalMet, false);
  assert.ok(Math.abs(r.pacer.realizedHourUsd - 0.31) < 1e-9); assert.ok(Number(a.sales[0].underlyingMoveBps) > 0);
});
test('empty archived snapshots explicitly block executable-profit verification', async () => {
  const a = new DirectionPaperAccount(policy, profit, T), c = contract();
  assert.equal(await a.observe(c, { ...quote(T, 0.39, 0.4), bids: [], asks: [] }, fees, signal()), 'empty-observed-book');
  assert.equal(a.report().endingCash, 200); assert.equal(a.report().fills, 0); assert.equal(a.report().feeAsOfVerified, null);
});
test('NO positions use the actual opposite book, and partial sales retain the unsold basis', async () => {
  const a = new DirectionPaperAccount(policy, profit, T), c = contract();
  await a.observe(c, quote(T, 0.60, 0.61), fees, signal(T, 'down'));
  assert.equal(a.fills[0].side, 'no'); assert.ok(Math.abs(Number(a.fills[0].sidePrice) - 0.4) < 1e-9);
  await a.observe(c, quote(T + 1000, 0.54, 0.55, 10), fees, null);
  let r = a.report(); assert.equal(r.unresolvedPositions[0].quantity, 10); assert.ok(Math.abs(r.remainingCostBasisUsd - 4.17) < 1e-9);
  await a.observe(c, quote(T + 2000, 0.49, 0.50, 10), fees, null);
  r = a.report(); assert.equal(r.unresolvedPositions.length, 0); assert.ok(r.simulatedNetRealizedUsd > 0);
  assert.ok(Math.abs(r.endingCash - 200 - r.simulatedNetRealizedUsd) < 1e-9);
});
test('many small fee-net sales can satisfy the hourly goal without a per-trade $4.50 gate', async () => {
  const a = new DirectionPaperAccount(policy, profit, T);
  for (let i = 0; i < 15; i++) {
    const at = T + i * 10000, ticker = `SMALL-${i}`, c = contract(ticker);
    await a.observe(c, quote(at, 0.39, 0.40, 20, ticker), fees, signal(at));
    await a.observe(c, quote(at + 1000, 0.45, 0.46, 20, ticker), fees, null);
  }
  const r = a.report(); assert.equal(r.sales, 15); assert.ok(r.simulatedNetRealizedUsd > 4.5);
  assert.ok(r.hourly[0].goalMet); assert.ok(Math.abs(r.endingCash - 200 - r.simulatedNetRealizedUsd) < 1e-9);
});
test('tiny partial sales must cover their own native rounded closing fee', async () => {
  const a = new DirectionPaperAccount({ ...policy, maximumContracts: 1, minimumNetTakeUsd: 0.001 }, profit, T), c = contract();
  await a.observe(c, quote(T, 0.39, 0.40, 1), fees, signal());
  assert.equal(await a.observe(c, quote(T + 1000, 0.58, 0.59, 0.03), fees, null), 'manage');
  assert.equal(a.report().sales, 0, '0.03 contracts would lose $0.0026 after the native closing fee');
});
test('resting profit exits need later observed trades, respect the initial queue, and credit actual partial net sales', async () => {
  const a = new DirectionPaperAccount({ ...policy, exitMode: 'resting-maker' }, profit, T), c = contract();
  const q = quote(T, 0.39, 0.4); q.asks.push({ price: 0.42, size: 5 });
  await a.observe(c, q, fees, signal());
  const trade = { ticker: c.ticker, at: T + 2000, exchangeAt: T + 2000, price: 0.42, quantity: 10, takerSide: 'yes' as const, sourceSha256: sha };
  a.observeTrade({ ...trade, exchangeAt: T, at: T + 500 });
  assert.equal(a.report().sales, 0, 'a delayed same-second print cannot fill an order created after it');
  a.observeTrade(trade);
  assert.equal(a.report().unresolvedPositions[0].quantity, 15, 'five ahead in the initial queue are consumed before five of ours');
  assert.ok(a.report().simulatedNetRealizedUsd > 0);
  a.observeTrade({ ...trade, at: T + 3000, exchangeAt: T + 3000, quantity: 15 });
  const r = a.report(); assert.equal(r.unresolvedPositions.length, 0); assert.equal(r.makerSales, 2);
  assert.ok(Math.abs(r.endingCash - 200.06) < 1e-9); assert.ok(Math.abs(r.paidFees - 0.34) < 1e-9);
});
test('unobserved maker exits and trades after the sale deadline never become assumed profits', async () => {
  const a = new DirectionPaperAccount({ ...policy, exitMode: 'resting-maker' }, profit, T), c = contract();
  await a.observe(c, quote(T, 0.39, 0.4), fees, signal());
  await a.observe(c, quote(T + 1000, 0.5, 0.51), fees, null);
  assert.equal(a.report().sales, 0, 'a crossed later snapshot is not a printed maker fill');
  a.observeTrade({ ticker: c.ticker, at: T + 880000, exchangeAt: T + 880000, price: 0.6, quantity: 100, takerSide: 'yes', sourceSha256: sha });
  assert.equal(a.report().sales, 0); assert.equal(a.report().unresolvedPositions.length, 1);
});
test('NO maker exits use actual NO-taker prints and the complementary YES order price', async () => {
  const a = new DirectionPaperAccount({ ...policy, exitMode: 'resting-maker' }, profit, T), c = contract();
  await a.observe(c, quote(T, 0.60, 0.61), fees, signal(T, 'down'));
  const trade = { ticker: c.ticker, at: T + 1000, exchangeAt: T + 1000, price: 0.58, quantity: 20, takerSide: 'yes' as const, sourceSha256: sha };
  a.observeTrade(trade); assert.equal(a.report().sales, 0);
  a.observeTrade({ ...trade, at: T + 2000, exchangeAt: T + 2000, takerSide: 'no' });
  const r = a.report(); assert.equal(r.unresolvedPositions.length, 0); assert.equal(r.makerSales, 1);
  assert.ok(Math.abs(r.endingCash - 200.06) < 1e-9);
});
test('snapshot cash study never invents liquidity, refills cash or marks an unresolved expiry profitable', async () => {
  const a = new DirectionPaperAccount({ ...policy, maximumOpenPositions: 1 }, profit, T), c = contract();
  await a.observe(c, quote(T, 0.39, 0.40), fees, signal());
  assert.equal(await a.observe(c, quote(T, 0.39, 0.40), fees, signal()), 'duplicate-book');
  await a.observe(c, quote(T + 1000, 0.45, 0.46), fees, null);
  await a.observe(c, quote(T + 61000, 0.39, 0.40), fees, signal(T + 61000));
  assert.equal(a.report().fills, 2, 'consumed ask depth is not restored after one minute');
  await a.observe(c, quote(T + 62000, 0.39, 0.40, 40), fees, signal(T + 62000));
  assert.equal(a.report().fills, 3, 'only genuinely additional displayed depth can be taken');
  assert.equal(await a.observe(c, quote(T + 900000, 0.99, 0.999), fees, null), 'expired-unresolved-exposure');
  const r = a.report(); assert.equal(r.unresolvedPositions.length, 1); assert.equal(r.noRefills, true); assert.equal(r.actualVenueProfitVerified, false);
  assert.ok(Math.abs(r.endingCash + r.remainingCostBasisUsd - 200 - r.simulatedNetRealizedUsd) < 1e-9);
});
test('deadline sales book losses and future fees, incompatible horizons and range contracts cannot open exposure', async () => {
  const a = new DirectionPaperAccount(policy, profit, T), c = contract();
  assert.equal(await a.observe(c, quote(T, 0.39, 0.40), { ...fees, knownAt: T + 1 }, signal()), 'unavailable-fees');
  assert.equal(await a.observe(c, quote(T + 1000, 0.39, 0.40), fees, { ...signal(T + 1000), byAt: T + 3600000 }), 'unavailable-direction-signal');
  assert.equal(await a.observe({ ...c, terms: { kind: 'between', strike: 99, cap: 101 } }, quote(T + 2000, 0.39, 0.40), fees, signal(T + 2000)), 'nonmonotone-contract');
  await a.observe(c, quote(T + 3000, 0.39, 0.40), fees, signal(T + 3000));
  await a.observe(c, quote(T + 870000, 0.35, 0.36), fees, null);
  const r = a.report(); assert.ok(r.simulatedNetRealizedUsd < 0); assert.equal(r.unresolvedPositions.length, 0);
  assert.equal(a.sales[0].reason, 'sale-deadline'); assert.ok(Math.abs(r.endingCash - 200 - r.simulatedNetRealizedUsd) < 1e-9);
});
test('native direction-only replay exports learned weights before the cutoff and ignores all contract labels', (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-native-direction-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'input.tape'), w = new TapeWriter(file);
  for (let s = 0; s <= 1020; s++) {
    w.step(T + s * 1000, [{ key: 'BTC-15m', asset: 'BTC', price: 100 + s / 100, mid: undefined, values: { rsi: s % 100 } }]);
    if (s === 5) w.settle('fixture', 1, T + s * 1000);
  } w.close();
  let evidence: FrozenSnnEvidence | undefined, model: SnnModelFile | undefined;
  const states: string[] = [];
  const r = replayAtlasSnnTape(file, { variant: 'S6', sourceSha256: sha, studyPolicyId: 'prospective-2026-11-09-v1', inputLagMs: 0, directionOnly: true, learningBefore: T + 1000000,
    maximumInputPriceAgeMs: 3000, params: { ...DEFAULT_SNN, nE: 8, nI: 2, nL1: 4 },
    onFrozenModel: (m, e) => { model = m; evidence = e; }, onState: (s) => states.push(s.provenance.replayProfile!) });
  assert.equal(r.frozenModelExported, true); assert.equal(r.ignoredContractOperations, 1);
  assert.ok(evidence!.trainedThrough < T + 1000000); assert.ok(evidence!.changedDirectionHeads > 0);
  assert.equal(evidence!.changedContractHeads, 0); assert.notEqual(evidence!.initialWeightsSha256, evidence!.frozenWeightsSha256);
  assert.ok(Object.keys(model!.columns!).length > 0); assert.ok(states.every((s) => s === 'direction-inputs-only-v1'));
});
