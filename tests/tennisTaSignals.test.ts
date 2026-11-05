import assert from 'node:assert/strict';
import { test } from 'node:test';
import { orderFee } from '../bot/fees';
import { FEES, SIGNAL_SPEC, SignalStudy, type EntryTrace } from '../research/tennisTaSignals';
import type { CellResult, MatchGrid } from '../research/tennisTaTypes';

// Synthetic MatchGrids (stratum H, one-level 1c books, imbalance 0) for family B of the tennis TA trial.

function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface GridOpts { seed: number; day: string; live: number; progEnd: number; resultA: 0 | 1; event?: string }

/** A grid whose books quote 1c wide around the path p (A) and 1 - p (B), with a random tape. */
function grid(p: Float64Array, o: GridOpts): MatchGrid {
  const n = p.length, r = rng(o.seed), f = () => new Float64Array(n);
  const bidA = f(), askA = f(), bidB = f(), askB = f(), yA = f(), nA = f(), yB = f(), nB = f(), progress = f();
  for (let i = 0; i < n; i++) {
    const ba = Math.min(0.98, Math.max(0.01, Math.floor(p[i] * 100 + 1e-9) / 100));
    bidA[i] = ba; askA[i] = Math.round(ba * 100 + 1) / 100;
    const bb = Math.min(0.98, Math.max(0.01, Math.floor((1 - p[i]) * 100 + 1e-9) / 100));
    bidB[i] = bb; askB[i] = Math.round(bb * 100 + 1) / 100;
    if (r() < 0.1) { const q = 1 + Math.floor(r() * 20); if (r() < 0.5) yA[i] = q; else nA[i] = q; }
    if (r() < 0.1) { const q = 1 + Math.floor(r() * 20); if (r() < 0.5) yB[i] = q; else nB[i] = q; }
    progress[i] = i < o.live ? 0 : (o.progEnd * (i - o.live)) / (n - o.live);
  }
  return {
    event: o.event ?? `EV-${o.seed}`, series: 'KXATPMATCH', stratum: 'H', tickers: ['KXATPMATCH-X-A', 'KXATPMATCH-X-B'], start: 0, day: o.day, t0: 0, n,
    bidA, askA, bidB, askB, yesVolA: yA, noVolA: nA, yesVolB: yB, noVolB: nB, imbA: f(), imbB: f(), progress,
    liveIdx: o.live, resultA: o.resultA, closeIdx: n - 1,
  };
}

/** Logit random walk (no edge anywhere). */
function rwPath(seed: number, n: number, sigma = 0.012): Float64Array {
  const r = rng(seed), p = new Float64Array(n);
  let x = (r() - 0.5) * 1.5;
  for (let i = 0; i < n; i++) {
    let u = 0;
    for (let k = 0; k < 6; k++) u += r();
    x += (u - 3) * Math.SQRT2 * sigma;
    p[i] = 1 / (1 + Math.exp(-x));
  }
  return p;
}

/** pA near 0.55 with small mean-reverting noise; every 45 min a 12c drop over 4 min, 1 min flat, a 10 min recovery. */
function meanRevertPath(seed: number, n: number): Float64Array {
  const r = rng(seed), p = new Float64Array(n);
  let noise = 0;
  for (let i = 0; i < n; i++) {
    if (i % 5 === 0) noise = noise * 0.9 + (r() - 0.5) * 0.006;
    let shock = 0;
    const c = (i - 1800) % 2700;
    if (i >= 1800) {
      if (c < 240) shock = -0.12 * (c / 240);
      else if (c < 300) shock = -0.12;
      else if (c < 900) shock = -0.12 * (1 - (c - 300) / 600);
    }
    p[i] = 0.55 + noise + shock;
  }
  return p;
}

const mean = (c: { n: number; sum: number }) => c.sum / c.n;
const byId = (cells: CellResult[]) => new Map(cells.map((c) => [c.id, c]));

test('oversold bounce: RSI exit-from-extreme follow earns on a mean-reverting path, its fade loses', () => {
  const st = new SignalStudy();
  for (let k = 0; k < 4; k++) {
    st.addMatch(grid(meanRevertPath(k + 1, 5 * 3600), { seed: 100 + k, day: `2026-02-0${k + 1}`, live: 600, progEnd: 0.6, resultA: 1 }));
  }
  const cells = byId(st.cells());
  const follow = cells.get('B|RSI14L|1m|exitExt|follow|all|ts10m');
  const fade = cells.get('B|RSI14L|1m|exitExt|fade|all|ts10m');
  assert.ok(follow && fade, 'both cells fired');
  assert.ok(follow.total.n >= 10, `follow entries ${follow.total.n}`);
  assert.equal(follow.total.n, fade.total.n, 'follow and fade share one entry set');
  assert.ok(mean(follow.total) > 0.2, `follow mean ${mean(follow.total)}`);
  assert.ok(mean(fade.total) < -0.5, `fade mean ${mean(fade.total)}`);
  // The placebo (same triggers shifted >= 10 min) does not carry the edge.
  assert.ok(follow.placebo && follow.placebo.n > 0 && mean(follow.placebo) < mean(follow.total));
  assert.ok(follow.pairDiff && follow.pairDiff.clusters > 0 && follow.pairDiff.sum > 0);
  // Stress (one tick worse on every exit) costs exactly count x 1c per sold entry here.
  assert.ok(follow.stress && follow.stress.sum < follow.total.sum);
});

test('random walk: mean net per entry of the all cells is negative (fees) and close to the placebo', () => {
  const st = new SignalStudy();
  for (let k = 0; k < 8; k++) {
    const p = rwPath(500 + k, 3 * 3600);
    st.addMatch(grid(p, { seed: 900 + k, day: `2026-03-0${1 + (k >> 1)}`, live: 1200, progEnd: 1, resultA: p[p.length - 1] > 0.5 ? 1 : 0 }));
  }
  let n = 0, s = 0, pn = 0, ps = 0;
  for (const c of st.cells()) {
    if (!c.id.includes('|all|')) continue;
    n += c.total.n; s += c.total.sum;
    pn += c.placebo?.n ?? 0; ps += c.placebo?.sum ?? 0;
  }
  assert.ok(n > 1000 && pn > 1000, `entries ${n}, placebo ${pn}`);
  const m = s / n, pm = ps / pn;
  assert.ok(m < 0, `mean ${m}`);
  assert.ok(pm < 0, `placebo mean ${pm}`);
  assert.ok(Math.abs(m - pm) < 0.15 * Math.abs(pm), `mean ${m} vs placebo ${pm}`);
});

test('no lookahead: changing samples after the cut leaves every entry filled at or before the cut unchanged', () => {
  const n = 4 * 3600, cut = 7000;
  const p = rwPath(77, n);
  const g1 = grid(p, { seed: 7, day: '2026-01-10', live: 900, progEnd: 1, resultA: 1 });
  const g2 = grid(p, { seed: 7, day: '2026-01-10', live: 900, progEnd: 1, resultA: 0 });
  // Rewrite everything after the cut: a different price path, tape and progress clock.
  const q = rwPath(78, n, 0.02), r = rng(79);
  for (let i = cut + 1; i < n; i++) {
    const x = Math.min(0.97, Math.max(0.03, q[i]));
    g2.bidA[i] = Math.floor(x * 100) / 100; g2.askA[i] = Math.round(g2.bidA[i] * 100 + 1 + (r() < 0.3 ? 2 : 0)) / 100;
    g2.bidB[i] = Math.floor((1 - x) * 100) / 100; g2.askB[i] = Math.round(g2.bidB[i] * 100 + 1) / 100;
    g2.yesVolA[i] = r() < 0.3 ? 50 : 0; g2.noVolA[i] = 0; g2.yesVolB[i] = 0; g2.noVolB[i] = r() < 0.3 ? 40 : 0;
    g2.progress[i] = Math.min(1, g2.progress[i] * 1.5);
  }
  const key = (t: EntryTrace) => [t.series, t.dir, t.exit, t.context, t.decision, t.fill, t.side, t.entryPx, t.count].join('|');
  const collect = (g: MatchGrid) => {
    const out: string[] = [];
    new SignalStudy({ trace: (t) => { if (!t.placebo && t.fill <= cut) out.push(key(t)); } }).addMatch(g);
    return out.sort();
  };
  const a = collect(g1), b = collect(g2);
  assert.ok(a.length > 100, `entries before the cut: ${a.length}`);
  assert.deepEqual(b, a);
});

test('fee rounding: a one-contract round trip pays at least 2 cents (each order rounds up to the cent)', () => {
  assert.equal(orderFee(1, 0.5, true, FEES), 0.02); // 0.07 x 0.25 = 0.0175 -> 0.02
  const trips: EntryTrace[] = [];
  const st = new SignalStudy({ orderUsd: 0.01, trace: (t) => { if (!t.placebo) trips.push(t); } });
  const p = rwPath(31, 2 * 3600);
  st.addMatch(grid(p, { seed: 32, day: '2026-01-05', live: 600, progEnd: 1, resultA: 1 }));
  const sold = trips.filter((t) => t.kind !== 'ride' && t.kind !== 'breach');
  assert.ok(sold.length > 100);
  for (const t of sold) {
    assert.equal(t.count, 1);
    assert.ok(t.fees >= 0.02 - 1e-12, `fees ${t.fees} at ${t.entryPx} -> ${t.exitPx}`);
    assert.ok(Math.abs(t.fees - (orderFee(1, t.entryPx, true, FEES) + orderFee(1, t.exitPx, true, FEES))) < 1e-12);
    assert.ok(Math.abs(t.net - (t.exitPx - t.entryPx - t.fees)) < 1e-12);
  }
  // Cell totals carry the same rounded fees: every entry pays at least 1c to buy, every sale at least 1c more.
  for (const c of st.cells()) {
    if (!c.id.includes('|all|') || !c.total.n) continue;
    const mine = trips.filter((t) => c.id === `B|${t.series}|${t.dir}|all|${t.exit}`);
    assert.equal(mine.length, c.total.n);
    const sales = mine.filter((t) => t.kind !== 'ride' && t.kind !== 'breach').length;
    assert.ok(c.fees >= 0.01 * (c.total.n + sales) - 1e-9);
    assert.ok(Math.abs(c.fees - mine.reduce((a, t) => a + t.fees, 0)) < 1e-9);
  }
});

/** pA flat at 0.50, a 2c rise at t = 1000 (MOM w60 fires toward A), then the match is decided at t = 1030. */
function decidedPath(n: number, final: number): Float64Array {
  const p = new Float64Array(n);
  for (let i = 0; i < n; i++) p[i] = i < 1000 ? 0.505 : i < 1030 ? 0.525 : final;
  return p;
}

test('settlement rule: a winner open when the match is decided rides to settlement, a loser is sold at the bid', () => {
  for (const [final, resultA] of [[0.985, 1], [0.015, 0]] as const) {
    const trips: EntryTrace[] = [];
    const st = new SignalStudy({ trace: (t) => { if (!t.placebo && t.series === 'MOM|1s|on:w60:0.01' && t.exit === 'ts10m') trips.push(t); } });
    st.addMatch(grid(decidedPath(3600, final), { seed: 5, day: '2026-01-02', live: 300, progEnd: 0.5, resultA }));
    const follow = trips.find((t) => t.dir === 'follow');
    const fade = trips.find((t) => t.dir === 'fade');
    assert.ok(follow && fade, 'one locked entry, both directions');
    assert.equal(follow.side, 'A');
    assert.equal(fade.side, 'B');
    assert.ok(follow.fill > 1000 && follow.fill < 1030);
    const winner = resultA === 1 ? follow : fade;
    const loser = resultA === 1 ? fade : follow;
    assert.equal(winner.kind, 'ride');
    assert.equal(winner.exitIdx, 1030);
    assert.equal(winner.exitPx, 1);
    assert.ok(Math.abs(winner.net - (winner.count * (1 - winner.entryPx) - orderFee(winner.count, winner.entryPx, true, FEES))) < 1e-9);
    assert.equal(loser.kind, 'cut');
    assert.equal(loser.exitIdx, 1030);
    assert.equal(loser.exitPx, 0.01);
    assert.ok(loser.net < 0);
    const cells = byId(st.cells());
    const cut = cells.get(`B|MOM|1s|on:w60:0.01|${loser.dir}|all|ts10m`)!;
    assert.equal(cut.breaches, 0);
    assert.ok(cut.fees > orderFee(loser.count, loser.entryPx, true, FEES), 'the loser paid an exit fee');
  }
});

test('design size covers every reported cell', () => {
  const st = new SignalStudy();
  for (let k = 0; k < 3; k++) {
    const p = rwPath(40 + k, 2 * 3600);
    st.addMatch(grid(p, { seed: 60 + k, day: `2026-04-0${k + 1}`, live: 600, progEnd: 1, resultA: 1 }));
  }
  const cells = st.cells();
  assert.ok(cells.length > 0);
  assert.ok(st.designSize() >= cells.length);
  // H, one tour series: 38 series x 2 directions x (1 + 25) contexts x 5 exits.
  assert.equal(st.designSize(), 38 * 2 * 26 * 5);
  assert.equal(new Set(cells.map((c) => c.id)).size, cells.length);
  for (const c of cells) {
    const parts = c.id.split('|');
    assert.equal(parts.length, 7);
    assert.equal(c.group, parts.slice(0, 5).join('|'));
    assert.ok(SIGNAL_SPEC.exits.includes(parts[6]));
    assert.ok(parts[5] === 'all' || SIGNAL_SPEC.contexts.includes(parts[5]), parts[5]);
    // H runs no 10 s / 30 s bars and no windows under 60 s (Amendment 1, A1).
    assert.ok(parts[2] !== '10s' && parts[2] !== '30s' && !/on:w(15|30):/.test(parts[3]), c.id);
  }
});
