import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { test } from 'node:test';
import { loadConfig, paperEnv } from '../bot/config';
import { orderFee } from '../bot/fees';
import { openEntryFee, openSidePrice, PositionBook } from '../bot/oms/positions';
import { positionNetAtBid } from '../bot/strategy/fairValueStrategy';
import { MatchTracker, PROGRESS_LATCH_MS } from '../bot/tennis/tennisStrategy';
import { FEES, H_LOT_CAP, latchedProgress, PLACEBO_MIN_SEC, SIGNAL_SPEC, SignalStudy, type EntryTrace } from '../research/tennisTaSignals';
import type { FamilyBCell, MatchGrid } from '../research/tennisTaTypes';

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

interface GridOpts { seed: number; day: string; live: number; progEnd: number; resultA: 0 | 1; event?: string; unit?: string; stratum?: 'H' | 'R';
  /** false: no tape but one 1-lot print at sample 0. */
  tape?: boolean }

/** A grid whose books quote 1c wide around the path p (A) and 1 - p (B), with a random tape; progress rises linearly from
 *  the live sample to progEnd at the last sample (0 throughout when live < 0). */
function grid(p: Float64Array, o: GridOpts): MatchGrid {
  const n = p.length, r = rng(o.seed), f = () => new Float64Array(n);
  const bidA = f(), askA = f(), bidB = f(), askB = f(), yA = f(), nA = f(), yB = f(), nB = f(), progress = f();
  for (let i = 0; i < n; i++) {
    const ba = Math.min(0.98, Math.max(0.01, Math.floor(p[i] * 100 + 1e-9) / 100));
    bidA[i] = ba; askA[i] = Math.round(ba * 100 + 1) / 100;
    const bb = Math.min(0.98, Math.max(0.01, Math.floor((1 - p[i]) * 100 + 1e-9) / 100));
    bidB[i] = bb; askB[i] = Math.round(bb * 100 + 1) / 100;
    if (o.tape !== false) {
      if (r() < 0.1) { const q = 1 + Math.floor(r() * 20); if (r() < 0.5) yA[i] = q; else nA[i] = q; }
      if (r() < 0.1) { const q = 1 + Math.floor(r() * 20); if (r() < 0.5) yB[i] = q; else nB[i] = q; }
    }
    progress[i] = o.live < 0 || i < o.live ? 0 : (o.progEnd * (i - o.live)) / (n - o.live);
  }
  // tape: false keeps one 1-lot print at sample 0, so the H match is not left out as "no tape" (A5).
  if (o.tape === false) yA[0] = 1;
  return {
    event: o.event ?? `EV-${o.seed}`, series: 'KXATPMATCH', stratum: o.stratum ?? 'H', tickers: ['KXATPMATCH-X-A', 'KXATPMATCH-X-B'], start: 0, day: o.day, t0: 0, n,
    bidA, askA, bidB, askB, yesVolA: yA, noVolA: nA, yesVolB: yB, noVolB: nB, imbA: f(), imbB: f(), progress,
    liveIdx: o.live, resultA: o.resultA, closeIdx: n - 1, unit: o.unit ?? 'W-2026-01-05',
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

/** A path from a step function: level(i). */
function pathOf(n: number, level: (i: number) => number): Float64Array {
  const p = new Float64Array(n);
  for (let i = 0; i < n; i++) p[i] = level(i);
  return p;
}

const byId = (cells: FamilyBCell[]) => new Map(cells.map((c) => [c.id, c]));
const placeboOf = (c: FamilyBCell) => Object.values(c.units).reduce((a, u) => ({ n: a.n + u[2], sum: a.sum + u[3] }), { n: 0, sum: 0 });
const MOM60 = 'MOM|1s|on:w60:0.01';

test('oversold bounce: RSI exit-from-extreme follow earns on a mean-reverting path, its fade loses', () => {
  const st = new SignalStudy();
  for (let k = 0; k < 4; k++) {
    st.addMatch(grid(meanRevertPath(k + 1, 5 * 3600), { seed: 100 + k, day: `2026-02-0${k + 1}`, live: 600, progEnd: 0.6, resultA: 1 }));
  }
  const cells = byId(st.exportCells().cells);
  const follow = cells.get('B|RSI14L|1m|exitExt|follow|all|ts10m');
  const fade = cells.get('B|RSI14L|1m|exitExt|fade|all|ts10m');
  assert.ok(follow && fade, 'both cells fired');
  assert.ok(follow.n >= 10, `follow entries ${follow.n}`);
  assert.equal(follow.n, fade.n, 'follow and fade share one entry set');
  assert.ok(follow.sum / follow.n > 0.2, `follow mean ${follow.sum / follow.n}`);
  assert.ok(fade.sum / fade.n < -0.5, `fade mean ${fade.sum / fade.n}`);
  // The placebo (same triggers shifted >= 30 min) does not carry the edge.
  const pl = placeboOf(follow);
  assert.ok(pl.n > 0 && pl.sum / pl.n < follow.sum / follow.n);
  // Stress (one tick worse on every sale, fees x1.25) costs more than nothing.
  assert.ok(follow.stressSum < follow.sum);
});

test('random walk: mean net per entry of the all cells is negative (fees) and close to the placebo', () => {
  const st = new SignalStudy();
  for (let k = 0; k < 8; k++) {
    const p = rwPath(500 + k, 3 * 3600);
    st.addMatch(grid(p, { seed: 900 + k, day: `2026-03-0${1 + (k >> 1)}`, live: 1200, progEnd: 1, resultA: p[p.length - 1] > 0.5 ? 1 : 0 }));
  }
  let n = 0, s = 0, pn = 0, ps = 0;
  for (const c of st.exportCells().cells) {
    if (!c.id.includes('|all|')) continue;
    n += c.n; s += c.sum;
    const pl = placeboOf(c);
    pn += pl.n; ps += pl.sum;
  }
  assert.ok(n > 1000 && pn > 1000, `entries ${n}, placebo ${pn}`);
  const m = s / n, pm = ps / pn;
  assert.ok(m < 0, `mean ${m}`);
  assert.ok(pm < 0, `placebo mean ${pm}`);
  assert.ok(Math.abs(m - pm) < 0.15 * Math.abs(pm), `mean ${m} vs placebo ${pm}`);
});

test('placebo pairing compares MEANS per unit: no false edge where the real arm only enters less often', () => {
  // No edge anywhere: pre-match (first 60 min) nearly flat (a 4-point logit tick every 10 min), in-play a logit random
  // walk. Real triggers are rare before the start; in-play triggers shifted there are not, so the placebo arm makes more
  // pre-match entries. Every entry loses spread and fees, so comparing SUMS (the old day-sum pairDiff) crowns the arm with
  // fewer entries; comparing per-unit means does not.
  const st = new SignalStudy();
  for (let k = 0; k < 30; k++) {
    const n = 3 * 3600, live = 3600, r = rng(1000 + k), p = new Float64Array(n);
    let x = r() - 0.5;
    for (let i = 0; i < n; i++) {
      if (i < live) { if (i % 600 === 0) x += (r() < 0.5 ? -1 : 1) * 0.04; }
      else { let u = 0; for (let q = 0; q < 6; q++) u += r(); x += (u - 3) * Math.SQRT2 * 0.012; }
      p[i] = 1 / (1 + Math.exp(-x));
    }
    const day = '2026-02-' + String(1 + Math.floor(k / 2)).padStart(2, '0');
    st.addMatch(grid(p, { seed: 2000 + k, day, live, progEnd: 1, resultA: p[n - 1] > 0.5 ? 1 : 0, unit: `W${Math.floor(k / 6)}` }));
  }
  let cells = 0, sumWins = 0, meanWins = 0, realN = 0, placeboN = 0;
  for (const c of st.exportCells().cells) {
    if (!c.id.includes('|KXATPMATCH:pre:')) continue;
    let ds = 0, dm = 0, paired = 0;
    for (const [n, s, pn, ps] of Object.values(c.units)) {
      if (!n || !pn) continue;
      paired++; ds += s - ps; dm += s / n - ps / pn; realN += n; placeboN += pn;
    }
    if (!paired) continue;
    cells++;
    if (ds > 0) sumWins++;
    if (dm > 0) meanWins++;
  }
  assert.ok(cells >= 100, `pre-match cells paired: ${cells}`);
  assert.ok(placeboN > 1.15 * realN, `placebo entries ${placeboN} vs real ${realN}: the arms differ in count`);
  // The old statistic: the real arm "beats" the placebo in most cells although neither has an edge.
  assert.ok(sumWins / cells > 0.75, `sum-paired wins ${sumWins} / ${cells}`);
  // The contract's statistic (per-unit means): a coin flip.
  assert.ok(meanWins / cells > 0.35 && meanWins / cells < 0.65, `mean-paired wins ${meanWins} / ${cells}`);
  // By day (the registry's control row, C7): the raw placebo day sum crowns the sparser arm too; the placebo scaled to the
  // real arm's entries that day (n x placebo sum / placebo n; a day without placebo entries takes the cell's pooled
  // placebo mean) does not. Every day row carries the counts for it.
  let allCells = 0, fewer = 0, daySumWins = 0, dayScaledWins = 0;
  for (const c of st.exportCells().cells) {
    if (!c.id.includes('|all|')) continue;
    const rows = Object.values(c.days);
    for (const r of rows) assert.equal(r.length, 4, `${c.id}: day rows are [n, sum, placebo n, placebo sum]`);
    const n = rows.reduce((a, r) => a + r[0], 0), pn = rows.reduce((a, r) => a + r[2], 0), ps = rows.reduce((a, r) => a + r[3], 0);
    if (!n || !pn) continue;
    let gSum = 0, gScaled = 0;
    for (const [dn, ds, dpn, dps] of rows) { gSum += ds - dps; gScaled += ds - dn * (dpn ? dps / dpn : ps / pn); }
    allCells++;
    if (n < pn) fewer++;
    if (gSum > 0) daySumWins++;
    if (gScaled > 0) dayScaledWins++;
  }
  assert.ok(allCells >= 200 && fewer > 0.7 * allCells, `all cells ${allCells}, real arm sparser in ${fewer}`);
  assert.ok(daySumWins / allCells > 0.62, `raw day-sum pairing wins ${daySumWins} / ${allCells}`);
  assert.ok(dayScaledWins / allCells > 0.38 && dayScaledWins / allCells < 0.62, `count-scaled day pairing wins ${dayScaledWins} / ${allCells}`);
});

test('placebo shift: at least 30 min from the real trigger both ways, none for a match under 2 x 30 min', () => {
  const seen: number[] = [];
  for (let k = 0; k < 40; k++) {
    // One MOM w60 trigger toward A, at 1000 or (so the shift wraps backwards) at 3000; N = 4000 samples.
    const d0 = k % 2 ? 3000 : 1000;
    const p = pathOf(4000, (i) => (i < d0 ? 0.405 : 0.425));
    const out: EntryTrace[] = [];
    const st = new SignalStudy({ trace: (t) => { if (t.series === MOM60 && t.dir === 'follow' && t.exit === 'ts2m') out.push(t); } });
    st.addMatch(grid(p, { seed: 3, day: '2026-01-02', live: -1, progEnd: 0, resultA: 1, event: `EV-shift-${k}`, tape: false }));
    const real = out.filter((t) => !t.placebo), plac = out.filter((t) => t.placebo);
    assert.deepEqual(real.map((t) => t.decision), [d0]);
    assert.equal(plac.length, 1, `placebo entries ${plac.length}`);
    const gap = Math.abs(plac[0].decision - d0), circ = Math.min(gap, 4000 - gap);
    assert.ok(circ >= PLACEBO_MIN_SEC, `placebo decision ${plac[0].decision} vs real ${d0}: ${circ} s apart`);
    seen.push(plac[0].decision);
  }
  assert.ok(new Set(seen).size > 20, 'the offsets are drawn, not fixed');
  // 3500 samples < 2 x 1800: no placebo at all (the old 600 s minimum shifted it by as little as 600 s).
  const out: EntryTrace[] = [];
  const st = new SignalStudy({ trace: (t) => { if (t.series === MOM60) out.push(t); } });
  st.addMatch(grid(pathOf(3500, (i) => (i < 1000 ? 0.405 : 0.565)), { seed: 1, day: '2026-01-02', live: -1, progEnd: 0, resultA: 1, tape: false }));
  assert.ok(out.some((t) => !t.placebo));
  assert.equal(out.filter((t) => t.placebo).length, 0);
  assert.equal(st.diagnostics().noPlaceboMatches, 1);
  assert.ok(st.diagnostics().noPlaceboEntries > 0);
  for (const c of st.exportCells().cells) for (const u of Object.values(c.units)) assert.equal(u[2], 0);
});

test('placebo past its source: a wrapped placebo that could ride past its source is left out by its time, never its outcome', () => {
  // OPP w60 0.01 toward A: B falls 2c at 3000 (N = 4000), so its placebo wraps to d' = 3000 + offset - 4000 in [800, 1200].
  const OPP60 = 'OPP|1s|on:w60:0.01';
  const opts = { seed: 3, day: '2026-01-02', live: -1, progEnd: 0, resultA: 1 as const, event: 'EV-span', tape: false };
  const first: EntryTrace[] = [];
  new SignalStudy({ trace: (t) => { if (t.series === OPP60 && t.dir === 'follow' && t.exit === 'ts2m') first.push(t); } })
    .addMatch(grid(pathOf(4000, (i) => (i < 3000 ? 0.405 : 0.425)), opts));
  assert.deepEqual(first.filter((t) => !t.placebo).map((t) => [t.decision, t.source]), [[3000, 3000]]);
  const pl = first.filter((t) => t.placebo);
  assert.equal(pl.length, 1);
  const dp = pl[0].decision;
  assert.equal(pl[0].source, 3000);
  assert.ok(dp <= 3000 - PLACEBO_MIN_SEC, `placebo ${dp}`);
  // Same event and length (so the same offsets). A moves 20c right after d' (up: the placebo's follow position is in profit
  // after fees and would ride to settlement past its source at 3000; down: it would lose), and the reading is in the last
  // share from `share` (until `back`, then again from `again`). Its longest time stop is d' + 1 + 900: it could ride past
  // it when the reading is in the share by then and the latch gets there within 2 min (+10 s) after it.
  const run = (up: boolean, share: number, back = 4000, again = 4000) => {
    const lv = up ? [0.405, 0.605, 0.625] : [0.405, 0.205, 0.225];
    const g = grid(pathOf(4000, (i) => (i < dp + 3 ? lv[0] : i < 3000 ? lv[1] : lv[2])), opts);
    for (let i = 0; i < g.n; i++) g.progress[i] = (i >= share && i < back) || i >= again ? 0.75 : 0.5;
    const all: EntryTrace[] = [];
    const st = new SignalStudy({ trace: (t) => all.push(t) });
    st.addMatch(g);
    return { all, mine: all.filter((t) => t.placebo && t.series === OPP60 && t.decision === dp), d: st.diagnostics() };
  };
  // Without the rule this one rides past its source: the reading is in the share from d' + 5, so the follow position (in
  // profit) rides through its stops, and the latch (d' + 125) cuts nothing in profit. Could ride (share at d' + 5, or
  // exactly at its longest time stop): left out, whichever way the price goes.
  for (const share of [dp + 5, dp + 901]) {
    const up = run(true, share), down = run(false, share);
    assert.equal(up.mine.length, 0, `share ${share - dp} s after d': the wrapped placebo is left out`);
    assert.equal(down.mine.length, 0, 'left out when it would lose too: the rule reads the time, not the outcome');
    assert.ok(up.d.placeboSpanExcluded >= 1 && down.d.placeboSpanExcluded >= 1);
    assert.equal(up.d.placeboSpanSource, 0, 'no placebo position is open past its source');
    for (const t of up.all) if (t.placebo && t.source > t.decision) assert.ok(t.exitIdx <= t.source, `${t.series} ${t.decision}: open past ${t.source}`);
    // diagnostics spanWindow replays each series without the rule from its first left-out trigger (measured only, never
    // recorded or traced): it sees the leak the rule removes, positions open past their source.
    for (const x of [up, down]) {
      const w = x.d.spanWindow;
      assert.ok(w.ruleOffPastSource >= 2, `share ${share - dp} s after d': replayed positions past their source ${w.ruleOffPastSource}`);
      assert.ok(w.ruleOffPositions > w.ruleOnPositions, `replay ${w.ruleOffPositions} vs recorded ${w.ruleOnPositions}`);
      assert.equal(x.all.filter((t) => t.placebo).length, w.allPlaceboPositions, 'the replay is never traced');
    }
  }
  // Kept, and closed in time: the share one second after its longest time stop (every exit is decided by then), or a
  // reading in the share for under a minute after d' whose latch comes only when the reading is back there at 2500.
  for (const [share, back, again] of [[dp + 902, 4000, 4000], [dp + 5, dp + 60, 2500]]) {
    const kept = run(true, share, back, again);
    assert.equal(kept.mine.length, 10, `share ${share - dp} s after d': one placebo entry, both directions, five exits`);
    for (const t of kept.mine) {
      assert.equal(t.source, 3000);
      assert.ok(t.kind !== 'ride' && t.exitIdx < 3000, `${t.dir}|${t.exit}: ${t.kind} at ${t.exitIdx}`);
    }
    assert.equal(kept.d.placeboSpanSource, 0);
  }
  const kept = run(true, dp + 902);
  // Every trace names its source: a real one itself, a placebo one at least 30 min away (circularly).
  for (const t of kept.all) {
    if (!t.placebo) { assert.equal(t.source, t.decision); continue; }
    const gap = Math.abs(t.decision - t.source);
    assert.ok(Math.min(gap, 4000 - gap) >= PLACEBO_MIN_SEC, `${t.series}: ${t.decision} from ${t.source}`);
  }
  // On random walks no placebo position outlasts its source, and the placebo still covers the matches: a placebo that did
  // not wrap (it lies after its source) keeps its rides.
  let laterRides = 0, tracedReal = 0, tracedPlacebo = 0;
  const st = new SignalStudy({ trace: (t) => {
    if (t.placebo) tracedPlacebo++; else tracedReal++;
    if (!t.placebo) return;
    if (t.source > t.decision) assert.ok(t.exitIdx <= t.source, `${t.series}: ${t.decision} open past ${t.source}`);
    else if (t.kind === 'ride') laterRides++;
  } });
  for (let k = 0; k < 4; k++) { const p = rwPath(500 + k, 3 * 3600); st.addMatch(grid(p, { seed: 900 + k, day: '2026-03-01', live: 1200, progEnd: 1, resultA: p[p.length - 1] > 0.5 ? 1 : 0 })); }
  const d = st.diagnostics();
  assert.ok(d.placeboSpanExcluded > 0 && d.placeboEntries > 10 * d.placeboSpanExcluded, `excluded ${d.placeboSpanExcluded}, placebo entries ${d.placeboEntries}`);
  assert.equal(d.placeboSpanSource, 0);
  assert.ok(laterRides > 0, 'placebo rides after their source are kept');
  // spanWindow: the arms' totals match the cells and the trace; the window is a share of each; the replay ran.
  const w = d.spanWindow;
  let n = 0, sum = 0, pn = 0, ps = 0;
  for (const c of st.exportCells().cells) {
    if (!c.id.includes('|all|')) continue;
    n += c.n; sum += c.sum;
    const pl = placeboOf(c);
    pn += pl.n; ps += pl.sum;
  }
  assert.equal(w.allRealPositions, n);
  assert.equal(w.allRealPositions, tracedReal);
  assert.equal(w.allRealPositions, Object.values(d.kinds).reduce((a, b) => a + b, 0));
  assert.equal(w.allPlaceboPositions, pn);
  assert.equal(w.allPlaceboPositions, tracedPlacebo);
  assert.ok(Math.abs(w.allRealNet - sum) < 1e-6 && Math.abs(w.allPlaceboNet - ps) < 1e-6, `nets ${w.allRealNet} / ${sum}, ${w.allPlaceboNet} / ${ps}`);
  assert.ok(w.realPositions > 0 && w.realPositions < w.allRealPositions, `real in the window ${w.realPositions} of ${w.allRealPositions}`);
  assert.ok(w.placeboPositions < w.allPlaceboPositions && w.ruleOnPositions <= w.placeboPositions, `placebo in the window ${w.placeboPositions}, after a left-out trigger ${w.ruleOnPositions}`);
  assert.ok(w.ruleOffPositions > w.ruleOnPositions, `replay ${w.ruleOffPositions} vs recorded ${w.ruleOnPositions}`);
});

test('order: the same matches in another day order give the same cells', () => {
  const ms = [0, 1, 2].map((k) => {
    const p = rwPath(90 + k, 2 * 3600);
    return grid(p, { seed: 95 + k, day: `2026-03-0${k + 2}`, unit: k < 2 ? 'W-2026-03-02' : 'W-2026-03-09', live: 600, progEnd: 1, resultA: p[p.length - 1] > 0.5 ? 1 : 0 });
  });
  const run = (order: number[]) => { const st = new SignalStudy({ bars: ['1m', '5m'] }); for (const k of order) st.addMatch(ms[k]); return st; };
  const a = run([0, 1, 2]), b = run([2, 0, 1]);
  assert.equal(a.diagnostics().outOfOrderGrids, 0);
  assert.equal(b.diagnostics().outOfOrderGrids, 2);
  const ea = a.exportCells(), eb = b.exportCells();
  assert.equal(ea.designSize, eb.designSize);
  assert.ok(ea.cells.length > 100);
  const cb = byId(eb.cells);
  assert.equal(cb.size, ea.cells.length);
  const sortRec = <T>(r: Record<string, T>) => Object.entries(r).sort(([x], [y]) => x.localeCompare(y));
  for (const c of ea.cells) {
    const d = cb.get(c.id)!;
    assert.ok(d, c.id);
    assert.equal(d.n, c.n);
    for (const k of ['sum', 'sumSq', 'sum3', 'sum4', 'gross', 'fees', 'stressSum'] as const) assert.ok(Math.abs(d[k] - c[k]) < 1e-6 * Math.max(1, Math.abs(c[k])), `${c.id} ${k}`);
    const close = (x: number[], y: number[]) => x.length === y.length && x.every((v, i) => Math.abs(v - y[i]) < 1e-6);
    const ua = sortRec(c.units), ub = sortRec(d.units), da = sortRec(c.days), db = sortRec(d.days);
    assert.ok(ua.length === ub.length && ua.every(([u, r], i) => ub[i][0] === u && close(r, ub[i][1])), `${c.id} units`);
    assert.ok(da.length === db.length && da.every(([u, r], i) => db[i][0] === u && close(r, db[i][1])), `${c.id} days`);
  }
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
  for (const c of st.exportCells().cells) {
    if (!c.id.includes('|all|') || !c.n) continue;
    const mine = trips.filter((t) => c.id === `B|${t.series}|${t.dir}|all|${t.exit}`);
    assert.equal(mine.length, c.n);
    const sales = mine.filter((t) => t.kind !== 'ride' && t.kind !== 'breach').length;
    assert.ok(c.fees >= 0.01 * (c.n + sales) - 1e-9);
    assert.ok(Math.abs(c.fees - mine.reduce((a, t) => a + t.fees, 0)) < 1e-6);
  }
});

test('exits: decided on one sample, sold one latency later, never on the sample that decided them', () => {
  // A at 0.30, a 2c rise at 1000 (MOM w60 fires toward A, bought at 1001 for 0.33), then a one-second spike of A's book
  // to 0.50 / 0.51 at 1100: the +30% take-profit (0.429) sees it, but the spike is gone when the sale lands.
  const p = pathOf(3600, (i) => (i < 1000 ? 0.305 : 0.325));
  const g = grid(p, { seed: 11, day: '2026-01-02', live: 300, progEnd: 0.5, resultA: 1, tape: false });
  g.bidA[1100] = 0.5; g.askA[1100] = 0.51;
  const trips: EntryTrace[] = [];
  new SignalStudy({ trace: (t) => { if (!t.placebo) trips.push(t); } }).addMatch(g);
  const tp = trips.find((t) => t.series === MOM60 && t.dir === 'follow' && t.exit === 'tp30sl30');
  assert.ok(tp, 'the MOM entry fired');
  assert.equal(tp.fill, 1001);
  assert.equal(tp.entryPx, 0.33);
  assert.equal(tp.kind, 'tp');
  assert.equal(tp.exitDecision, 1100);
  assert.equal(tp.exitIdx, 1101, 'sold one latency after the decision');
  assert.equal(tp.exitPx, 0.32, 'at the bid then, not at the spike');
  // Every sale on a random walk: decided after the fill, sold at least one latency after the decision.
  const st = new SignalStudy({ trace: (t) => { if (!t.placebo) trips.push(t); } });
  trips.length = 0;
  st.addMatch(grid(rwPath(5, 3 * 3600), { seed: 6, day: '2026-01-02', live: 900, progEnd: 1, resultA: 1 }));
  const sold = trips.filter((t) => t.kind !== 'ride' && t.kind !== 'breach');
  assert.ok(sold.length > 500);
  for (const t of sold) {
    assert.ok(t.exitDecision >= t.fill + 1, `decision ${t.exitDecision} vs fill ${t.fill}`);
    assert.ok(t.exitIdx >= t.exitDecision + 1, `sale ${t.exitIdx} vs decision ${t.exitDecision}`);
  }
});

/** Index of the last 30-min step at or before the decision of a staircase (steps at multiples of 1800 s). */
const sinceStep = (d: number) => d - Math.floor((d - 1) / 1800) * 1800;

test('flat windows: no reading from a window that did not move (SLOPE, STOCH, RSI, MOM, MFI, close-only flickers)', () => {
  // A staircase: 1c steps every 30 min, flat in between, so every 1-minute window more than its length after a step is flat.
  const lv = [0.375, 0.385, 0.395, 0.405, 0.395, 0.385, 0.375, 0.365, 0.355, 0.365, 0.375, 0.385];
  const steps = pathOf(6 * 3600, (i) => lv[Math.floor(i / 1800)]);
  const trips: EntryTrace[] = [];
  const st = new SignalStudy({ trace: (t) => { if (!t.placebo && t.dir === 'follow' && t.exit === 'ts2m') trips.push(t); } });
  st.addMatch(grid(steps, { seed: 3, day: '2026-01-02', live: -1, progEnd: 0, resultA: 1, tape: false }));
  // Minutes after a step that a 1-minute reading can still see it: closes read - 1 (close-based), 14 (range, STOCH).
  const maxMin: Record<string, number> = { RSI14L: 14, SLOPE14L: 13, MOM10L: 10, MACDH12_26_9L: 9, BBP20_2L: 19, STOCH14_3_3L: 14, WILLR14L: 14, CCI14L: 14, ADX14L: 14 };
  let ta = 0;
  for (const t of trips) {
    const [reading, bar] = t.series.split('|');
    if (bar !== '1m' || !(reading in maxMin)) continue;
    ta++;
    assert.ok(sinceStep(t.decision) <= maxMin[reading] * 60, `${t.series} fired ${sinceStep(t.decision) / 60} min after a step`);
  }
  assert.ok(ta > 0, 'the staircase still makes real readings next to its steps');
  // RSI over closes that never change, with a 5 s flicker inside every third bar: no reading until the real step at 2400.
  const flick = pathOf(2 * 3600, (i) => { const s = i % 60, m = Math.floor(i / 60); return i >= 2400 ? 0.385 : m % 3 === 0 && s >= 30 && s < 35 ? 0.385 : 0.375; });
  const rsi: EntryTrace[] = [];
  new SignalStudy({ trace: (t) => { if (!t.placebo && t.series.startsWith('RSI14L|1m')) rsi.push(t); } })
    .addMatch(grid(flick, { seed: 9, day: '2026-01-02', live: -1, progEnd: 0, resultA: 1 }));
  // (TA-Lib reads 0 on the flat closes; the step then makes it 100, a false "leaves oversold" at 2460.)
  assert.deepEqual(rsi.map((t) => t.decision), []);
  // MFI: pA rises every minute (true MFI 100 throughout) with 1 + 2 contracts on the tape: TA-Lib on the 0..1 scale reads 0
  // (money flow under 1.0) and "leaves oversold"; in cents it never fires.
  const rise = pathOf(3600, (i) => 0.3 + 0.005 * Math.floor(i / 60) + 0.0001);
  const g = grid(rise, { seed: 9, day: '2026-01-02', live: -1, progEnd: 0, resultA: 1, tape: false });
  g.yesVolA[20 * 60 + 30] = 1; g.yesVolA[24 * 60 + 30] = 2;
  const mfi: EntryTrace[] = [];
  new SignalStudy({ trace: (t) => { if (!t.placebo && t.series.startsWith('MFI14|')) mfi.push(t); } }).addMatch(g);
  assert.deepEqual(mfi.map((t) => `${t.decision}:${t.side}`), []);
  // A zero-cross needs the sign of the last nonzero reading to flip: closes 0.40, 0.41 (bars 50-54), 0.40 (55-59), 0.41 (60-)
  // make MOM10 + (bars 50-54), exactly 0 (55-64, the window still moving), + again (65-69): no sign change, no trigger.
  const twice = pathOf(3 * 3600, (i) => (i < 3000 ? 0.4 : i < 3300 ? 0.41 : i < 3600 ? 0.4 : 0.41));
  const mom: EntryTrace[] = [];
  new SignalStudy({ trace: (t) => { if (!t.placebo && t.series === 'MOM10L|1m|zeroX' && t.dir === 'follow' && t.exit === 'ts2m') mom.push(t); } })
    .addMatch(grid(twice, { seed: 4, day: '2026-01-02', live: -1, progEnd: 0, resultA: 1, tape: false }));
  assert.equal(mom.length, 0, `MOM10 fired at ${mom.map((t) => t.decision)}`);
});

test('gaps are masked, never carried: no TA reading over a gap until a fresh warm-up, no primitive at or right after it', () => {
  const n = 3 * 3600;
  const p = rwPath(21, n, 0.02);
  const g = grid(p, { seed: 22, day: '2026-01-02', live: 600, progEnd: 1, resultA: 1 });
  for (let i = 5000; i < 5300; i++) { g.bidA[i] = NaN; g.askA[i] = NaN; g.bidB[i] = NaN; g.askB[i] = NaN; }
  const trips: EntryTrace[] = [];
  const st = new SignalStudy({ trace: (t) => { if (!t.placebo && t.dir === 'follow' && t.exit === 'ts2m') trips.push(t); } });
  st.addMatch(g);
  assert.ok(st.diagnostics().gapBars >= 4, `gap bars ${st.diagnostics().gapBars}`);
  // 1-minute bars 84..87 hold no valid mark; the next segment starts at bar 88 and MOM10 (the shortest warm-up) needs 11 bars
  // for a value and one more for a crossing: the first 1-minute TA decision after the gap is at (88 + 11 + 1) x 60 = 6000.
  const ta1m = trips.filter((t) => t.series.split('|')[1] === '1m');
  assert.ok(ta1m.length > 20);
  for (const t of ta1m) assert.ok(t.decision <= 5040 || t.decision >= 6000, `${t.series} at ${t.decision}`);
  // Primitives: the books are unknown in [5000, 5300); nothing fires there or at the first sample back.
  for (const t of trips) if (t.series.startsWith('MOM|') || t.series.startsWith('OPP|')) assert.ok(t.decision < 5000 || t.decision > 5300, `${t.series} at ${t.decision}`);
});

/** End-cut fixtures: A at 0.505, a 2c rise at 1000 (MOM w60 toward A: follow buys A at 0.53, fade buys B at 0.48), A at
 *  `level` (0.60) from 1050; progress 0.5 from the start (300) and 0.75 from 1100 (the last 30% by the reading; the latch,
 *  2 min of readings there, from 1220), back to 0.5 from `backAt` when given. */
function endGrid(o: { resultA: 0 | 1; dropAt?: number; noBidB?: boolean; level?: number; backAt?: number; moveAt?: number }): MatchGrid {
  const lv = o.level ?? 0.6;
  const p = pathOf(3600, (i) => (i < 1000 ? 0.505 : i < 1050 ? 0.525 : o.dropAt !== undefined && i >= o.dropAt ? 0.5 : o.moveAt !== undefined && i >= o.moveAt ? lv + 0.02 : lv));
  const g = grid(p, { seed: 5, day: '2026-01-02', live: 300, progEnd: 0, resultA: o.resultA });
  for (let i = 0; i < g.n; i++) g.progress[i] = i < 300 ? 0 : i < 1100 || (o.backAt !== undefined && i >= o.backAt) ? 0.5 : 0.75;
  if (o.noBidB) for (let i = 1101; i < g.n; i++) { g.bidB[i] = NaN; g.askB[i] = NaN; }
  return g;
}

test('end cut: in the last share a position in profit after fees rides to settlement, one that is not is sold at the bid', () => {
  for (const resultA of [1, 0] as const) {
    const trips: EntryTrace[] = [];
    const st = new SignalStudy({ trace: (t) => { if (!t.placebo) trips.push(t); } });
    st.addMatch(endGrid({ resultA }));
    const mine = trips.filter((t) => t.series === MOM60);
    assert.equal(mine.length, 10, 'one locked entry, both directions, five exits');
    for (const t of mine) {
      assert.equal(t.decision, 1000);
      if (t.dir === 'follow') {
        // 18 x 0.60 - 0.31 - (18 x 0.53 + 0.32) = +0.63 after fees from 1100, the first reading in the last share: it rides
        // from there (production's lastShare reads the reading, not the latch; ts2m's stop at 1121 never sells it), paid
        // by the result.
        assert.equal(t.side, 'A');
        assert.equal(t.kind, 'ride', `${t.exit}: ${t.kind}`);
        assert.equal(t.exitPx, resultA);
        assert.equal(t.exitIdx, 3599);
        assert.ok(Math.abs(t.net - (t.count * (resultA - t.entryPx) - orderFee(t.count, t.entryPx, true, FEES))) < 1e-9);
      } else if (t.exit === 'ts2m') {
        // B bought at 0.48, bid 0.40: not in profit, but the latch is not in the last share before 1220, so production does
        // not cut it yet and its own exit stands: the 2 min stop at 1121.
        assert.equal(t.kind, 'time');
        assert.equal(t.exitDecision, 1121);
        assert.equal(t.exitIdx, 1122);
      } else {
        // The others are still open at 1220, when the reading has held the last share for 2 min: cut on the quotes of 1220,
        // sold at 1221.
        assert.equal(t.side, 'B');
        assert.equal(t.kind, 'cut', `${t.exit}: ${t.kind}`);
        assert.equal(t.exitDecision, 1220);
        assert.equal(t.exitIdx, 1221);
        assert.equal(t.exitPx, 0.4);
      }
    }
    // The end-entry block: nothing enters once the latched progress reaches 0.65 (here 1220).
    assert.ok(trips.every((t) => t.decision < 1220));
    const cells = byId(st.exportCells().cells);
    assert.equal(cells.get(`B|${MOM60}|follow|all|ts10m`)!.breaches, 0);
    assert.equal(cells.get(`B|${MOM60}|fade|all|ts10m`)!.breaches, 0);
  }
  // A rider is judged again every second: A falls back to 0.50 at 2000, the follow position is cut there.
  const trips: EntryTrace[] = [];
  const st = new SignalStudy({ trace: (t) => { if (!t.placebo) trips.push(t); } });
  st.addMatch(endGrid({ resultA: 1, dropAt: 2000 }));
  for (const t of trips.filter((x) => x.series === MOM60 && x.dir === 'follow')) {
    assert.equal(t.kind, 'cut');
    assert.equal(t.exitDecision, 2000);
    assert.equal(t.exitIdx, 2001);
    assert.equal(t.exitPx, 0.5);
  }
  assert.ok(st.diagnostics().endBlocked > 0, 'the drop at 2000 triggers series that the end block refuses');
  assert.ok(trips.every((t) => t.decision < 1220));
});

test('end cut waits for the latch: a reading in the last share for under 2 min neither cuts nor blocks entries', () => {
  // The reading is 0.75 from 1100 to 1219 only (120 readings, under PROGRESS_LATCH_MS), then 0.5 again; A moves 2c at 2500.
  const run = (backAt: number) => {
    const trips: EntryTrace[] = [];
    const st = new SignalStudy({ trace: (t) => { if (!t.placebo && t.series === MOM60) trips.push(t); } });
    st.addMatch(endGrid({ resultA: 1, backAt, moveAt: 2500 }));
    return { trips, d: st.diagnostics() };
  };
  const { trips } = run(1220);
  const first = trips.filter((t) => t.decision === 1000);
  assert.equal(first.length, 10);
  for (const t of first) {
    assert.notEqual(t.kind, 'cut', `${t.dir}|${t.exit}`);
    assert.notEqual(t.kind, 'ride', `${t.dir}|${t.exit}`);
  }
  const at = (dir: string, exit: string) => first.find((t) => t.dir === dir && t.exit === exit)!;
  // The follow position (in profit) rode through 1100-1219, which held its 2 min stop (1121); the comeback at 1220 ends the
  // ride and the stop sells it there. The fade position (not in profit) keeps its own exits: never cut.
  assert.equal(at('follow', 'ts2m').kind, 'time');
  assert.equal(at('follow', 'ts2m').exitDecision, 1220);
  assert.equal(at('fade', 'ts2m').exitDecision, 1121);
  assert.equal(at('fade', 'ts10m').kind, 'time');
  assert.equal(at('fade', 'ts10m').exitDecision, 1601);
  // No end-entry block: the move at 2500 enters.
  assert.ok(trips.some((t) => t.decision === 2500), `decisions ${[...new Set(trips.map((t) => t.decision))]}`);
  // One more reading (1100-1220: the reading at 1220 closes 2 min of the last share) latches it: cut at 1220, the move at
  // 2500 is blocked.
  const held = run(1221);
  const heldFade = held.trips.filter((t) => t.decision === 1000 && t.dir === 'fade' && t.exit !== 'ts2m');
  assert.equal(heldFade.length, 4);
  assert.ok(heldFade.every((t) => t.kind === 'cut' && t.exitDecision === 1220));
  assert.ok(!held.trips.some((t) => t.decision >= 1220));
  assert.ok(held.d.endBlocked > 0);
  assert.equal(held.d.progressHighFromGrid, 0);
});

test('latched progress: latchedProgress is MatchTracker.latchProgress reading for reading; a grid that carries it is used', () => {
  const tennis = loadConfig(paperEnv({})).tennis;
  const cases: Array<{ name: string; p: Float64Array; step: number }> = [];
  for (let k = 0; k < 6; k++) {
    // Rising readings with holds, one-tick spikes, comebacks, and jumps.
    const r = rng(300 + k), n = 1500, p = new Float64Array(n);
    let x = 0;
    for (let i = 0; i < n; i++) {
      const u = r();
      x = u < 0.02 ? Math.min(1, x + 0.2 * r()) : u < 0.04 ? Math.max(0, x - 0.2 * r()) : u < 0.5 ? x : Math.min(1, x + 0.002 * r());
      p[i] = u > 0.995 ? Math.min(1, x + 0.3) : x;
    }
    cases.push({ name: `walk ${k}`, p, step: k % 2 ? 5000 : 1000 });
  }
  const nan = Float64Array.from({ length: 400 }, (_, i) => (i === 250 ? NaN : i / 400));
  cases.push({ name: 'NaN reading', p: nan, step: 1000 });
  for (const c of cases) {
    const ref = new MatchTracker('ref', tennis);
    const got = latchedProgress(c.p, c.p.length, c.step);
    for (let i = 0; i < c.p.length; i++) {
      const want = ref.latchProgress(i * c.step, c.p[i]);
      assert.ok(Object.is(got[i], want) || Math.abs(got[i] - want) < 1e-15, `${c.name} reading ${i}: ${got[i]} vs ${want}`);
    }
  }
  // 1 s readings: 0 until 2 min are covered; a 0.75 held 119 s never counts, one held 120 s does.
  assert.equal(PROGRESS_LATCH_MS, 120_000);
  const spike = Float64Array.from({ length: 600 }, (_, i) => (i >= 200 && i < 320 ? 0.75 : 0.5));
  assert.equal(Math.max(...latchedProgress(spike)), 0.5);
  const hold = Float64Array.from({ length: 600 }, (_, i) => (i >= 200 && i <= 320 ? 0.75 : 0.5));
  const h = latchedProgress(hold);
  assert.equal(h[319], 0.5);
  assert.equal(h[320], 0.75);
  assert.equal(h[599], 0.75, 'it never falls');
  // A grid that carries production's latch (research/tennisTaSim.ts grids: g.progressHigh) is read as it is: here the latch
  // reaches the last share only at 1500, so the not-in-profit fade positions are cut at 1500 and entries stop there.
  const g = endGrid({ resultA: 1 }) as MatchGrid & { progressHigh?: Float64Array };
  g.progressHigh = Float64Array.from({ length: g.n }, (_, i) => (i < 1500 ? 0.5 : 0.75));
  const trips: EntryTrace[] = [];
  const st = new SignalStudy({ trace: (t) => { if (!t.placebo && t.series === MOM60) trips.push(t); } });
  st.addMatch(g);
  const fades = trips.filter((x) => x.dir === 'fade' && x.exit !== 'ts2m');
  assert.equal(fades.length, 4);
  for (const t of fades) assert.ok(t.kind === 'cut' && t.exitDecision === 1500, `${t.exit}: ${t.kind} at ${t.exitDecision}`);
  assert.ok(!trips.some((t) => t.decision >= 1500));
  assert.equal(st.diagnostics().progressHighFromGrid, 1);
  assert.equal((st.exportCells().diagnostics as { settings: { progressLatchMs: number } }).settings.progressLatchMs, PROGRESS_LATCH_MS);
  // Not production's latch: one that falls, or is short.
  const bad = endGrid({ resultA: 1 }) as MatchGrid & { progressHigh?: Float64Array };
  bad.progressHigh = Float64Array.from({ length: bad.n }, (_, i) => (i === 2000 ? 0.75 : 0.5));
  assert.throws(() => new SignalStudy().addMatch(bad), /progressHigh falls/);
  bad.progressHigh = new Float64Array(10);
  assert.throws(() => new SignalStudy().addMatch(bad), /progressHigh samples/);
});

test('after fees on the open contracts\' cost: entry price + entry fee a contract, as production\'s positionNetAtBid', () => {
  // follow buys 18 A at 0.53 (entry fee 0.32). In the last share A's bid is 0.56 (net -0.10: the entry fee makes it a loss)
  // or 0.57 (net +0.09).
  const fill = { ticker: 'KXATPMATCH-X-A', side: 'bid' as const, count: 18, price: 0.53, fee: orderFee(18, 0.53, true, FEES) };
  const pos = new PositionBook().applyFill(fill);
  const cost = openSidePrice(pos)! + openEntryFee(pos)!;
  const prod = (b: number) => positionNetAtBid(pos.yes, cost, { price: b }, undefined, FEES)!;
  assert.ok(Math.abs(prod(0.56) + 0.1) < 1e-9 && Math.abs(prod(0.57) - 0.09) < 1e-9, `${prod(0.56)} ${prod(0.57)}`);
  // Without the entry fee 0.56 would be a profit: the fee is what decides it.
  assert.ok(positionNetAtBid(pos.yes, openSidePrice(pos)!, { price: 0.56 }, undefined, FEES)! > 0);
  for (const [level, kind] of [[0.565, 'cut'], [0.575, 'ride']] as const) {
    const trips: EntryTrace[] = [];
    new SignalStudy({ trace: (t) => { if (!t.placebo && t.series === MOM60 && t.dir === 'follow') trips.push(t); } }).addMatch(endGrid({ resultA: 1, level }));
    assert.equal(trips.length, 5);
    for (const t of trips) {
      assert.equal(t.count, 18);
      assert.equal(t.entryPx, 0.53);
      // ts2m's stop (1121) comes before the latch (1220): a position not in profit keeps its own exit until then.
      assert.equal(t.kind, kind === 'cut' && t.exit === 'ts2m' ? 'time' : kind, `${level} ${t.exit}`);
      if (t.kind === 'cut') { assert.equal(t.exitDecision, 1220); assert.ok(Math.abs(t.net - prod(0.56)) < 1e-9); }
    }
  }
});

test('end cut: a position held to settlement not in profit is a breach, counted per cell', () => {
  // B's book disappears right after the cut decision at 1100: nothing to sell into, B settles at 0.
  const trips: EntryTrace[] = [];
  const st = new SignalStudy({ trace: (t) => { if (!t.placebo && t.series === MOM60) trips.push(t); } });
  st.addMatch(endGrid({ resultA: 1, noBidB: true }));
  const fade = trips.filter((t) => t.dir === 'fade');
  assert.equal(fade.length, 5);
  for (const t of fade) {
    assert.equal(t.kind, 'breach');
    assert.equal(t.exitPx, 0);
    assert.ok(Math.abs(t.net - (-t.count * t.entryPx - orderFee(t.count, t.entryPx, true, FEES))) < 1e-9);
  }
  const cells = byId(st.exportCells().cells);
  for (const x of SIGNAL_SPEC.exits) {
    assert.equal(cells.get(`B|${MOM60}|fade|all|${x}`)!.breaches, 1);
    assert.equal(cells.get(`B|${MOM60}|follow|all|${x}`)!.breaches, 0);
  }
  assert.equal(st.diagnostics().kinds.breach >= 5, true);
  // A match whose progress never reaches the last share: a position still open at closeIdx is a breach too.
  const late: EntryTrace[] = [];
  const g = grid(pathOf(3600, (i) => (i < 3200 ? 0.505 : 0.525)), { seed: 8, day: '2026-01-03', live: 300, progEnd: 0.5, resultA: 1, tape: false });
  new SignalStudy({ trace: (t) => { if (!t.placebo && t.series === MOM60 && t.exit === 'ts10m') late.push(t); } }).addMatch(g);
  assert.ok(late.length === 2 && late.every((t) => t.kind === 'breach'), late.map((t) => t.kind).join());
});

test('H fills are capped at the synthesized book\'s 100 lots; R fills over 100 are counted', () => {
  const p = pathOf(4000, (i) => (i < 1000 ? 0.105 : 0.125));
  for (const stratum of ['H', 'R'] as const) {
    const trips: EntryTrace[] = [];
    const st = new SignalStudy({ orderUsd: 20, trace: (t) => { if (!t.placebo && t.series === MOM60 && t.dir === 'follow') trips.push(t); } });
    st.addMatch(grid(p, { seed: 2, day: '2026-01-02', live: -1, progEnd: 0, resultA: 1, stratum }));
    assert.ok(trips.length > 0);
    // floor(20 / 0.13) = 153 contracts.
    for (const t of trips) assert.equal(t.count, stratum === 'H' ? H_LOT_CAP : 153);
    if (stratum === 'H') assert.ok(st.diagnostics().hCapped > 0);
    else assert.ok(st.diagnostics().rOver100 > 0);
  }
});

test('input contract: unit required, H and R never mixed, any day order (counted), R-only bars refused on H', () => {
  const p = rwPath(1, 2 * 3600);
  const g = (o: Partial<GridOpts> & { day: string }) => grid(p, { seed: 1, live: 600, progEnd: 1, resultA: 1, ...o });
  const noUnit = g({ day: '2026-01-02' });
  delete noUnit.unit;
  assert.throws(() => new SignalStudy().addMatch(noUnit), /no unit/);
  const st = new SignalStudy();
  st.addMatch(g({ day: '2026-01-02' }));
  assert.throws(() => st.addMatch(g({ day: '2026-01-03', stratum: 'R' })), /never mixed/);
  // A grid of an earlier day (a match that finished late) is taken and only counted.
  st.addMatch(g({ day: '2026-01-01', event: 'EV-late' }));
  st.addMatch(g({ day: '2026-01-02', event: 'EV-same-day' }));
  assert.equal(st.diagnostics().outOfOrderGrids, 1);
  assert.equal(st.diagnostics().matches, 3);
  assert.throws(() => new SignalStudy({ bars: ['1m', '30s'], stratum: 'H' }), /recorded books/);
  assert.throws(() => new SignalStudy({ bars: ['1m', '30s'] }).addMatch(g({ day: '2026-01-02' })), /recorded books/);
  assert.throws(() => new SignalStudy({ bars: ['2m'] }), /unknown bar/);
  // The sweep's H study: 1 m and 5 m bars only.
  const h = new SignalStudy({ bars: ['1m', '5m'] });
  h.addMatch(g({ day: '2026-01-02' }));
  for (const c of h.exportCells().cells) assert.ok(!/\|(10s|30s)\|/.test(c.id), c.id);
});

test('TA-Lib: the study refuses to run without the real engine (no silent zero-trigger TA series)', () => {
  const root = path.resolve(import.meta.dirname, '..');
  const script = "import('./research/tennisTaSignals.ts').then((m) => { try { new m.SignalStudy(); console.log('constructed'); } catch (e) { console.log('threw: ' + e.message); } })";
  const out = execFileSync(process.execPath, ['--import', 'tsx', '-e', script], { cwd: root, env: { ...process.env, TA_ENGINE: 'builtin' }, encoding: 'utf8' });
  assert.match(out, /threw: .*TA-Lib engine/);
});

test('exportCells: the C2 shape, with per-unit and per-day rows that add up to the cell', () => {
  const trips: EntryTrace[] = [], tripMatch = new Map<EntryTrace, number>();
  let cur = 0;
  const st = new SignalStudy({ trace: (t) => { trips.push(t); tripMatch.set(t, cur); } });
  const units = ['W-2026-03-02', 'W-2026-03-02', 'W-2026-03-09', 'W-2026-03-09'];
  const days = ['2026-03-02', '2026-03-03', '2026-03-09', '2026-03-10'];
  for (let k = 0; k < 4; k++) {
    cur = k;
    const p = rwPath(70 + k, 3 * 3600);
    st.addMatch(grid(p, { seed: 80 + k, day: days[k], unit: units[k], live: 900, progEnd: 1, resultA: p[p.length - 1] > 0.5 ? 1 : 0 }));
  }
  const ex = st.exportCells();
  assert.equal(ex.stratum, 'H');
  assert.equal(ex.designSize, st.designSize());
  assert.equal(typeof ex.diagnostics, 'object');
  assert.equal((ex.diagnostics as { matches: number }).matches, 4);
  assert.ok(ex.cells.length > 100);
  assert.equal(new Set(ex.cells.map((c) => c.id)).size, ex.cells.length);
  const keys = ['id', 'group', 'n', 'sum', 'sumSq', 'sum3', 'sum4', 'breaches', 'gross', 'fees', 'stressSum', 'units', 'days', 'markets', 'placeboMarkets'];
  for (const c of ex.cells) {
    assert.deepEqual(Object.keys(c).sort(), [...keys].sort());
    let un = 0, us = 0, dn = 0, ds = 0, upn = 0, ups = 0, dpn = 0, dps = 0;
    for (const [u, row] of Object.entries(c.units)) {
      assert.ok(units.includes(u));
      assert.equal(row.length, 4);
      un += row[0]; us += row[1]; upn += row[2]; ups += row[3];
      assert.ok(row[0] > 0 || row[2] > 0);
    }
    // Days carry the placebo columns too (the registry's family B placebo row needs a by_day, C7).
    for (const [d, row] of Object.entries(c.days)) {
      assert.ok(days.includes(d));
      assert.equal(row.length, 4);
      dn += row[0]; ds += row[1]; dpn += row[2]; dps += row[3];
      assert.ok(row[0] > 0 || row[2] > 0);
    }
    assert.equal(un, c.n);
    assert.equal(dn, c.n);
    assert.equal(dpn, upn);
    assert.ok(Math.abs(us - c.sum) < 1e-6 && Math.abs(ds - c.sum) < 1e-6 && Math.abs(dps - ups) < 1e-6);
    assert.ok(Math.abs(c.gross - c.fees - c.sum) < 1e-6);
  }
  // One cell against its positions: moments, stress, placebo columns by unit, days.
  const cell = ex.cells.find((c) => c.id === 'B|MOM|1s|on:w60:0.01|follow|all|ts10m')!;
  assert.ok(cell && cell.n > 5);
  const mine = trips.filter((t) => t.series === MOM60 && t.dir === 'follow' && t.exit === 'ts10m');
  const real = mine.filter((t) => !t.placebo), plac = mine.filter((t) => t.placebo);
  const mom = (k: number) => real.reduce((a, t) => a + t.net ** k, 0);
  assert.equal(cell.n, real.length);
  for (const [k, v] of [[1, cell.sum], [2, cell.sumSq], [3, cell.sum3], [4, cell.sum4]] as const) assert.ok(Math.abs(mom(k) - v) < 1e-6 * Math.max(1, Math.abs(v)), `moment ${k}`);
  assert.ok(Math.abs(real.reduce((a, t) => a + t.stressNet, 0) - cell.stressSum) < 1e-6);
  assert.equal(Object.values(cell.units).reduce((a, u) => a + u[2], 0), plac.length);
  assert.ok(Math.abs(Object.values(cell.units).reduce((a, u) => a + u[3], 0) - plac.reduce((a, t) => a + t.net, 0)) < 1e-6);
  // Markets: distinct match x side with an entry, per arm (the registry rows' markets).
  const mk = (l: typeof mine) => new Set(l.map((t) => `${tripMatch.get(t)}|${t.side}`)).size;
  assert.equal(cell.markets, mk(real));
  assert.equal(cell.placeboMarkets, mk(plac));
  assert.ok(cell.markets > 0 && cell.markets <= real.length);
  // Stress: the same exits, every sale one tick lower and every fee x1.25.
  for (const t of real) {
    const fs = { ...FEES, takerMultiplier: 1.25, makerMultiplier: 1.25 };
    const ps = Math.round(Math.max(t.exitPx - 0.01, 0.01) * 1e4) / 1e4;
    const want = t.kind === 'ride' || t.kind === 'breach'
      ? t.count * (t.exitPx - t.entryPx) - orderFee(t.count, t.entryPx, true, fs)
      : t.count * (ps - t.entryPx) - orderFee(t.count, t.entryPx, true, fs) - orderFee(t.count, ps, true, fs);
    assert.ok(Math.abs(t.stressNet - want) < 1e-9);
  }
  // A study without matches still exports (empty) when it was given its stratum, with that stratum's design.
  const empty = new SignalStudy({ bars: ['1m', '5m'], stratum: 'H' }).exportCells();
  assert.equal(empty.stratum, 'H');
  assert.equal(empty.cells.length, 0);
  assert.equal(empty.designSize, 38 * 2 * 1 * 5);
  const emptyR = new SignalStudy({ stratum: 'R' }).exportCells();
  assert.equal(emptyR.stratum, 'R');
  assert.equal(emptyR.designSize, 68 * 2 * 1 * 5);
  // Without a stratum and without a grid it cannot tell H from R: it refuses rather than guess.
  assert.throws(() => new SignalStudy().exportCells(), /no stratum/);
});

test('design size covers every reported cell', () => {
  const st = new SignalStudy();
  for (let k = 0; k < 3; k++) {
    const p = rwPath(40 + k, 2 * 3600);
    st.addMatch(grid(p, { seed: 60 + k, day: `2026-04-0${k + 1}`, live: 600, progEnd: 1, resultA: 1 }));
  }
  const cells = st.exportCells().cells;
  assert.ok(cells.length > 0);
  assert.ok(st.designSize() >= cells.length);
  // H, one tour series: 38 series x 2 directions x (1 + 5 phases x 5 buckets) contexts x 5 exits. t3 (a reading of 2/3 or
  // more) is in the design: the end-entry block reads the latched progress, so entries go on there until the reading has
  // held 0.65 for 2 min.
  assert.equal(st.designSize(), 38 * 2 * 26 * 5);
  assert.deepEqual((st.exportCells().diagnostics as { settings: { phasesInDesign: string[] } }).settings.phasesInDesign, SIGNAL_SPEC.phases);
  // Here the reading passes 2/3 at 5000 and the latch 0.65 at 5010: a placebo trigger enters in that window.
  assert.ok(cells.some((c) => c.id.includes(':t3:')), 'entries in t3 under the latch');
  assert.equal(new SignalStudy({ settleFrac: 0.2, endEntryMargin: 0.05 }).designSize(), 38 * 2 * 1 * 5);
  for (const c of cells) {
    const parts = c.id.split('|');
    assert.equal(parts.length, 7);
    assert.equal(c.group, parts.slice(0, 5).join('|'));
    assert.ok(SIGNAL_SPEC.exits.includes(parts[6]));
    assert.ok(parts[5] === 'all' || SIGNAL_SPEC.contexts.includes(parts[5]), parts[5]);
    // H runs no 10 s / 30 s bars and no windows under 60 s (Amendment 1, A1).
    assert.ok(parts[2] !== '10s' && parts[2] !== '30s' && !/on:w(15|30):/.test(parts[3]), c.id);
  }
  // Another end rule, the same design.
  const wide = new SignalStudy({ settleFrac: 0.2, endEntryMargin: 0.05 });
  wide.addMatch(grid(rwPath(40, 2 * 3600), { seed: 60, day: '2026-04-01', live: 600, progEnd: 1, resultA: 1 }));
  assert.equal(wide.designSize(), 38 * 2 * 26 * 5);
});
