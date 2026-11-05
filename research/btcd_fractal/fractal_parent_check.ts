// Fractal engine parent check (research only; bot/ is not touched).
//
// Runs the bot's own engine (bot/macro/fractalEngine.ts, DEFAULT_FRACTAL: parent 2016-01-01..2018-01-01, child from
// 2018-01-01, weekly bars, 52-bar minimum child) and the walk-forward study of research/fractalStudy.ts on two parents:
//   TV   the live setup: TradingView BTC.D in both windows.
//   CMC  CoinMarketCap BTC.D for the parent window, TradingView BTC.D for the child (from 2018-01-01). CMC's daily rows are
//        dated one day after the close they hold (its 00:02 UTC snapshot), so each row is moved back one day; the
//        lag-correlation check in the round 14 notes puts that at 0.80 against 0.04 for no shift.
// The projections are scored against TradingView BTC.D in both runs (the outcome series does not change).
// Gate 55 and minFit 0.8 are the config defaults (bot/config.ts, WATERFALL_GATE / WATERFALL_MIN_FIT).
//
// Run: /tmp/claude/tsxrun/node_modules/.bin/tsx research/btcd_fractal/fractal_parent_check.ts [--out <file>] [--now <ms>]
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { DEFAULT_FRACTAL, fractalState, projectedCross, type FractalConfig } from '../../bot/macro/fractalEngine';
import type { Candle } from '../../bot/ta/indicators';

const DAY = 86_400_000;
const GATE = 55;
const MIN_FIT = 0.8;
const HERE = path.dirname(fileURLToPath(import.meta.url));
const DATA = path.join(HERE, 'data');
const iso = (t: number) => new Date(t).toISOString().slice(0, 10);
function cliArg(k: string, d: string): string { const i = process.argv.indexOf(`--${k}`); return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d; }

function readDaily(file: string): Candle[] {
  const rows: Candle[] = [];
  for (const line of fs.readFileSync(file, 'utf8').split('\n').slice(1)) {
    const p = line.trim().split(',');
    if (p.length < 5 || !Number.isFinite(Number(p[0]))) continue;
    const [ts, o, h, l, c, v] = p.map(Number);
    rows.push({ ts, o, h, l, c, v: Number.isFinite(v) ? v : 0 } as Candle);
  }
  rows.sort((a, b) => a.ts - b.ts);
  return rows.filter((c, i) => i === 0 || c.ts !== rows[i - 1].ts);
}

function summary(s: NonNullable<ReturnType<typeof fractalState>>) {
  return {
    asOf: iso(s.asOf), parent: iso(s.parentTs), progress: +s.progress.toFixed(3), phase: s.phase,
    dilation: +s.dilation.toFixed(2), localDilation: +s.localDilation.toFixed(2),
    map: { a: +s.map.a.toFixed(2), b: +s.map.b.toFixed(3) },
    fit: { r: +s.fit.r.toFixed(3), recentR: +s.fit.recentR.toFixed(3), maePts: +s.fit.maePts.toFixed(2), recentMaePts: +s.fit.recentMaePts.toFixed(2) },
    btcd: +s.btcd.toFixed(2), proj: { d30: +s.proj.d30.toFixed(2), d90: +s.proj.d90.toFixed(2), d180: +s.proj.d180.toFixed(2) },
    nextWaterfall: s.nextWaterfall ? { start: iso(s.nextWaterfall.startTs), end: iso(s.nextWaterfall.endTs), from: +s.nextWaterfall.fromBtcd.toFixed(1), to: +s.nextWaterfall.toBtcd.toFixed(1), weeksAway: +s.nextWaterfall.weeksAway.toFixed(1), inside: s.nextWaterfall.inside } : null,
    low: s.low ? { at: iso(s.low.ts), btcd: +s.low.btcd.toFixed(1) } : null,
    gateCross: (() => { const c = projectedCross(s, GATE); return c ? iso(c) : null; })(),
  };
}

// The walk-forward of research/fractalStudy.ts, on an injected series: at every week from 52 child bars on, the engine
// sees only data up to that week; its projected BTC.D 30/90/180 days ahead is scored against the TradingView close then.
function study(btcd: Candle[], now: number, cfg: FractalConfig = DEFAULT_FRACTAL) {
  const parentBars = btcd.filter((c) => c.ts >= cfg.parentFrom && c.ts < cfg.parentTo).length;
  const closeAt = (t: number) => { let lo = 0, hi = btcd.length; while (lo < hi) { const m = (lo + hi) >> 1; if (btcd[m].ts + DAY <= t) lo = m + 1; else hi = m; } return lo > 0 ? btcd[lo - 1].c : NaN; };
  const weekly: Array<{ asOf: string; parent: string; progress: number; phase: string; fit: number; recentFit: number; btcd: number }> = [];
  type E = { e: number; f: number; hit: number; fit: number };
  const errs: Record<'d30' | 'd90' | 'd180', E[]> = { d30: [], d90: [], d180: [] };
  for (let t = cfg.childFrom + cfg.minChildBars * cfg.barMs; t <= now; t += cfg.barMs) {
    const s = fractalState(btcd, t, cfg);
    if (!s) continue;
    weekly.push({ asOf: iso(s.asOf), parent: iso(s.parentTs), progress: +s.progress.toFixed(3), phase: s.phase, fit: +s.fit.r.toFixed(3), recentFit: +s.fit.recentR.toFixed(3), btcd: +s.btcd.toFixed(2) });
    for (const [k, days] of [['d30', 30], ['d90', 90], ['d180', 180]] as const) {
      const p = s.proj[k];
      const later = s.asOf + days * DAY;
      if (!Number.isFinite(p) || later > now) continue;
      const real = closeAt(later + DAY);
      if (!Number.isFinite(real)) continue;
      errs[k].push({ e: Math.abs(p - real), f: Math.abs(s.btcd - real), hit: Math.sign(p - s.btcd) === Math.sign(real - s.btcd) ? 1 : 0, fit: Math.min(s.fit.r, s.fit.recentR) });
    }
  }
  const agg = (xs: E[]) => ({
    n: xs.length,
    maeEngine: +(xs.reduce((a, x) => a + x.e, 0) / Math.max(1, xs.length)).toFixed(2),
    maeFlat: +(xs.reduce((a, x) => a + x.f, 0) / Math.max(1, xs.length)).toFixed(2),
    directionHit: +(xs.reduce((a, x) => a + x.hit, 0) / Math.max(1, xs.length)).toFixed(3),
  });
  const skill = Object.fromEntries((['d30', 'd90', 'd180'] as const).map((k) => [k, { ...agg(errs[k]), fitAtLeastMin: agg(errs[k].filter((x) => x.fit >= MIN_FIT)) }]));
  const s = fractalState(btcd, now, cfg);
  return { parentBars, now: s ? summary(s) : null, skill, weekly };
}

function main() {
  const now = Number(cliArg('now', String(Date.now())));
  const out = cliArg('out', path.join(HERE, 'parent_check', 'results.json'));
  const tv = readDaily(path.join(DATA, 'BTC.D_1d.csv'));
  const cmc = readDaily(path.join(DATA, 'BTCD_CMC_1d.csv')).map((c) => ({ ...c, ts: c.ts - DAY }));
  const { parentFrom, parentTo, childFrom } = DEFAULT_FRACTAL;
  const spliced = [...cmc.filter((c) => c.ts >= parentFrom && c.ts < parentTo), ...tv.filter((c) => c.ts >= childFrom)];
  const runs = { TV: study(tv, now), CMC: study(spliced, now) };
  const result = { runUTC: new Date().toISOString(), now: iso(now), gate: GATE, minFit: MIN_FIT, parents: { TV: 'TradingView BTC.D, both windows', CMC: 'CoinMarketCap BTC.D 2016-2017 (dated one day back), TradingView BTC.D from 2018-01-01' }, runs };
  for (const [k, r] of Object.entries(runs)) {
    console.log(`\n== ${k}: parent bars ${r.parentBars}; weekly alignments ${r.weekly.length}`);
    if (r.now) console.log('now:', JSON.stringify(r.now));
    else console.log('now: no alignment');
    for (const [h, v] of Object.entries(r.skill)) console.log(`  ${h}: n ${v.n}, MAE engine ${v.maeEngine} vs flat ${v.maeFlat} pts, direction ${(100 * v.directionHit).toFixed(0)}%; fit >= ${MIN_FIT}: n ${v.fitAtLeastMin.n}, engine ${v.fitAtLeastMin.maeEngine} vs flat ${v.fitAtLeastMin.maeFlat}, direction ${(100 * v.fitAtLeastMin.directionHit).toFixed(0)}%`);
  }
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, JSON.stringify(result, null, 2));
  console.log(`\nwrote ${out}`);
}

main();
