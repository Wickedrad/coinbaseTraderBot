// Tennis TA rulebook trial statistics (research/tennisTaStats.ts): clustered t, Student tail, BH, CSCV PBO and the
// family A / B discovery funnels of pre-registration section 6.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { rng } from '../research/stats';
import { bhReject, clusteredT, cscvPbo, discoverA, discoverB, meanOf, pairedZ, perHour24, tSf } from '../research/tennisTaStats';
import { ClusterAcc, emptyStats, type CellResult, type ConfigDay, type ConfigRun, type PairDiff } from '../research/tennisTaTypes';

const gauss = (r: () => number) => Math.sqrt(-2 * Math.log(r() + 1e-12)) * Math.cos(2 * Math.PI * r());
const close = (a: number, b: number, tol: number, msg?: string) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ''} ${a} vs ${b} (tol ${tol})`);

/** Consecutive UTC days from a start date. */
function days(from: string, count: number): string[] {
  const t0 = Date.parse(`${from}T00:00:00Z`);
  return Array.from({ length: count }, (_, i) => new Date(t0 + i * 86_400_000).toISOString().slice(0, 10));
}

test('clusteredT matches a brute-force cluster-robust computation from raw entries with day labels', () => {
  const r = rng(7);
  const xs: Array<{ x: number; day: string }> = [];
  for (const [k, day] of days('2025-03-20', 25).entries()) {
    const shock = 0.3 * gauss(r); // a shared day effect: entries of one day are correlated
    const n = 1 + (k % 5);
    for (let i = 0; i < n; i++) xs.push({ x: 0.05 + shock + gauss(r), day });
  }
  const acc = new ClusterAcc();
  for (const { x, day } of xs) acc.add(x, day);
  acc.flush();
  const s = acc.total;
  // brute force
  const n = xs.length, m = xs.reduce((a, e) => a + e.x, 0) / n;
  const byDay = new Map<string, number>();
  for (const e of xs) byDay.set(e.day, (byDay.get(e.day) ?? 0) + (e.x - m));
  const C = byDay.size;
  const V = ([...byDay.values()].reduce((a, u) => a + u * u, 0) / (n * n)) * (C / (C - 1));
  for (const mu0 of [0, 0.1, -0.2]) {
    const ct = clusteredT(s, mu0);
    close(ct.mean, m, 1e-12, 'mean');
    close(ct.se, Math.sqrt(V), 1e-12, 'se');
    close(ct.t, (m - mu0) / Math.sqrt(V), 1e-9, 't');
    assert.equal(ct.df, C - 1);
  }
  assert.equal(s.clusters, 25);
  close(meanOf(s), m, 1e-12);
  // folds hold their own clusters (months): March 20..31 = 12 days, April 13 days
  assert.equal(acc.folds['2025-03'].clusters, 12);
  assert.equal(acc.folds['2025-04'].clusters, 13);
  assert.ok(Number.isNaN(clusteredT(emptyStats()).t));
  assert.ok(Number.isNaN(meanOf(emptyStats())));
});

test('tSf: Student-t upper tail against known values, symmetry and the far tail', () => {
  close(tSf(1.645, 1e6), 0.05, 2e-4, 't 1.645 df 1e6');
  close(tSf(1.645, 1e6), 0.0499851, 2e-6, 'normal limit');
  close(tSf(2.0, 10), 0.0366940, 1e-6, 't 2 df 10');
  close(tSf(1, 1), 0.25, 1e-12, 'Cauchy');
  assert.equal(tSf(0, 7), 0.5);
  close(tSf(-2.0, 10), 1 - 0.0366940, 1e-6, 'lower side');
  // df = 2 has a closed form: P(T >= t) = 1 / ((sqrt(t^2+2) + t) sqrt(t^2+2)); check relative accuracy deep in the tail.
  for (const t of [0.5, 3, 30, 3000]) {
    const exact = 1 / ((Math.sqrt(t * t + 2) + t) * Math.sqrt(t * t + 2));
    assert.ok(Math.abs(tSf(t, 2) / exact - 1) < 1e-9, `df 2 t ${t}: ${tSf(t, 2)} vs ${exact}`);
  }
  assert.equal(tSf(Infinity, 5), 0);
  assert.ok(Number.isNaN(tSf(NaN, 5)));
  assert.ok(Number.isNaN(tSf(1, 0)));
});

test('pairedZ: mean daily difference over its standard error', () => {
  const d = [1, 2, 3, 4, 5];
  const pd: PairDiff = { clusters: d.length, sum: d.reduce((a, b) => a + b, 0), sumSq: d.reduce((a, b) => a + b * b, 0) };
  const z = pairedZ(pd);
  // mean 3, sd sqrt(2.5), se sqrt(2.5/5)
  close(z.z, 3 / Math.sqrt(0.5), 1e-12);
  assert.equal(z.days, 5);
  assert.equal(z.meanPerDay, 3);
  assert.ok(Number.isNaN(pairedZ({ clusters: 1, sum: 2, sumSq: 4 }).z));
});

test('bhReject: the Benjamini-Hochberg 1995 example, the design size and the step-up', () => {
  // Benjamini & Hochberg (1995), section 4: 15 p-values at q = 0.05 reject the four smallest.
  const p = [0.0001, 0.0004, 0.0019, 0.0095, 0.0201, 0.0278, 0.0298, 0.0344, 0.0459, 0.324, 0.4262, 0.5719, 0.6528, 0.759, 1.0];
  const perm = [14, 3, 9, 0, 12, 7, 1, 5, 11, 2, 8, 13, 4, 10, 6];
  const shuffled = perm.map((i) => p[i]);
  const rej = bhReject(shuffled, 0.05);
  assert.deepEqual([...rej].map((i) => shuffled[i]).sort((a, b) => a - b), [0.0001, 0.0004, 0.0019, 0.0095]);
  // 15 more untested hypotheses (p = 1) in the design: the cutoffs halve, 0.0095 > 0.05 * 4 / 30.
  assert.deepEqual([...bhReject(p, 0.05, 30)].sort((a, b) => a - b), [0, 1, 2]);
  // step-up: the smaller p fails its own rank but is rejected with the larger one
  assert.deepEqual([...bhReject([0.03, 0.031], 0.05)].sort(), [0, 1]);
  assert.equal(bhReject([0.03, NaN], 0.05).size, 0, 'NaN counts as 1');
  assert.equal(bhReject([], 0.1, 100).size, 0);
});

test('cscvPbo: about 0 when one config dominates every fold, about 0.5 for pure noise', () => {
  const r = rng(11);
  const dom = Array.from({ length: 10 }, (_, c) => Array.from({ length: 12 }, () => (c === 3 ? 1 : 0) + 0.1 * gauss(r)));
  const a = cscvPbo(dom);
  assert.equal(a.combos, 924, 'C(12, 6) splits, all enumerated');
  assert.equal(a.pbo, 0);
  assert.ok(a.logits.every((l) => l > 0));

  const r2 = rng(2026);
  const noise = Array.from({ length: 50 }, () => Array.from({ length: 12 }, () => gauss(r2)));
  const b = cscvPbo(noise, 12);
  assert.ok(Math.abs(b.pbo - 0.5) <= 0.2, `noise PBO ${b.pbo}`);
  // the in-sample winner of pure noise is often the out-of-sample loser: logits spread both ways
  assert.ok(b.logits.some((l) => l > 0) && b.logits.some((l) => l < 0));

  // sampling: fewer combinations than C(S, S/2), deterministic for a seed
  const c1 = cscvPbo(noise, 12, 200, 5), c2 = cscvPbo(noise, 12, 200, 5);
  assert.equal(c1.combos, 200);
  assert.equal(c1.pbo, c2.pbo);
  // 13 folds into 6 blocks of adjacent folds
  assert.equal(cscvPbo(noise.map((row) => [...row, 0]), 6).combos, 20);
  assert.ok(Number.isNaN(cscvPbo([[1, 2, 3, 4]]).pbo), 'one config: nothing to select');
});

test('perHour24 counts every hour of the inclusive day span', () => {
  assert.equal(perHour24(48, '2025-03-01', '2025-03-02'), 1);
  assert.equal(perHour24(24, '2025-03-01', '2025-03-01'), 1);
  close(perHour24(4.5 * 24 * 31, '2025-03-01', '2025-03-31'), 4.5, 1e-12);
  assert.ok(Number.isNaN(perHour24(1, '2025-03-02', '2025-03-01')));
});

// --- family B ---------------------------------------------------------------------------------------------------------

/** A synthetic B cell over 120 match-days (4 months), 3 entries a day, per-entry net = mu + noise. */
function bCell(id: string, group: string, mu: number, o: { seed: number; stressMu?: number; placeboMu?: number; breaches?: number }): CellResult {
  const r = rng(o.seed);
  const acc = new ClusterAcc(), st = new ClusterAcc(), pl = new ClusterAcc();
  const pd: PairDiff = { clusters: 0, sum: 0, sumSq: 0 };
  for (const day of days('2025-03-01', 120)) {
    let cs = 0, ps = 0;
    for (let i = 0; i < 3; i++) {
      const x = mu + gauss(r);
      acc.add(x, day); cs += x;
      st.add((o.stressMu ?? mu - 0.1) + gauss(r), day);
      const y = (o.placeboMu ?? 0) + gauss(r);
      pl.add(y, day); ps += y;
    }
    pd.clusters++; pd.sum += cs - ps; pd.sumSq += (cs - ps) ** 2;
  }
  for (const a of [acc, st, pl]) a.flush();
  return { id, family: 'B', group, total: acc.total, folds: acc.folds, stress: st.total, placebo: pl.total, pairDiff: pd, breaches: o.breaches ?? 0, gross: 0, fees: 0 };
}

test('discoverB: a planted cell passes, noise, a breaching cell and a stress loser do not; one per group', () => {
  const planted = bCell('B|RSI14|30s|exitLow|follow|all|tp30sl30', 'RSI14|30s|exitLow|follow', 0.6, { seed: 1 });
  const weaker = bCell('B|RSI14|30s|exitLow|follow|p15-35:pre:chop|tp30sl30', 'RSI14|30s|exitLow|follow', 0.45, { seed: 2 });
  const noise = bCell('B|CCI14|1m|zero|follow|all|t2m', 'CCI14|1m|zero|follow', 0, { seed: 3 });
  const breach = bCell('B|ROC10|5m|zero|fade|all|t10m', 'ROC10|5m|zero|fade', 0.6, { seed: 4, breaches: 2 });
  const stressLoser = bCell('B|MFI14|1m|exitHigh|fade|all|trail3', 'MFI14|1m|exitHigh|fade', 0.6, { seed: 5, stressMu: -0.3 });
  const small: CellResult = { ...bCell('B|WILLR14|10s|exitLow|follow|all|t2m', 'WILLR14|10s|exitLow|follow', 2, { seed: 6 }) };
  small.total = { ...small.total, clusters: 20 }; // too few match-days
  const reversed = bCell('B|RSI14|30s|exitLow|fade|all|tp30sl30', 'RSI14|30s|exitLow|fade', -0.6, { seed: 7 });
  const out = discoverB([noise, planted, breach, weaker, stressLoser, small, reversed], 5000);
  assert.deepEqual(out.flagged.map((f) => f.cell.id), [planted.id], 'one representative: the planted cell with the better t');
  assert.equal(out.tested, 6, 'the 20-day cell gets no p-value');
  const f = out.flagged[0];
  assert.ok(f.t > 5 && f.p < 1e-6 && f.foldShare === 1 && f.stressMean > 0 && f.placeboZ > 2);
  assert.ok(f.why.every((w) => w.includes(' ok:')));
  assert.match(out.markdown, /RSI14\\\|30s/);
  assert.match(out.markdown, /~~breaches~~/, 'the breaching cell is listed with its failed rule');
  assert.match(out.markdown, /~~F2~~/);
  assert.match(out.markdown, /-0\.\d{4} \(t -\d/, 'the reversed cell is shown next to the planted one');
  assert.ok(Number.isFinite(out.pbo.pbo));

  // A cell without its placebo arm cannot be flagged yet.
  const noPlacebo: CellResult = { ...planted, pairDiff: undefined, placebo: undefined };
  assert.equal(discoverB([noPlacebo], 100).flagged.length, 0);
  // A placebo that earns as much leaves z near 0 or below.
  const leaky = bCell('B|RSI14|30s|exitLow|follow|all|tp50sl25', 'g', 0.6, { seed: 9, placeboMu: 0.9 });
  assert.equal(discoverB([leaky], 100).flagged.length, 0);
});

// --- family A ---------------------------------------------------------------------------------------------------------

/** A config's days: 4 matches a day, 3 entries, pnl per entry = mu + noise (summed into the day). */
function aDays(mu: number, seed: number, breachDay = -1, list = days('2025-03-01', 120)): ConfigDay[] {
  const r = rng(seed);
  return list.map((day, k) => {
    let pnl = 0;
    for (let i = 0; i < 3; i++) pnl += mu + gauss(r);
    return { day, matches: 4, traded: 3, entries: 3, pnl, gross: pnl + 0.3, fees: 0.3, breaches: k === breachDay ? 1 : 0, unresolved: 0, legs: { entry: 3, exit: 3 } };
  });
}

function aRuns(id: string, overrides: ConfigRun['overrides'], mu: number, seed: number, o: { breachDay?: number; placeboMu?: number; stressMu?: number } = {}): ConfigRun[] {
  const all = aDays(mu, seed, o.breachDay);
  const ctx = { TENNIS_TRAIL_RATCHET: false, ...overrides };
  return [
    // the primary run in two slices (merged by id)
    { id, overrides: ctx, fill: 'F1', stratum: 'H', days: all.slice(0, 50) },
    { id, overrides: ctx, fill: 'F1', stratum: 'H', days: all.slice(50) },
    { id, overrides: ctx, fill: 'F2', stratum: 'H', days: aDays(o.stressMu ?? mu - 0.05, seed + 100) },
    { id: `${id}|coin`, overrides: ctx, fill: 'F1', placebo: 'coin', stratum: 'H', days: aDays(o.placeboMu ?? 0, seed + 200) },
  ];
}

test('discoverA: merges slices, flags a planted config, rejects noise and breaches, ranks knobs, draws heat tables', () => {
  const runs: ConfigRun[] = [
    ...aRuns('prod', {}, 0, 1),
    ...aRuns('flow0.4', { TENNIS_CONF_FLOW: 0.4 }, 0.5, 2),
    ...aRuns('flow0.05', { TENNIS_CONF_FLOW: 0.05 }, 0, 3),
    ...aRuns('tp0.2', { TENNIS_TP_PCT: 0.2 }, 0.5, 4, { breachDay: 17 }),
    ...aRuns('win30', { TENNIS_CONF_WINDOW_SEC: 30 }, 0.1, 5),
    ...aRuns('mom0.02', { TENNIS_CONF_MOMENTUM_CENTS: 0.02 }, 0.1, 15),
    ...aRuns('flow0.4+win30', { TENNIS_CONF_FLOW: 0.4, TENNIS_CONF_WINDOW_SEC: 30 }, 0.4, 6),
    ...aRuns('flow0.05+win30', { TENNIS_CONF_FLOW: 0.05, TENNIS_CONF_WINDOW_SEC: 30 }, 0, 7),
    // a recorded-day run: another stratum, never pooled
    { id: 'prod', overrides: {}, fill: 'F1', stratum: 'R', days: aDays(5, 8, -1, days('2026-10-21', 10)) },
  ];
  const out = discoverA(runs);
  assert.equal(out.baselineId, 'prod', 'TENNIS_TRAIL_RATCHET=false on every run is context, not a knob');
  assert.equal(out.perConfig.length, 8);
  const by = new Map(out.perConfig.map((c) => [c.id, c]));
  const flow = by.get('flow0.4')!;
  assert.equal(flow.entries, 360, 'two slices merged by id');
  assert.equal(flow.matches, 480);
  assert.equal(flow.days, 120);
  close(flow.perMatch, flow.pnl / 480, 1e-12);
  close(flow.perHour24, flow.pnl / (120 * 24), 1e-9);
  assert.ok(flow.flagged, flow.why.join('; '));
  assert.ok(flow.t > 5 && flow.p < 1e-6 && flow.foldShare === 1 && flow.stressPnl! > 0 && flow.placeboZ! > 2);
  assert.ok(!by.get('flow0.05')!.flagged);
  const tp = by.get('tp0.2')!;
  assert.ok(!tp.flagged && tp.breaches === 1 && tp.why.some((w) => w.startsWith('breaches FAIL')));
  assert.ok(by.get('flow0.4+win30')!.flagged);

  // A1: knob ranges include the baseline as 'prod'; TENNIS_CONF_FLOW and TENNIS_TP_PCT move $/match the most.
  const flowS = out.sensitivity.find((s) => s.knob === 'TENNIS_CONF_FLOW')!;
  assert.deepEqual(flowS.levels.map((l) => l.level), ['prod', '0.05', '0.4']);
  const pm = (id: string) => by.get(id)!.perMatch;
  close(flowS.range, Math.max(pm('prod'), pm('flow0.05'), pm('flow0.4')) - Math.min(pm('prod'), pm('flow0.05'), pm('flow0.4')), 1e-12);
  assert.deepEqual(new Set(out.top6.slice(0, 2)), new Set(['TENNIS_CONF_FLOW', 'TENNIS_TP_PCT']));
  assert.equal(out.top6.length, 4, 'four one-at-a-time knobs in this grid');
  assert.ok(!out.sensitivity.some((s) => s.knob === 'TENNIS_TRAIL_RATCHET'));

  // heat table for the flow x window pair, completed from the one-at-a-time configs and the baseline
  assert.match(out.markdown, /#### confWindowSec \(rows\) x confFlow \(columns\)/);
  assert.match(out.markdown, /\| confWindowSec \\ confFlow \| prod \| 0\.05 \| 0\.4 \|/);
  assert.match(out.markdown, /\| 30 \| [+-]\d\.\d{3} \(/);
  assert.match(out.markdown, /A2 knobs/);
  assert.ok(Number.isFinite(out.pbo.pbo));

  // stratum R alone
  const r = discoverA(runs, { stratum: 'R', minDays: 5, minN: 10 });
  assert.equal(r.perConfig.length, 1);
  assert.equal(r.perConfig[0].entries, 30);
  assert.ok(!r.perConfig[0].flagged && r.perConfig[0].needs.join() === 'F2,placebo', 'no F2 or placebo run on R');
});

test('discoverA ties in the A2 pick go to the earlier pre-registered knob', () => {
  // Every config earns exactly the same: every range is 0, so the pick is the pre-registered order.
  const flat = (id: string, ov: ConfigRun['overrides']): ConfigRun => ({
    id, overrides: ov, fill: 'F1', stratum: 'H',
    days: days('2025-03-01', 40).map((day) => ({ day, matches: 2, traded: 1, entries: 3, pnl: 1, gross: 1.2, fees: 0.2, breaches: 0, unresolved: 0, legs: {} })),
  });
  const keys = ['HARNESS_LOSER_STOP', 'TENNIS_MAX_SPREAD', 'TENNIS_FAV_MIN', 'TENNIS_CONF_FLOW', 'TENNIS_TP_CENTS', 'TENNIS_CONF_WINDOW_SEC', 'TENNIS_HUNT_MAX_SEC', 'TENNIS_CONF_DEPTH'];
  const out = discoverA([flat('base', {}), ...keys.map((k) => flat(k, { [k]: 0.5 }))]);
  assert.deepEqual(out.top6, ['TENNIS_CONF_WINDOW_SEC', 'TENNIS_CONF_FLOW', 'TENNIS_TP_CENTS', 'TENNIS_FAV_MIN', 'TENNIS_HUNT_MAX_SEC', 'TENNIS_MAX_SPREAD']);
  // zero variance per entry: t is infinite, p 0; the configs still lack F2 and placebo runs
  assert.ok(out.perConfig.every((c) => !c.flagged && c.needs.join() === 'F2,placebo'));
});
