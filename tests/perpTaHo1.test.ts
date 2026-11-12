import assert from 'node:assert/strict';
import { test } from 'node:test';
import { rvTerciles, rv60, percentile } from '../research/perpTaRegime';
import { ho1Of, rulebook, type CoinOut, type Frozen } from '../research/perpTaBlind';

const MIN = 60_000, DAY = 86_400_000;

test('perp TA regime v1: RV60 needs 50 returns and the bar before; terciles need 7 days of history', () => {
  assert.equal(percentile(Float64Array.from([1, 2, 3, 4]), 100 / 3), 2); // numpy: 1 + 3 * (1/3)
  const n = 12 * 1440, t0 = Date.UTC(2025, 0, 1);
  // Days 0-9 calm (1 bp a minute, alternating), day 10 on wild (10 bp): wild minutes land in HIGH once the window has 7 days.
  const close = new Float64Array(n);
  let c = 100;
  for (let i = 0; i < n; i++) { const r = (i < 10 * 1440 ? 1e-4 : 1e-3) * (i % 2 ? 1 : -1) * (1 + (i % 7) / 10); c *= Math.exp(r); close[i] = c; }
  const bar = (i: number) => i !== 5000; // one missing bar
  const rv = rv60(n, bar, (i) => close[i]);
  assert.ok(Number.isNaN(rv[30]), 'under 50 returns');
  assert.ok(Number.isNaN(rv[5001]), 'no label after a missing bar');
  assert.ok(Number.isFinite(rv[5002]), '59 returns left after one missing bar');
  const ter = rvTerciles(t0, n, bar, (i) => close[i], 0, n);
  assert.equal(ter[3 * 1440], -1, 'day 3: fewer than 7 days of RV60 behind it');
  assert.ok(ter[8 * 1440 + 100] >= 0, 'day 8 labelled');
  assert.equal(ter[10 * 1440 + 120], 2, 'wild after calm is HIGH');
});

const days = (n: number, f: (k: number) => number) => Object.fromEntries(Array.from({ length: n }, (_, k) => [new Date(Date.UTC(2025, 6, 1) + k * DAY).toISOString().slice(0, 10), f(k)]));

test('perp TA HO-1: folds, RV terciles and the placebo decide; each failure is named', () => {
  // 96 days, fold 3 (days 32-47) loses; 5 of 6 folds won.
  const bd = days(96, (k) => (k >= 32 && k < 48 ? -2 : 3));
  const taken = [{ x: 40, rnd: -10, ter: 0 }, { x: 30, rnd: -12, ter: 1 }, { x: -5, rnd: -8, ter: 2 }];
  const ok = ho1Of(bd, taken, [700, 700, 700], 500);
  assert.equal(ok.days, 96);
  assert.equal(ok.folds_won, 5);
  assert.equal(ok.terciles_won, 2);
  assert.equal(ok.terciles_covered, 3);
  assert.equal(ok.beats_placebo, true);
  assert.deepEqual(ok.why, []);
  assert.equal(ok.worst_fold_per_hour, +(-2 / 24).toFixed(4));
  // Too few days; too few folds won; a deep fold.
  assert.ok(ho1Of(days(80, () => 1), taken, [700, 700, 700], 500).why.some((w) => /80 held-out days < 90/.test(w)));
  const bad = ho1Of(days(96, (k) => (k < 48 ? -30 : 5)), taken, [700, 700, 700], 500);
  assert.ok(bad.why.some((w) => /3 of 6 folds won/.test(w)));
  assert.ok(bad.why.some((w) => /worst fold/.test(w)));
  // A tercile with under 100 h is not covered: one won tercile left.
  const thin = ho1Of(bd, taken, [700, 50, 700], 500);
  assert.equal(thin.terciles_covered, 2);
  assert.ok(thin.why.some((w) => /1 of 3 RV terciles won/.test(w)));
  // The random entries do better: fails on the placebo; no baseline at all fails closed.
  assert.ok(ho1Of(bd, taken.map((t) => ({ ...t, rnd: 50 })), [700, 700, 700], 500).why.some((w) => /not above its placebo/.test(w)));
  assert.ok(ho1Of(bd, taken.map(({ x, ter }) => ({ x, ter })), [700, 700, 700], 500).why.some((w) => /no placebo/.test(w)));
  // A 493-day block: folds stay 16 days long, so 16 days at -$0.80/h at the end fail the worst-fold rule.
  const long = ho1Of(days(493, (k) => (k >= 477 ? -0.8 * 24 : 0.2 * 24)), taken, [700, 700, 700], 500);
  assert.equal(long.folds, 30);
  assert.ok(long.why.some((w) => /worst fold/.test(w)), long.why.join('; '));
  assert.ok(!long.why.some((w) => /folds won/.test(w)), 'won 29 of 30');
});

test('perp TA blind rulebook carries the HO-1 block; signals without the baseline fail closed', () => {
  const seal = '2025-07-01T00:00:00.000Z', s0 = Date.parse(seal), end = s0 + 120 * DAY;
  const fz = { schema: 'perpta-frozen1', run: '1', sha: 's', at: seal, seal, validFrom: '2024-01-01T00:00:00.000Z', costs: { takerBps: 12, makerBps: 5, halfSpreadBps: 0.2, ttBps: 1 }, passing: 2, hash: 'abcdef0123456789', cands: [{ id: 'b', a: 'BTC' }, { id: 'e', a: 'ETH' }] } as unknown as Frozen;
  // A trade a day on each coin, +30 bps, its random-entry baseline -10 bps, terciles in turn; 4-hour holds.
  const sigs = (off: number, base: boolean) => Array.from({ length: 119 }, (_, k) => {
    const t = s0 + k * DAY + off * 3_600_000;
    return (base ? [t, 30, t + 4 * 3_600_000, 240, 0, -10, k % 3] : [t, 30, t + 4 * 3_600_000, 240, 0]) as [number, number, number, number, number, number?, number?];
  });
  const coin = (a: string, id: string, off: number, base: boolean): CoinOut => ({
    schema: 'perpta-blind1', asset: a, hash: fz.hash, sealFrom: seal, sealTo: new Date(end).toISOString(), sealDays: 120, replication: [], notes: [],
    cands: [{ id, sealed: {} as never, signals: sigs(off, base) }], terMinutes: [57600, 57600, 57600, 0],
  });
  const b = rulebook(fz, [coin('BTC', 'b', 1, true), coin('ETH', 'e', 2, true)], ['b', 'e'], { resamples: 500 });
  assert.equal(b.ho1.days, 120);
  assert.equal(b.ho1.folds, 7); // 120 days in folds of HO-1's 16 days
  assert.equal(b.ho1.folds_won, 7);
  assert.equal(b.ho1.terciles_won, 3);
  assert.equal(b.ho1.beats_placebo, true);
  assert.deepEqual(b.ho1.tercile_hours, [960, 960, 960]);
  assert.ok(!b.why.some((w) => w.startsWith('HO-1')), b.why.join('; '));
  // A set frozen before the baseline was recorded cannot show it beats its placebo, and has no terciles.
  const old = rulebook(fz, [coin('BTC', 'b', 1, false), coin('ETH', 'e', 2, false)], ['b', 'e'], { resamples: 500 });
  assert.equal(old.pass, false);
  assert.ok(old.why.some((w) => /no placebo/.test(w)));
  assert.ok(old.why.some((w) => /0 of 3 RV terciles won/.test(w)));
});
