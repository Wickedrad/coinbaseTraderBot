import assert from 'node:assert/strict';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { test } from 'node:test';
import { buildHistoryReplay } from '../research/history/historyReplay';
import { phaseLabel, runSweep, type SimSpec } from '../research/tennisTaSim';
import type { MatchGrid } from '../research/tennisTaTypes';
import { writeTaHistory } from './tennisTaFixture';

const MIN = 60_000;

async function replayDir(): Promise<string> {
  const hist = fs.mkdtempSync(path.join(os.tmpdir(), 'tta-')), out = path.join(hist, 'replay');
  writeTaHistory(hist);
  await buildHistoryReplay({ historyDir: hist, outDir: out, assets: [], fromDay: '2026-03-02', toDay: '2026-03-03', tennisSeries: ['KXATPMATCH'], log: () => {} });
  return out;
}

const LOOSE = { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0, TENNIS_ENTRY_MIN_SIGNALS_LIVE: 0, TENNIS_FAV_ENTRY_MIN_SIGNALS: 0 };

test('phase labels: pre, the first 20 live minutes, then progress terciles', () => {
  assert.equal(phaseLabel(undefined, 0, 0), 'pre');
  assert.equal(phaseLabel(0, 19 * MIN, 0.5), 'e20');
  assert.deepEqual([0.1, 0.5, 0.9].map((p) => phaseLabel(0, 30 * MIN, p)), ['p1', 'p2', 'p3']);
});

test('tennis TA sweep: configs in lock-step, per-match P&L over every match, episodes add up, F1 never fills more than F0', async () => {
  const dir = await replayDir();
  const specs: SimSpec[] = [
    { id: 'f0', overrides: { ...LOOSE }, fill: 'F0' },
    { id: 'f1', overrides: { ...LOOSE }, fill: 'F1' },
    { id: 'f2', overrides: { ...LOOSE }, fill: 'F2' },
    { id: 'coin', overrides: { ...LOOSE }, fill: 'F1', placebo: 'coin' },
    { id: 'nopacer', overrides: { ...LOOSE, HARNESS_PACER: 'off' }, fill: 'F1' },
    { id: 'ride', overrides: { ...LOOSE, HARNESS_LOSER_CUT: false }, fill: 'F0' },
  ];
  const grids: MatchGrid[] = [];
  const r = await runSweep({ dir, fromDay: '2026-03-02', toDay: '2026-03-02', stratum: 'H', specs, onGrid: (g) => grids.push(g) });
  assert.equal(r.matches, 3);
  assert.equal(r.matchList.length, 3);
  assert.ok(r.matchList.every((m) => m.trades > 100 && m.tickers.length === 2 && !m.unresolved));
  for (const run of r.runs) {
    assert.equal(run.pnl.length, 3, `${run.id}: one value per match`);
    const sumMatch = run.pnl.reduce((a, b) => a + b, 0);
    const sumDays = run.days.reduce((a, d) => a + d.pnl, 0);
    const sumEps = run.episodes.reduce((a, e) => a + e.pnl, 0);
    assert.ok(Math.abs(sumMatch - sumDays) < 1e-3, `${run.id}: matches ${sumMatch} vs days ${sumDays}`);
    assert.ok(Math.abs(sumMatch - sumEps) < 0.02, `${run.id}: matches ${sumMatch} vs episodes ${sumEps}`);
    for (const e of run.episodes) {
      assert.ok(e.m >= 0 && e.m < 3 && (e.k === 0 || e.k === 1), `${run.id}: episode indices`);
      assert.ok(['pre', 'e20', 'p1', 'p2', 'p3'].includes(e.ph));
      assert.ok(e.sig >= 0 && e.sig < 16);
    }
  }
  const by = Object.fromEntries(r.runs.map((x) => [x.id, x]));
  const fills = (id: string) => by[id].days.reduce((a, d) => a + Object.values(d.legs).reduce((s, v) => s + v, 0), 0);
  const entries = (id: string) => by[id].days.reduce((a, d) => a + d.entries, 0);
  assert.ok(entries('f0') > 0, 'the loose config trades');
  assert.ok(entries('f1') <= entries('f0'), `F1 ${entries('f1')} entries vs F0 ${entries('f0')}`);
  assert.ok(fills('f1') > 0, 'F1 fills too');
  // The loser window cut: nothing reaches settlement in breach.
  for (const id of ['f0', 'f1', 'f2', 'coin', 'nopacer']) assert.equal(by[id].days.reduce((a, d) => a + d.breaches, 0), 0, `${id}: no breaches`);
  // Grids: one per match, one sample a second, quotes where the book stood.
  assert.equal(grids.length, 3);
  for (const g of grids) {
    assert.ok(g.n > 3 * 3600 && g.n < 4 * 3600, `grid ${g.n} samples`);
    let quoted = 0;
    for (let i = 0; i < g.n; i++) if (Number.isFinite(g.bidA[i]) && Number.isFinite(g.askA[i])) { quoted++; assert.ok(g.askA[i] > g.bidA[i]); }
    assert.ok(quoted > 0.8 * g.n, `quoted ${quoted}/${g.n}`);
    assert.ok(g.liveIdx > 0 && g.progress[g.n - 1] > 0.5);
  }
  console.log(JSON.stringify(Object.fromEntries(r.runs.map((x) => [x.id, { pnl: x.pnl.map((v) => +v.toFixed(2)), entries: entries(x.id), fills: fills(x.id), legs: x.days[0]?.legs, breaches: x.days.reduce((a, d) => a + d.breaches, 0) }]))));
  console.log(`decisions ${r.decisions}, ${r.ms} ms, ${((r.ms * 1000) / Math.max(1, r.decisions)).toFixed(1)} us per config decision`);
});

test('tennis TA sweep: admit() keeps a match out of the pool, and its configs never see it', async () => {
  const dir = await replayDir();
  const r = await runSweep({ dir, fromDay: '2026-03-02', toDay: '2026-03-02', stratum: 'H', specs: [{ id: 'a', overrides: { ...LOOSE }, fill: 'F1' }], admit: (m) => m.event !== 'KXATPMATCH-M2' });
  assert.deepEqual(r.matchList.map((m) => m.event).sort(), ['KXATPMATCH-M1', 'KXATPMATCH-M3']);
  assert.equal(r.runs[0].pnl.length, 2);
});
