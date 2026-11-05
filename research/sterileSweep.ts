// Sterile sweep (Steven, Nov 5: "in a sterile environment sweep parameters and market data ... for the shortest
// timeframe ... flag all outcomes that were in profit, then find real-world examples of those conditions to blind test
// the features on"). Simulated 15-minute markets over a grid of market conditions, each feature setting run on them with
// the real bot code (research/randomSweep.ts evalTrial -> research/backtest.ts), against the baseline and a placebo.
//
// A condition cell is one combination of:
//   vol     the index's volatility, bp a minute (0.25, 0.5, 1, 2: the real buckets of randomSweep.regimeKey)
//   trend   the volatility over the stretch: rising (x0.5 -> x2) or calming (x2 -> x0.5), as rv15m / rv1h reads it
//   drift   none, or a steady push of 0.3 sd a minute in one direction (flips each window)
//   market  how Kalshi's quote follows the coin's fair value: 'fair' (fair value + noise), 'longshot' (the side under
//           30c priced 5c rich, the favourite-longshot bias), 'lag' (the quote closes a quarter of the gap every 15 s,
//           the fidelity thread's fitted quote lag)
// Each cell is 16 windows (4 hours) per seed. Synthetic markets test where a setting CAN pay; they prove nothing about
// real edge: every flagged cell must be found in real history and blind-tested there (stage `real` in the report).
//
//   node --import tsx research/sterileSweep.ts gen --out data/sterile [--seeds 2] [--windows 16]
//   node --import tsx research/sterileSweep.ts run --dir data/sterile --variant tp_be --model data/models/model.json --out research/out/sterile
//   node --import tsx research/sterileSweep.ts report --out research/out/sterile

import fs from 'fs';
import path from 'path';
import { fairValue } from '../bot/model/fairValue';
import { rng } from './stats';

export interface Scenario { vol: number; trend: 'rising' | 'calming'; drift: 0 | 1; market: 'fair' | 'longshot' | 'lag'; seed: number }

export const GRID = {
  vol: [0.25, 0.5, 1, 2],
  trend: ['rising', 'calming'] as const,
  drift: [0, 1] as const,
  market: ['fair', 'longshot', 'lag'] as const,
};

/** The settings swept: the benched features' reworked forms (research/benchedJobs.ts), each on top of the baseline. */
export const SETTINGS: Record<string, Record<string, string>> = {
  baseline: {},
  placebo: { RS_TICK_PHASE_MS: '500' },
  tp_be: { TP_LEVEL: '0', PROFIT_TARGET_CENTS: '0.5', PROFIT_TARGET_PCT: '0' },
  tp_1c: { TP_LEVEL: '0', PROFIT_TARGET_CENTS: '1', PROFIT_TARGET_PCT: '0' },
  tp_l1: { TP_LEVEL: '1' },
  skill_w75: { MODEL_SKILL_W: '0.75' },
  tails50: { MODEL_SKILL_W_TAILS: '0.5' },
  dip8: { SINUOUS_DIP_BUY: 'true', SINUOUS_DIP_MARGIN: '0.08' },
  cross_l1: { SINUOUS_CROSS: 'true', SINUOUS_CROSS_LEVEL: '1' },
};

export const cellKey = (s: Omit<Scenario, 'seed'>) => `vol${s.vol}bp|${s.trend}|${s.drift ? 'drift' : 'flat'}|${s.market}`;

export function scenarios(seeds: number): Scenario[] {
  const out: Scenario[] = [];
  for (const vol of GRID.vol) for (const trend of GRID.trend) for (const drift of GRID.drift) for (const market of GRID.market)
    for (let seed = 1; seed <= seeds; seed++) out.push({ vol, trend, drift, market, seed });
  return out;
}

/** One cell's recording (the server's md-DAY.jsonl format, as research/synthetic.ts): index and spot at 1 s, a 15-minute
 *  market every window with a five-level book every 5 s and random prints at the touch. */
export function writeScenario(dir: string, sc: Scenario, windows = 16, startMs = Date.parse('2026-01-05T00:00:00Z')): void {
  fs.mkdirSync(dir, { recursive: true });
  const r = rng(1000 * sc.seed + Math.round(sc.vol * 100) + (sc.trend === 'rising' ? 7 : 3) + sc.drift * 11 + ({ fair: 0, longshot: 17, lag: 29 })[sc.market]);
  const gauss = () => Math.sqrt(-2 * Math.log(r() + 1e-12)) * Math.cos(2 * Math.PI * r());
  const W = 15 * 60, WARM = 3600;
  const total = WARM + windows * W + 120;
  const base = (sc.vol * 1e-4) / Math.sqrt(60); // sd per sqrt(second)
  // Volatility multiplier over the stretch (warm-up included, so the hour's vol leads the 15 minutes' as it should).
  const volAt = (s: number) => { const f = s / total; return sc.trend === 'rising' ? 0.5 * Math.pow(4, f) : 2 * Math.pow(0.25, f); };
  const LEAD = 3;
  const walk: number[] = [];
  let x = Math.log(60000);
  for (let s = 0; s < total + LEAD + 1; s++) {
    const sig = base * volAt(s);
    const w = Math.floor(Math.max(0, s - WARM) / W);
    const mu = sc.drift ? (w % 2 ? -1 : 1) * 0.3 * sig * Math.sqrt(60) / 60 : 0;
    x += mu + sig * gauss();
    walk.push(Math.exp(x));
  }
  const lines: string[] = [];
  const hist: number[] = [];
  const quoted = new Map<number, number>();
  for (let s = 0; s < total; s++) {
    const t = startMs + s * 1000, S = walk[s];
    hist.push(S);
    lines.push(JSON.stringify({ t, k: 'index', asset: 'BTC', value: S, ts: t, src: 'synthetic' }));
    lines.push(JSON.stringify({ t, k: 'spot', asset: 'BTC', value: walk[s + LEAD] * (1 + 0.00002 * gauss()), ts: t }));
    const rel = s - WARM;
    if (rel < 0) continue;
    const w = Math.floor(rel / W);
    if (w >= windows) continue;
    const open = startMs + (WARM + w * W) * 1000, close = open + W * 1000;
    const ticker = `STR-${w}`;
    if (rel % W === 0) {
      const strike = hist.slice(-60).reduce((a, b) => a + b, 0) / Math.min(60, hist.length);
      lines.push(JSON.stringify({ t, k: 'market', ticker, series: 'KXBTC15M', asset: 'BTC', openTime: open, closeTime: close, strike, tickSize: 0.01 }));
    }
    if (rel % 5 !== 0) continue;
    const strike = hist.slice(Math.max(0, WARM + w * W - 60), WARM + w * W).reduce((a, b) => a + b, 0) / 60 || S;
    const tau = (close - t) / 1000;
    const obs = tau <= 60 ? hist.slice(-(60 - tau)).reduce((a, b) => a + b, 0) / Math.max(1, 60 - tau) : undefined;
    const fv = fairValue({ spot: S, strike, sigmaPerSqrtSec: base * volAt(s), tauSec: tau, observedAvg: obs })?.pYes ?? 0.5;
    let m = fv + 0.02 * gauss();
    if (sc.market === 'longshot') m += fv < 0.3 ? 0.05 : fv > 0.7 ? -0.05 : 0;
    if (sc.market === 'lag') { const prev = quoted.get(w); m = prev === undefined ? fv : prev + 0.25 * (fv - prev) / 3 + 0.01 * gauss(); quoted.set(w, m); }
    m = Math.min(0.97, Math.max(0.03, m));
    const bid = Math.max(0.01, Math.floor((m - 0.02) * 100) / 100);
    const ask = Math.min(0.99, Math.ceil((m + 0.02) * 100) / 100);
    const lvls = (p0: number, dir: number) => Array.from({ length: 5 }, (_, i) => ({ price: Math.round((p0 + dir * i * 0.01) * 100) / 100, size: Math.round(5 + r() * 45) }))
      .filter((l) => l.price >= 0.01 && l.price <= 0.99);
    lines.push(JSON.stringify({ t, k: 'book', ticker, bids: lvls(bid, -1), asks: lvls(ask, 1), ts: t }));
    if (r() < 0.4) lines.push(JSON.stringify({ t, k: 'trade', ticker, price: r() < 0.5 ? bid : ask, count: 1 + Math.floor(r() * 10), takerSide: r() < 0.5 ? 'no' : 'yes', ts: t }));
  }
  fs.writeFileSync(path.join(dir, `md-${new Date(startMs).toISOString().slice(0, 10)}.jsonl`), lines.join('\n') + '\n');
}

const dirName = (sc: Scenario) => `${cellKey(sc).replace(/\|/g, '_')}_s${sc.seed}`;

function arg(k: string, d: string): string { const i = process.argv.indexOf(`--${k}`); return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : d; }
const f2 = (x: number) => (x >= 0 ? '+' : '') + x.toFixed(2);

interface CellResult { cell: string; seed: number; pnl: number; trades: number; fees: number; ok: boolean; error?: string }

async function main(): Promise<void> {
  const cmd = process.argv[2];
  if (cmd === 'gen') {
    const out = arg('out', 'data/sterile'), seeds = Number(arg('seeds', '2')), windows = Number(arg('windows', '16'));
    const all = scenarios(seeds);
    for (const sc of all) writeScenario(path.join(out, dirName(sc)), sc, windows);
    console.log(`[sterile] ${all.length} scenarios (${all.length / seeds} cells x ${seeds} seeds, ${windows} windows each) in ${out}`);
    return;
  }
  if (cmd === 'run') {
    const dir = arg('dir', 'data/sterile'), name = arg('variant', 'baseline'), out = arg('out', 'research/out/sterile');
    const env = SETTINGS[name];
    if (!env) throw new Error(`unknown setting ${name} (${Object.keys(SETTINGS).join(', ')})`);
    const { evalTrial } = await import('./randomSweep');
    const rows: CellResult[] = [];
    const t0 = Date.now();
    for (const d of fs.readdirSync(dir).sort()) {
      const m = /^(vol[\d.]+bp)_(rising|calming)_(flat|drift)_(fair|longshot|lag)_s(\d+)$/.exec(d);
      if (!m) continue;
      const r = await evalTrial(path.join(dir, d), arg('model', 'data/models/model.json'), env, 3, 'all');
      rows.push({ cell: `${m[1]}|${m[2]}|${m[3]}|${m[4]}`, seed: Number(m[5]), pnl: r.pnl, trades: r.trades, fees: r.fees, ok: r.ok, ...(r.ok ? {} : { error: r.error }) });
    }
    fs.mkdirSync(out, { recursive: true });
    fs.writeFileSync(path.join(out, `${name}.json`), JSON.stringify({ name, rows }));
    const ok = rows.filter((x) => x.ok);
    console.log(`[sterile] ${name}: ${ok.length}/${rows.length} scenarios, P&L ${f2(ok.reduce((a, x) => a + x.pnl, 0))}, ${ok.reduce((a, x) => a + x.trades, 0)} trades in ${((Date.now() - t0) / 60_000).toFixed(1)} min${rows.length > ok.length ? `; first error: ${rows.find((x) => !x.ok)?.error}` : ''}`);
    return;
  }
  if (cmd === 'report') {
    const out = arg('out', 'research/out/sterile');
    const res = new Map<string, CellResult[]>();
    for (const f of fs.existsSync(out) ? fs.readdirSync(out) : []) if (f.endsWith('.json')) { const j = JSON.parse(fs.readFileSync(path.join(out, f), 'utf8')); res.set(j.name, j.rows); }
    const base = res.get('baseline');
    if (!base) { console.log('no baseline'); return; }
    const key = (x: CellResult) => `${x.cell}#${x.seed}`;
    const bmap = new Map(base.filter((x) => x.ok).map((x) => [key(x), x]));
    // The noise floor: the placebo's absolute gap from the baseline per cell (summed over seeds).
    const cellDiff = (rows: CellResult[]) => {
      const g = new Map<string, { d: number; pnl: number; n: number; up: number }>();
      for (const x of rows) { const b = bmap.get(key(x)); if (!x.ok || !b) continue; const c = g.get(x.cell) ?? { d: 0, pnl: 0, n: 0, up: 0 }; c.d += x.pnl - b.pnl; c.pnl += x.pnl; c.n++; c.up += x.pnl - b.pnl > 0 ? 1 : 0; g.set(x.cell, c); }
      return g;
    };
    const plc = res.get('placebo');
    const noise = plc ? [...cellDiff(plc).values()].map((c) => Math.abs(c.d)) : [];
    const floor = noise.length ? noise.sort((a, b) => a - b)[Math.floor(noise.length * 0.9)] : 0;
    const bcell = new Map<string, number>();
    for (const x of base) if (x.ok) bcell.set(x.cell, (bcell.get(x.cell) ?? 0) + x.pnl);
    console.log(`sterile sweep: ${bmap.size} scenarios, ${bcell.size} cells; baseline P&L ${f2([...bcell.values()].reduce((a, v) => a + v, 0))}; placebo noise floor (90th pct |gap| per cell) ${floor.toFixed(2)}`);
    console.log(`baseline profitable cells: ${[...bcell].filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ${f2(v)}`).join(', ') || 'none'}`);
    for (const [name, rows] of [...res].sort()) {
      if (name === 'baseline' || name === 'placebo') continue;
      const g = cellDiff(rows);
      const tot = [...g.values()].reduce((a, c) => a + c.d, 0);
      const flagged = [...g].filter(([, c]) => c.d > floor && c.pnl > 0 && c.up === c.n).sort((a, b) => b[1].d - a[1].d);
      const hurt = [...g].filter(([, c]) => c.d < -floor).sort((a, b) => a[1].d - b[1].d);
      console.log(`${name.padEnd(10)} vs baseline ${f2(tot)} over ${g.size} cells | FLAGGED (beats the placebo floor on every seed, and in profit): ${flagged.map(([k, c]) => `${k} ${f2(c.d)} (P&L ${f2(c.pnl)})`).join(', ') || 'none'}`);
      if (hurt.length) console.log(`${''.padEnd(10)} hurts: ${hurt.slice(0, 8).map(([k, c]) => `${k} ${f2(c.d)}`).join(', ')}`);
      // By each dimension alone: where the setting helps on average.
      for (const dim of [0, 1, 2, 3]) {
        const m = new Map<string, number>();
        for (const [k, c] of g) { const p = k.split('|')[dim]; m.set(p, (m.get(p) ?? 0) + c.d); }
        console.log(`${''.padEnd(10)} by ${['vol', 'trend', 'drift', 'market'][dim]}: ${[...m].map(([k, v]) => `${k} ${f2(v)}`).join(', ')}`);
      }
    }
    return;
  }
  throw new Error('usage: sterileSweep.ts gen|run|report (see the header)');
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) main().catch((e) => { console.error((e as Error).stack ?? e); process.exitCode = 1; });
