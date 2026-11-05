import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadConfig } from '../bot/config';
import { fitAnchorWeight, MarketAnchor, DEFAULT_MARKET_ANCHOR } from '../bot/model/marketAnchor';
import { logit, sigmoid } from '../bot/util/num';

// Deterministic generator.
const rng = (seed: number) => () => ((seed = (seed * 16807) % 2147483647) / 2147483647);

/** Markets where the truth is logit p = a + wTrue * d (the bot's disagreement d is worth wTrue). */
function sample(n: number, wTrue: number, seed = 7) {
  const r = rng(seed);
  return Array.from({ length: n }, () => {
    const a = (r() - 0.5) * 3, d = (r() - 0.5) * 2;
    const y: 0 | 1 = r() < sigmoid(a + wTrue * d) ? 1 : 0;
    return { a, d, y };
  });
}

test('market anchor: the fitted weight finds how much of the disagreement is right', () => {
  for (const wTrue of [0, 0.4, 1]) {
    const w = fitAnchorWeight(sample(6000, wTrue), 0.5, 0.5, 1.5);
    assert.ok(Math.abs(w - wTrue) < 0.15, `w ${w} vs true ${wTrue}`);
  }
});

test('market anchor: a thin record stays near the prior, and w never leaves [0, maxW]', () => {
  assert.equal(fitAnchorWeight([], 0.5, 0.5, 1.5), 0.5);
  const w = fitAnchorWeight(sample(10, 0), 0.5, 0.5, 1.5);
  assert.ok(Math.abs(w - 0.5) < 0.4, `w ${w}`);
  // Disagreement exactly wrong every time: w floors at 0 rather than flipping the bot's side.
  const wrong = Array.from({ length: 500 }, (_, i) => ({ a: 0, d: i % 2 ? 1 : -1, y: (i % 2 ? 0 : 1) as 0 | 1 }));
  assert.equal(fitAnchorWeight(wrong, 0.5, 0.5, 1.5), 0);
});

test('market anchor: price is the market at w = 0, the bot at w = 1, and the raw price when off', () => {
  const t = 'KXBTCD-26NOV0217-T70000';
  const at = (w: number) => new MarketAnchor({ ...DEFAULT_MARKET_ANCHOR, enabled: true, fixedW: w }).price(t, 1800, 0.4, 0.6);
  assert.ok(Math.abs(at(0) - 0.4) < 1e-9);
  assert.ok(Math.abs(at(1) - 0.6) < 1e-9);
  assert.ok(Math.abs(at(0.5) - sigmoid((logit(0.4) + logit(0.6)) / 2)) < 1e-9);
  assert.equal(new MarketAnchor(DEFAULT_MARKET_ANCHOR).price(t, 1800, 0.4, 0.6), 0.6);
});

test('market anchor: learns per bucket from settled markets, scoring each before it learns from it', () => {
  let now = 0;
  const a = new MarketAnchor({ ...DEFAULT_MARKET_ANCHOR, enabled: true, prior: 0.5, priorSd: 0.3 }, undefined, () => now);
  const r = rng(3);
  // The bot's disagreement is noise: the market is the truth.
  for (let i = 0; i < 400; i++) {
    const t = `KXBTC15M-26NOV02${i}-15`;
    const pm = 0.2 + 0.6 * r();
    a.observe(t, 520, pm, Math.min(0.97, Math.max(0.03, pm + (r() - 0.5) * 0.4)));
    now += 1000;
    a.settle(t, r() < pm ? 'yes' : 'no');
  }
  const w = a.weight('KXBTC15M-26NOV029999-15', 520);
  assert.ok(w < 0.2, `noise disagreement should earn little weight, got ${w}`);
  // Another bucket learned nothing: the prior.
  assert.equal(a.weight('KXBTC15M-26NOV029999-15', 200), 0.5);
  const s = a.status();
  assert.equal(s.scored, 400);
  assert.ok(s.llRaw! > s.llMarket!);
});

test('market anchor: config is off by default and reads its lab settings', () => {
  const base = { DASHBOARD_TOKEN: 'x'.repeat(32) };
  assert.equal(loadConfig(base).strategy.marketAnchor.enabled, false);
  assert.equal(loadConfig(base).strategy.marketAnchor.fixedW, undefined);
  const c = loadConfig({ ...base, MARKET_ANCHOR: 'true', MARKET_ANCHOR_W: '0.25', MARKET_ANCHOR_SHUFFLE: 'true' }).strategy.marketAnchor;
  assert.equal(c.enabled, true);
  assert.equal(c.fixedW, 0.25);
  assert.equal(c.shuffle, true);
});

test('market anchor by series: a series whose disagreement is right earns its own weight, the rest keep the bucket\'s', () => {
  let now = 0;
  const a = new MarketAnchor({ ...DEFAULT_MARKET_ANCHOR, enabled: true, bySeries: true, window: 2000 }, undefined, () => now);
  const r = rng(11);
  for (let i = 0; i < 1500; i++) {
    const good = i % 2 === 0;
    const t = `${good ? 'KXDOGE' : 'KXBTCD'}-26NOV02${i}-T1`;
    const pm = 0.2 + 0.6 * r();
    const pb = Math.min(0.95, Math.max(0.05, pm + (r() - 0.5) * 0.4));
    a.observe(t, 1900, pm, pb);
    now += 1000;
    // DOGE: the bot is the truth; BTC: the market is.
    a.settle(t, r() < (good ? pb : pm) ? 'yes' : 'no');
  }
  const wDoge = a.weight('KXDOGE-26NOV02X-T1', 1900), wBtc = a.weight('KXBTCD-26NOV02X-T1', 1900);
  assert.ok(wDoge > 0.7, `doge ${wDoge}`);
  assert.ok(wBtc < 0.3, `btc ${wBtc}`);
  assert.ok(a.status().series);
});

test('market anchor min w: a learned weight under the floor prices at the market', () => {
  const a = new MarketAnchor({ ...DEFAULT_MARKET_ANCHOR, enabled: true, prior: 0.1, priorSd: 0.01, minW: 0.25 });
  assert.equal(a.weight('KXBTC15M-26NOV04-15', 500), 0);
  assert.equal(a.price('KXBTC15M-26NOV04-15', 500, 0.4, 0.6), 0.4);
  const b = new MarketAnchor({ ...DEFAULT_MARKET_ANCHOR, enabled: true, prior: 0.5, priorSd: 0.01, minW: 0.25 });
  assert.equal(b.weight('KXBTC15M-26NOV04-15', 500), 0.5);
});

test('quote side gate: off by default; on, a price on the mid quotes neither side, a price above it bids only', async () => {
  const base = { DASHBOARD_TOKEN: 'x'.repeat(32) };
  assert.equal(loadConfig(base).strategy.quoteSideGate, 0);
  assert.equal(loadConfig({ ...base, QUOTE_SIDE_GATE: '0.02' }).strategy.quoteSideGate, 0.02);
});

test('market anchor split: a disagreement that fades the favourite and is wrong loses its weight, the other keeps it', () => {
  let now = 0;
  const a = new MarketAnchor({ ...DEFAULT_MARKET_ANCHOR, enabled: true, split: true, window: 3000 }, undefined, () => now);
  const r = rng(5);
  for (let i = 0; i < 2500; i++) {
    const t = `KXBTC15M-26NOV05${i}-15`;
    const pm = r() < 0.5 ? 0.15 + 0.1 * r() : 0.75 + 0.1 * r();
    const toward = r() < 0.5;
    // The bot moves 8c toward 0.5 or 8c away from it.
    const pb = pm > 0.5 ? (toward ? pm - 0.08 : Math.min(0.97, pm + 0.08)) : (toward ? pm + 0.08 : Math.max(0.03, pm - 0.08));
    a.observe(t, 520, pm, pb);
    now += 1000;
    // Toward 0.5: the market is the truth. Away: the bot is.
    a.settle(t, r() < (toward ? pm : pb) ? 'yes' : 'no');
  }
  const tk = 'KXBTC15M-26NOV05X-15';
  const wToward = a.weight(tk, 520, ':t'), wAway = a.weight(tk, 520, ':a');
  assert.ok(wToward < 0.3, `toward ${wToward}`);
  assert.ok(wAway > 0.7, `away ${wAway}`);
  // The price uses the direction: fading a 0.8 favourite to 0.7 stays near 0.8; pushing it to 0.88 keeps most of the move.
  assert.ok(a.price(tk, 520, 0.8, 0.7) > 0.77);
  assert.ok(a.price(tk, 520, 0.8, 0.88) > 0.86);
  const g = a.status().groups.updown15m.find((b: any) => b.lo <= 520 && 520 < b.hi) as any;
  assert.ok(g.toward !== undefined && g.away !== undefined);
});
